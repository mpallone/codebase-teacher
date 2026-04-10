"""Build review packets from repo source + teach output.

A review packet is a self-contained markdown file that gives Claude Code
everything it needs to judge the quality of teach's output for a repo:
the judging rubric, repo metadata, source samples, and all generated docs.
"""

from __future__ import annotations

import os
from pathlib import Path


# Max tokens worth of source files to include (~4 chars/token).
SOURCE_BUDGET_CHARS = 120_000  # ~30K tokens


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

    # Repo README
    readme = _read_readme(repo_path)
    if readme:
        sections.append("---\n## Repo README (excerpt)\n")
        sections.append(readme[:5000])

    # Directory tree
    sections.append("---\n## Directory Structure\n")
    sections.append("```")
    sections.append(_build_tree(repo_path))
    sections.append("```")

    # Source samples
    sections.append("---\n## Source Code Samples\n")
    sections.append(_sample_source_files(repo_path, language))

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


def _sample_source_files(repo_path: Path, language: str) -> str:
    """Select and include source files, staying within the token budget."""
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
        # Prune skipped directories
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
        for fname in files:
            fpath = Path(root_dir) / fname
            if fpath.suffix in extensions:
                source_files.append(fpath)

    # Sort: shorter paths first (likely entry points / top-level modules)
    source_files.sort(key=lambda p: (len(p.relative_to(repo_path).parts), p.name))

    chunks: list[str] = []
    chars_used = 0

    for fpath in source_files:
        if chars_used >= SOURCE_BUDGET_CHARS:
            remaining = len(source_files) - len(chunks)
            if remaining > 0:
                chunks.append(f"\n*({remaining} more source files not shown — budget exceeded)*\n")
            break

        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        rel = fpath.relative_to(repo_path)
        header = f"\n### `{rel}`\n```{language}\n"
        footer = "\n```\n"
        entry = header + content + footer

        if chars_used + len(entry) > SOURCE_BUDGET_CHARS:
            # Truncate this file to fit remaining budget
            remaining_chars = SOURCE_BUDGET_CHARS - chars_used - len(header) - len(footer) - 50
            if remaining_chars > 500:
                entry = header + content[:remaining_chars] + "\n... (truncated)\n" + footer
            else:
                remaining = len(source_files) - len(chunks)
                chunks.append(f"\n*({remaining} more source files not shown — budget exceeded)*\n")
                break

        chunks.append(entry)
        chars_used += len(entry)

    if not chunks:
        return "*No source files found.*\n"

    prefix = "\n###"
    shown = len([c for c in chunks if c.startswith(prefix)])
    return f"Showing {shown} of {len(source_files)} source files.\n" + "".join(chunks)


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
