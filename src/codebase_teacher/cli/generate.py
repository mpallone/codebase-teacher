"""CLI command: teach generate <path> — generate documentation and diagrams."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import click
from rich.console import Console

from codebase_teacher.core.config import Settings
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
    analysis = _load_analysis(db, project_id)
    if analysis is None:
        console.print("[red]No analysis data found. Run [bold]teach analyze[/] first.[/]")
        db.close()
        return

    # Set up LLM and artifact store
    provider = create_provider(settings)
    output_dir = settings.output_path(root)
    store = ArtifactStore(output_dir, db, project_id)

    generated: list[Path] = []

    if gen_type in ("all", "docs"):
        console.print("\n[bold cyan]Generating documentation...[/]")
        doc_paths = await generate_all_docs(provider, analysis, store)
        generated.extend(doc_paths)
        for p in doc_paths:
            console.print(f"  [green]Created:[/] {p.relative_to(root)}")

    if gen_type in ("all", "diagrams"):
        console.print("\n[bold cyan]Generating diagrams...[/]")
        diagram_paths = await generate_all_diagrams(provider, analysis, store)
        generated.extend(diagram_paths)
        for p in diagram_paths:
            console.print(f"  [green]Created:[/] {p.relative_to(root)}")

    console.print(f"\n[bold green]Generated {len(generated)} files![/]")
    console.print(f"Output directory: {output_dir}")
    db.close()


def _load_analysis(db: Database, project_id: int) -> AnalysisResult | None:
    """Load the most recent analysis result from cache."""
    # Get all cached analyses and find the full_analysis
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
    except Exception:
        return None
