"""Codebase discovery — walk directories and let user mark folders as relevant."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.prompt import Prompt
from rich.tree import Tree

from codebase_teacher.storage.database import Database

# Directories to always skip
ALWAYS_SKIP = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules", ".tox", ".mypy_cache",
    ".pytest_cache", ".eggs", "*.egg-info", ".venv", "venv", "env", ".env",
    ".teacher", ".teacher-output", "dist", "build", ".idea", ".vscode",
}


def _should_skip(name: str) -> bool:
    """Check if a directory name should always be skipped."""
    return name in ALWAYS_SKIP or name.startswith(".")


def _load_gitignore_patterns(root: Path) -> list[str]:
    """Load patterns from .gitignore if it exists."""
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        return []
    patterns = []
    for line in gitignore.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def _is_gitignored(path: Path, root: Path, patterns: list[str]) -> bool:
    """Simple gitignore check — not fully spec-compliant but handles common cases."""
    rel = str(path.relative_to(root))
    for pattern in patterns:
        clean = pattern.rstrip("/")
        if clean in rel or rel.endswith(clean):
            return True
    return False


def discover_folders(root: Path) -> list[Path]:
    """Walk the directory tree and return all non-skipped top-level folders."""
    if not root.is_dir():
        raise FileNotFoundError(f"Not a directory: {root}")

    gitignore_patterns = _load_gitignore_patterns(root)
    folders: list[Path] = []

    for item in sorted(root.iterdir()):
        if not item.is_dir():
            continue
        if _should_skip(item.name):
            continue
        if _is_gitignored(item, root, gitignore_patterns):
            continue
        folders.append(item)

    return folders


def build_folder_tree(root: Path, max_depth: int = 3) -> Tree:
    """Build a rich Tree showing the folder structure."""
    tree = Tree(f"[bold blue]{root.name}/[/]")
    _add_to_tree(tree, root, max_depth, current_depth=0)
    return tree


def _add_to_tree(tree: Tree, path: Path, max_depth: int, current_depth: int) -> None:
    if current_depth >= max_depth:
        return

    try:
        entries = sorted(path.iterdir())
    except PermissionError:
        return

    dirs = [e for e in entries if e.is_dir() and not _should_skip(e.name)]
    files = [e for e in entries if e.is_file()]

    for d in dirs:
        branch = tree.add(f"[bold blue]{d.name}/[/]")
        _add_to_tree(branch, d, max_depth, current_depth + 1)

    # Show file count instead of every file at deeper levels
    if current_depth < max_depth - 1:
        for f in files[:10]:
            tree.add(f"[dim]{f.name}[/]")
        if len(files) > 10:
            tree.add(f"[dim]... and {len(files) - 10} more files[/]")
    elif files:
        tree.add(f"[dim]{len(files)} files[/]")


def auto_select_all(
    root: Path,
    db: Database,
    project_id: int,
    console: Console | None = None,
) -> list[str]:
    """Non-interactive: mark all discovered folders as relevant.

    Use this instead of interactive_folder_selection() when running headlessly
    (e.g. from Claude Code on iOS via --auto flag).
    """
    console = console or Console()
    folders = discover_folders(root)
    relevant: list[str] = []

    for folder in folders:
        rel_path = str(folder.relative_to(root))
        db.set_folder_status(project_id, rel_path, "relevant")
        relevant.append(rel_path)

    if not relevant:
        relevant = ["."]

    console.print(f"[green]Auto-selected {len(relevant)} folder(s).[/]")
    return relevant


def interactive_folder_selection(
    root: Path,
    db: Database,
    project_id: int,
    console: Console | None = None,
) -> list[str]:
    """Interactively ask the user about each folder's relevance.

    Returns list of relevant folder paths (relative to root).
    """
    console = console or Console()
    folders = discover_folders(root)

    if not folders:
        console.print("[yellow]No subdirectories found.[/]")
        return ["."]

    console.print("\n[bold]Codebase folder structure:[/]")
    tree = build_folder_tree(root)
    console.print(tree)
    console.print()

    # Check for existing decisions
    existing = db.get_folder_statuses(project_id)
    relevant: list[str] = []

    console.print(
        "[bold]For each folder, indicate if it's relevant to what you want to learn.[/]"
    )
    console.print("[dim]Options: (y)es / (n)o / (s)kip (I don't know)[/]\n")

    for folder in folders:
        rel_path = str(folder.relative_to(root))

        # Use existing decision if available
        if rel_path in existing:
            status = existing[rel_path]
            console.print(f"  {rel_path}: [dim]previously marked as {status}[/]")
            if status == "relevant":
                relevant.append(rel_path)
            continue

        # Count files for context
        file_count = sum(1 for _ in folder.rglob("*") if _.is_file())
        choice = Prompt.ask(
            f"  [bold]{rel_path}/[/] ({file_count} files)",
            choices=["y", "n", "s"],
            default="y",
        )

        if choice == "y":
            db.set_folder_status(project_id, rel_path, "relevant")
            relevant.append(rel_path)
        elif choice == "n":
            db.set_folder_status(project_id, rel_path, "irrelevant")
        else:
            db.set_folder_status(project_id, rel_path, "unknown")

    if not relevant:
        console.print("[yellow]No folders marked as relevant. Including root.[/]")
        relevant = ["."]

    console.print(f"\n[green]Selected {len(relevant)} relevant folder(s).[/]")
    return relevant
