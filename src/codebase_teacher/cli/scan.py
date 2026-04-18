"""CLI command: teach scan <path> — discover and classify codebase."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from codebase_teacher.core.config import Settings
from codebase_teacher.core.exceptions import LearnerInfoTooLarge
from codebase_teacher.scanner.dependency import detect_dependencies, print_dependency_report
from codebase_teacher.scanner.discovery import auto_select_all, interactive_folder_selection
from codebase_teacher.scanner.file_classifier import classify_directory
from codebase_teacher.scanner.learner_info import load_learner_info
from codebase_teacher.storage.database import Database

console = Console()


@click.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--auto", is_flag=True, help="Auto-select all folders (non-interactive, for headless/mobile use)")
@click.pass_context
def scan(ctx: click.Context, path: str, auto: bool) -> None:
    """Scan a codebase — discover folders and classify files."""
    root = Path(path)
    settings = Settings()
    if ctx.obj.get("model"):
        settings.model = ctx.obj["model"]

    console.print(f"\n[bold]Scanning codebase:[/] {root}")

    try:
        learner_info = load_learner_info(root)
    except LearnerInfoTooLarge as e:
        console.print(f"[red bold]{e}[/]")
        sys.exit(1)
    if learner_info:
        console.print(
            "[cyan]Detected LEARNER-INFO.md — will guide analysis and doc generation.[/]"
        )

    # Set up database
    db = Database(settings.db_path(root))
    project_id = db.get_or_create_project(str(root), root.name)

    # Step 1: Folder discovery
    console.print("\n[bold cyan]Step 1: Folder Discovery[/]")
    if auto:
        relevant_folders = auto_select_all(root, db, project_id, console)
    else:
        relevant_folders = interactive_folder_selection(root, db, project_id, console)

    # Step 2: Classify files
    console.print("\n[bold cyan]Step 2: Classifying files...[/]")
    files = classify_directory(root, relevant_folders)

    # Store classifications
    for file_info in files:
        db.set_file_classification(
            project_id, file_info.path, file_info.category,
            file_info.language, file_info.token_estimate,
        )

    # Print summary
    categories: dict[str, int] = {}
    languages: dict[str, int] = {}
    for f in files:
        categories[f.category] = categories.get(f.category, 0) + 1
        if f.language:
            languages[f.language] = languages.get(f.language, 0) + 1

    console.print(f"\n[bold]Files classified:[/] {len(files)} total")
    for cat, count in sorted(categories.items()):
        console.print(f"  {cat}: {count}")

    if languages:
        console.print("\n[bold]Languages detected:[/]")
        for lang, count in sorted(languages.items(), key=lambda x: -x[1]):
            console.print(f"  {lang}: {count} files")

    # Step 3: Dependency analysis
    console.print("\n[bold cyan]Step 3: Analyzing dependencies...[/]")
    dep_report = detect_dependencies(root)
    print_dependency_report(dep_report, console)

    console.print("\n[green bold]Scan complete![/] Run [bold]teach analyze {path}[/] next.")
    db.close()
