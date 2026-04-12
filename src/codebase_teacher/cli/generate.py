"""CLI command: teach generate <path> — generate documentation and diagrams."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import click
from pydantic import ValidationError
from rich.console import Console

from codebase_teacher.core.config import Settings
from codebase_teacher.core.exceptions import AnalysisError
from codebase_teacher.generator.diagrams import generate_all_diagrams
from codebase_teacher.generator.docs import generate_all_docs
from codebase_teacher.llm.factory import create_provider
from codebase_teacher.storage.artifact_store import ArtifactStore
from codebase_teacher.storage.database import Database
from codebase_teacher.storage.models import AnalysisResult

console = Console()


@click.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--type", "gen_type", type=click.Choice(["all", "docs", "diagrams"]), default="all")
@click.pass_context
def generate(ctx: click.Context, path: str, gen_type: str) -> None:
    """Generate documentation and diagrams from analysis results."""
    root = Path(path)
    settings = Settings()
    if ctx.obj.get("provider"):
        settings.provider = ctx.obj["provider"]
    if ctx.obj.get("model"):
        settings.model = ctx.obj["model"]

    console.print(f"\n[bold]Generating content for:[/] {root}")
    console.print(f"[dim]Provider: {settings.provider}[/]")
    console.print(f"[dim]Output: {settings.output_path(root)}[/]")

    asyncio.run(_generate_async(root, settings, gen_type))


async def _generate_async(root: Path, settings: Settings, gen_type: str) -> None:
    db = Database(settings.db_path(root))
    project_id = db.get_or_create_project(str(root), root.name)

    # Load cached analysis
    try:
        analysis = _load_analysis(db, project_id)
    except AnalysisError as e:
        console.print(f"[red bold]{e}[/]")
        db.close()
        sys.exit(1)

    if analysis is None:
        console.print("[red]No analysis data found. Run [bold]teach analyze[/] first.[/]")
        db.close()
        return

    # Set up LLM and artifact store
    provider = create_provider(settings)
    output_dir = settings.output_path(root)
    store = ArtifactStore(output_dir, db, project_id)

    generated: list[Path] = []
    all_errors: list[tuple[str, Exception]] = []

    if gen_type in ("all", "docs"):
        console.print("\n[bold cyan]Generating documentation...[/]")
        doc_paths, doc_errors = await generate_all_docs(provider, analysis, store)
        generated.extend(doc_paths)
        all_errors.extend(doc_errors)
        for p in doc_paths:
            console.print(f"  [green]Created:[/] {p.relative_to(root)}")
        for name, err in doc_errors:
            console.print(f"  [red]Failed:[/] {name}: {err}")

    if gen_type in ("all", "diagrams"):
        console.print("\n[bold cyan]Generating diagrams...[/]")
        diagram_paths, diagram_errors = await generate_all_diagrams(provider, analysis, store)
        generated.extend(diagram_paths)
        all_errors.extend(diagram_errors)
        for p in diagram_paths:
            console.print(f"  [green]Created:[/] {p.relative_to(root)}")
        for name, err in diagram_errors:
            console.print(f"  [red]Failed:[/] {name}: {err}")

    if all_errors:
        console.print(
            f"\n[red bold]Generated {len(generated)} file(s), "
            f"{len(all_errors)} failed.[/]"
        )
    else:
        console.print(f"\n[bold green]Generated {len(generated)} files![/]")

    console.print(f"Output directory: {output_dir}")
    db.close()

    if all_errors:
        sys.exit(1)


def _load_analysis(db: Database, project_id: int) -> AnalysisResult | None:
    """Load the most recent analysis result from cache.

    Returns None if no analysis has been run. Raises AnalysisError
    if the cached data exists but is corrupt.
    """
    rows = db.conn.execute(
        "SELECT result_json FROM analysis_cache "
        "WHERE project_id = ? AND analyzer_name = 'full_analysis' "
        "ORDER BY created_at DESC LIMIT 1",
        (project_id,),
    ).fetchone()

    if rows is None:
        return None

    try:
        data = json.loads(rows["result_json"])
        return AnalysisResult.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as e:
        raise AnalysisError(
            f"Cached analysis is corrupt and cannot be loaded: {e}\n"
            f"Run 'teach analyze' again to regenerate."
        ) from e
