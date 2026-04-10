"""Build review packets from repo source + teach output.

A review packet is a self-contained markdown file that gives Claude Code
everything it needs to judge the quality of teach's output for a repo:
the judging rubric, repo metadata, ALL source code, and all generated docs.

All test repos are < 20K lines, so we include every source file in full —
no sampling, no truncation. The judge needs complete source to catch both
hallucinations (claims not in the code) and omissions (code not in the docs).
"""

from __future__ import annotations

import os
from pathlib import Path


def build_packet(
    slug: str,
    repo_path: Path,
    output_dir: Path,
    dest: Path,
    language: str = "unknown",
) -> Path:
    """Build a review packet for a single repo.

    Args:
        slug: Repo identifier (e.g. "flask").
        repo_path: Path to the cloned repo.
        output_dir: Path to .teacher-output/ directory.
        dest: Where to write the packet.md file.
        language: Primary language of the repo.

    Returns:
        Path to the written packet file.
    """
    sections = []

    # Header with rubric
    rubric = _load_rubric()
    sections.append(f"# Eval Packet: {slug}\n")
    sections.append(f"**Language:** {language}\n")
    sections.append(f"**Repo path:** `{repo_path}`\n")
    sections.append(rubric)

    # Repo README (full text)
    readme = _read_readme(repo_path)
    if readme:
        sections.append("---\n## Repo README\n")
        sections.append(readme)

    # Directory tree
    sections.append("---\n## Directory Structure\n")
    sections.append("```")
    sections.append(_build_tree(repo_path))
    sections.append("```")

    # All source files
    sections.append("---\n## Source Code (complete)\n")
    sections.append(_all_source_files(repo_path, language))

    # Generated docs (full text)
    sections.append("---\n## Generated Documentation (teach output)\n")
    sections.append(_read_generated_docs(output_dir))

    packet_text = "\n".join(sections)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(packet_text, encoding="utf-8")
    return dest


def _load_rubric() -> str:
    """Load the judge rubric from prompts/."""
    rubric_path = Path(__file__).parent / "prompts" / "judge_rubric.md"
    if rubric_path.exists():
        return "\n## Judging Rubric\n\n" + rubric_path.read_text(encoding="utf-8")
    return ""


def _read_readme(repo_path: Path) -> str:
    """Read README.md or README from the repo."""
    for name in ("README.md", "README.rst", "README.txt", "README"):
        readme = repo_path / name
        if readme.exists():
            return readme.read_text(encoding="utf-8", errors="ignore")
    return ""


def _build_tree(root: Path, max_depth: int = 3) -> str:
    """Build a directory tree string, skipping common noise directories."""
    skip = {
        ".git", "__pycache__", "node_modules", ".tox", ".mypy_cache",
        ".pytest_cache", ".eggs", ".venv", "venv", ".teacher", ".teacher-output",
        "dist", "build", ".idea", ".vscode", ".gradle", "target",
    }
    lines: list[str] = []
    _tree_walk(root, root, lines, skip, max_depth, 0)
    return "\n".join(lines)


def _tree_walk(
    root: Path, current: Path, lines: list[str],
    skip: set[str], max_depth: int, depth: int,
) -> None:
    if depth >= max_depth:
        return
    try:
        entries = sorted(current.iterdir())
    except PermissionError:
        return

    indent = "  " * depth
    dirs = [e for e in entries if e.is_dir() and e.name not in skip and not e.name.startswith(".")]
    files = [e for e in entries if e.is_file()]

    for d in dirs:
        lines.append(f"{indent}{d.name}/")
        _tree_walk(root, d, lines, skip, max_depth, depth + 1)

    for f in files[:15]:
        lines.append(f"{indent}{f.name}")
    if len(files) > 15:
        lines.append(f"{indent}... and {len(files) - 15} more files")


def _all_source_files(repo_path: Path, language: str) -> str:
    """Include every source file in full. No sampling, no truncation.

    All test repos are < 20K lines, so including everything is safe and
    gives the judge complete visibility to catch omissions and hallucinations.
    """
    ext_map = {
        "python": {".py"},
        "java": {".java"},
        "scala": {".scala"},
        "terraform": {".tf"},
    }
    extensions = ext_map.get(language, {".py", ".java", ".scala", ".tf"})

    # Collect all source files (exclude tests, vendored code, generated files)
    skip_dirs = {
        ".git", "__pycache__", "node_modules", "test", "tests", "spec",
        ".teacher", ".teacher-output", "vendor", "third_party", "build",
        "dist", "target", ".gradle",
    }

    source_files: list[Path] = []
    for root_dir, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
        for fname in files:
            fpath = Path(root_dir) / fname
            if fpath.suffix in extensions:
                source_files.append(fpath)

    # Sort: shorter paths first (likely entry points / top-level modules)
    source_files.sort(key=lambda p: (len(p.relative_to(repo_path).parts), p.name))

    chunks: list[str] = []
    for fpath in source_files:
        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = fpath.relative_to(repo_path)
        chunks.append(f"\n### `{rel}`\n```{language}\n{content}\n```\n")

    if not chunks:
        return "*No source files found.*\n"

    return f"All {len(chunks)} source files included.\n" + "".join(chunks)


def _read_generated_docs(output_dir: Path) -> str:
    """Read all generated markdown files from .teacher-output/."""
    if not output_dir.exists():
        return "*No teach output found.*\n"

    sections: list[str] = []
    for subdir_name in ("docs", "diagrams"):
        subdir = output_dir / subdir_name
        if not subdir.exists():
            continue
        for md_file in sorted(subdir.glob("*.md")):
            content = md_file.read_text(encoding="utf-8", errors="ignore")
            sections.append(f"\n### {subdir_name}/{md_file.name}\n\n{content}\n")

    if not sections:
        return "*No generated documentation files found.*\n"

    return "".join(sections)
