"""CLI command: teach analyze <path> — run LLM-assisted code analysis."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from codebase_teacher.analyzer.api_detector import detect_apis, detect_apis_from_ast
from codebase_teacher.analyzer.code_parser import parse_codebase
from codebase_teacher.analyzer.flow_tracer import trace_data_flows
from codebase_teacher.analyzer.infra_detector import detect_infrastructure
from codebase_teacher.core.config import Settings
from codebase_teacher.llm.context_manager import ContextManager
from codebase_teacher.llm.litellm_adapter import LiteLLMProvider
from codebase_teacher.scanner.dependency import detect_dependencies
from codebase_teacher.storage.database import Database
from codebase_teacher.storage.models import AnalysisResult

console = Console()


@click.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.pass_context
def analyze(ctx: click.Context, path: str) -> None:
    """Analyze a codebase using LLM-assisted code understanding."""
    root = Path(path)
    settings = Settings()
    if ctx.obj.get("model"):
        settings.model = ctx.obj["model"]

    console.print(f"\n[bold]Analyzing codebase:[/] {root}")
    console.print(f"[dim]Model: {settings.model}[/]")

    asyncio.run(_analyze_async(root, settings))


async def _analyze_async(root: Path, settings: Settings) -> None:
    db = Database(settings.db_path(root))
    project_id = db.get_or_create_project(str(root), root.name)

    # Check that scan has been run
    relevant_folders = db.get_relevant_folders(project_id)
    if not relevant_folders:
        console.print(
            "[yellow]No scan data found. Run [bold]teach scan[/] first, "
            "or using root directory.[/]"
        )
        relevant_folders = ["."]

    # Get source files from classification
    source_files_data = db.get_files_by_category(project_id, "source")
    source_files = [f["file_path"] for f in source_files_data]
    if not source_files:
        # Fall back: find Python files in relevant folders
        for folder_rel in relevant_folders:
            folder = root / folder_rel if folder_rel != "." else root
            for py_file in folder.rglob("*.py"):
                source_files.append(str(py_file.relative_to(root)))

    if not source_files:
        console.print("[red]No source files found to analyze.[/]")
        db.close()
        return

    console.print(f"[bold]Source files to analyze:[/] {len(source_files)}")

    # Initialize LLM
    provider = LiteLLMProvider(model=settings.model, max_tokens=settings.max_tokens)
    ctx_manager = ContextManager(provider, max_concurrent=settings.max_concurrent_llm_calls)

    result = AnalysisResult()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # Step 1: AST parsing (deterministic, no LLM)
        task = progress.add_task("Parsing code (AST)...", total=None)
        result.codebase_graph = parse_codebase(root, source_files, console=console)
        progress.update(task, completed=True, description="[green]AST parsing complete")

        console.print(
            f"  Found {len(result.codebase_graph.functions)} functions, "
            f"{len(result.codebase_graph.classes)} classes, "
            f"{len(result.codebase_graph.imports)} imports"
        )

        # Step 2: AST-based API detection (no LLM)
        task = progress.add_task("Detecting APIs from AST...", total=None)
        ast_endpoints = detect_apis_from_ast(
            result.codebase_graph.functions,
            result.codebase_graph.classes,
        )
        progress.update(task, completed=True, description="[green]AST API detection complete")

        # Step 3: File summarization (LLM)
        task = progress.add_task("Summarizing files (LLM)...", total=None)
        file_contents = _read_source_files(root, source_files)
        file_summaries = await ctx_manager.summarize_files(file_contents)
        result.file_summaries = {fs.path: fs.summary for fs in file_summaries}
        progress.update(task, completed=True, description="[green]File summaries complete")

        # Step 4: Module summarization (LLM)
        task = progress.add_task("Summarizing modules (LLM)...", total=None)
        modules = _group_by_module(file_summaries)
        module_summaries = []
        for module_path, mod_file_summaries in modules.items():
            ms = await ctx_manager.summarize_module(module_path, mod_file_summaries)
            module_summaries.append(ms)
        result.module_summaries = {ms.path: ms.summary for ms in module_summaries}
        progress.update(task, completed=True, description="[green]Module summaries complete")

        # Step 5: Project summary (LLM)
        task = progress.add_task("Generating project summary (LLM)...", total=None)
        project_summary = await ctx_manager.summarize_project(module_summaries)
        result.project_summary = project_summary.summary
        progress.update(task, completed=True, description="[green]Project summary complete")

        # Step 6: LLM-based API detection (for what AST missed)
        task = progress.add_task("Detecting APIs (LLM)...", total=None)
        llm_endpoints = await detect_apis(provider, file_contents)
        # Merge AST + LLM endpoints, dedup by handler name
        seen_handlers = {ep.handler for ep in ast_endpoints}
        result.api_endpoints = list(ast_endpoints)
        for ep in llm_endpoints:
            if ep.handler not in seen_handlers:
                result.api_endpoints.append(ep)
                seen_handlers.add(ep.handler)
        progress.update(task, completed=True, description="[green]API detection complete")

        # Step 7: Infrastructure detection (LLM)
        task = progress.add_task("Detecting infrastructure (LLM)...", total=None)
        dep_report = detect_dependencies(root)
        # Include config/infra files for infrastructure detection
        infra_files = {
            **{f["file_path"]: _read_file(root, f["file_path"]) for f in db.get_files_by_category(project_id, "config")},
            **{f["file_path"]: _read_file(root, f["file_path"]) for f in db.get_files_by_category(project_id, "infra")},
        }
        # Add a subset of source files too
        for path, content in list(file_contents.items())[:20]:
            infra_files[path] = content
        result.infrastructure = await detect_infrastructure(
            provider, infra_files, dep_report.infra_hints
        )
        progress.update(task, completed=True, description="[green]Infrastructure detection complete")

        # Step 8: Data flow tracing (LLM)
        task = progress.add_task("Tracing data flows (LLM)...", total=None)
        result.data_flows = await trace_data_flows(
            provider,
            result.project_summary,
            result.module_summaries,
            [ep.model_dump() for ep in result.api_endpoints],
            [comp.model_dump() for comp in result.infrastructure],
        )
        progress.update(task, completed=True, description="[green]Data flow tracing complete")

    # Cache the full analysis result
    content_hash = _compute_hash(source_files, root)
    db.cache_analysis(
        project_id, "full_analysis", content_hash,
        result.model_dump(),
    )

    console.print(f"\n[bold green]Analysis complete![/]")
    console.print(f"  APIs: {len(result.api_endpoints)}")
    console.print(f"  Infrastructure: {len(result.infrastructure)}")
    console.print(f"  Data flows: {len(result.data_flows)}")
    console.print(f"\nRun [bold]teach generate {root}[/] to produce documentation.")

    db.close()


def _read_source_files(root: Path, source_files: list[str]) -> dict[str, str]:
    """Read source files into memory."""
    contents: dict[str, str] = {}
    for rel_path in source_files:
        content = _read_file(root, rel_path)
        if content:
            contents[rel_path] = content
    return contents


def _read_file(root: Path, rel_path: str) -> str:
    """Read a single file, returning empty string on failure."""
    try:
        return (root / rel_path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _group_by_module(file_summaries: list) -> dict:
    """Group file summaries by their parent directory."""
    from collections import defaultdict
    modules: dict = defaultdict(list)
    for fs in file_summaries:
        parts = fs.path.split("/")
        module = parts[0] if len(parts) > 1 else "."
        modules[module].append(fs)
    return dict(modules)


def _compute_hash(source_files: list[str], root: Path) -> str:
    """Compute a hash of all source file contents for caching."""
    h = hashlib.sha256()
    for rel_path in sorted(source_files):
        try:
            content = (root / rel_path).read_bytes()
            h.update(content)
        except OSError:
            pass
    return h.hexdigest()[:16]
