"""CLI command: teach analyze <path> — run LLM-assisted code analysis."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from codebase_teacher.analyzer.api_detector import detect_apis, detect_apis_from_ast
from codebase_teacher.analyzer.code_parser import parse_codebase
from codebase_teacher.analyzer.flow_tracer import trace_data_flows
from codebase_teacher.analyzer.infra_detector import detect_infrastructure
from codebase_teacher.core.config import Settings
from codebase_teacher.core.exceptions import LearnerInfoTooLarge, LLMError
from codebase_teacher.core.results import FileFailure, PartialResult
from codebase_teacher.llm.context_manager import ContextManager
from codebase_teacher.llm.factory import create_provider
from codebase_teacher.scanner.dependency import detect_dependencies
from codebase_teacher.scanner.file_classifier import classify_file
from codebase_teacher.scanner.learner_info import learner_info_bytes, load_learner_info
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
    if ctx.obj.get("provider"):
        settings.provider = ctx.obj["provider"]
    if ctx.obj.get("model"):
        settings.model = ctx.obj["model"]

    console.print(f"\n[bold]Analyzing codebase:[/] {root}")
    console.print(f"[dim]Provider: {settings.provider}[/]")

    asyncio.run(_analyze_async(root, settings))


async def _analyze_async(root: Path, settings: Settings) -> None:
    db = Database(settings.db_path(root))
    project_id = db.get_or_create_project(str(root), root.name)

    try:
        learner_info = load_learner_info(root)
    except LearnerInfoTooLarge as e:
        console.print(f"[red bold]{e}[/]")
        db.close()
        sys.exit(1)
    learner_bytes = learner_info_bytes(root)
    if learner_info:
        console.print(
            f"[cyan]Using LEARNER-INFO.md ({len(learner_info)} chars) "
            f"to focus analysis.[/]"
        )

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

    # Check cache before spending LLM tokens
    content_hash, hash_failures = _compute_hash(source_files, root, learner_bytes)
    cached = db.get_cached_analysis(project_id, "full_analysis", content_hash)
    if cached:
        console.print("[green]Cache hit — skipping LLM analysis (source unchanged).[/]")
        db.close()
        return

    # Initialize LLM
    provider = create_provider(settings)
    ctx_manager = ContextManager(
        provider,
        max_concurrent=settings.max_concurrent_llm_calls,
        learner_info=learner_info,
    )

    result = AnalysisResult()
    all_failures: list[FileFailure] = list(hash_failures)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # Step 1: AST parsing (deterministic, no LLM)
        task = progress.add_task("Parsing code (AST)...", total=None)
        parse_result = parse_codebase(root, source_files, console=console)
        result.codebase_graph = parse_result.value
        all_failures.extend(parse_result.failures)
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
        file_read_result = _read_source_files(root, source_files)
        file_contents = file_read_result.value
        all_failures.extend(file_read_result.failures)

        try:
            summary_result = await ctx_manager.summarize_files(file_contents)
        except LLMError as e:
            progress.stop()
            console.print(
                f"\n[red bold]LLM error during file summarization:[/] {e}\n"
                f"[red]Analysis cannot continue without file summaries.[/]"
            )
            db.close()
            sys.exit(1)

        file_summaries = summary_result.value
        all_failures.extend(summary_result.failures)
        if summary_result.has_failures:
            console.print(
                f"  [yellow]Warning:[/] {len(summary_result.failures)} file(s) "
                f"could not be summarized"
            )
        result.file_summaries = {fs.path: fs.summary for fs in file_summaries}
        progress.update(task, completed=True, description="[green]File summaries complete")

        # Step 4: Module summarization (LLM)
        task = progress.add_task("Summarizing modules (LLM)...", total=None)
        modules = _group_by_module(file_summaries)
        module_summaries = []
        try:
            for module_path, mod_file_summaries in modules.items():
                ms = await ctx_manager.summarize_module(module_path, mod_file_summaries)
                module_summaries.append(ms)
        except LLMError as e:
            progress.stop()
            console.print(
                f"\n[red bold]LLM error during module summarization:[/] {e}\n"
                f"[red]Analysis cannot continue without module summaries.[/]"
            )
            db.close()
            sys.exit(1)
        result.module_summaries = {ms.path: ms.summary for ms in module_summaries}
        progress.update(task, completed=True, description="[green]Module summaries complete")

        # Step 5: Project summary (LLM)
        task = progress.add_task("Generating project summary (LLM)...", total=None)
        try:
            project_summary = await ctx_manager.summarize_project(module_summaries)
        except LLMError as e:
            progress.stop()
            console.print(
                f"\n[red bold]LLM error during project summarization:[/] {e}\n"
                f"[red]Analysis cannot continue without a project summary.[/]"
            )
            db.close()
            sys.exit(1)
        result.project_summary = project_summary.summary
        progress.update(task, completed=True, description="[green]Project summary complete")

        # Step 6: LLM-based API detection (for what AST missed)
        task = progress.add_task("Detecting APIs (LLM)...", total=None)
        try:
            llm_endpoints = await detect_apis(provider, file_contents)
        except LLMError as e:
            progress.stop()
            console.print(
                f"\n[red bold]LLM error during API detection:[/] {e}\n"
                f"[red]Analysis cannot continue.[/]"
            )
            db.close()
            sys.exit(1)
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
            **{f["file_path"]: _read_file_safe(root, f["file_path"]) for f in db.get_files_by_category(project_id, "config")},
            **{f["file_path"]: _read_file_safe(root, f["file_path"]) for f in db.get_files_by_category(project_id, "infra")},
        }
        # Fallback: scan root-level files through the existing classifier.
        # If `teach scan` wasn't run, the db lookups above return nothing and
        # files like Dockerfile would never reach the LLM.  Reuses
        # file_classifier's INFRA_PATTERNS / CONFIG_PATTERNS — no hardcoded
        # filename list here.  See TODO #9.
        for path in sorted(root.iterdir()):
            if not path.is_file():
                continue
            info = classify_file(path, root)
            if info.category in ("infra", "config") and info.path not in infra_files:
                content = _read_file_safe(root, info.path)
                if content:
                    infra_files[info.path] = content
        # Add a subset of source files too
        for path, content in list(file_contents.items())[:20]:
            infra_files[path] = content
        try:
            result.infrastructure = await detect_infrastructure(
                provider,
                infra_files,
                dep_report.infra_hints,
                learner_info=learner_info,
            )
        except LLMError as e:
            progress.stop()
            console.print(
                f"\n[red bold]LLM error during infrastructure detection:[/] {e}\n"
                f"[red]Analysis cannot continue.[/]"
            )
            db.close()
            sys.exit(1)
        progress.update(task, completed=True, description="[green]Infrastructure detection complete")

        # Step 8: Data flow tracing (LLM)
        task = progress.add_task("Tracing data flows (LLM)...", total=None)
        try:
            result.data_flows = await trace_data_flows(
                provider,
                result.project_summary,
                result.module_summaries,
                [ep.model_dump() for ep in result.api_endpoints],
                [comp.model_dump() for comp in result.infrastructure],
                learner_info=learner_info,
            )
        except LLMError as e:
            progress.stop()
            console.print(
                f"\n[red bold]LLM error during data flow tracing:[/] {e}\n"
                f"[red]Analysis cannot continue.[/]"
            )
            db.close()
            sys.exit(1)
        progress.update(task, completed=True, description="[green]Data flow tracing complete")

    # Cache the full analysis result
    result.learner_info = learner_info
    content_hash, _ = _compute_hash(source_files, root, learner_bytes)
    db.cache_analysis(
        project_id, "full_analysis", content_hash,
        result.model_dump(),
    )

    console.print(f"\n[bold green]Analysis complete![/]")
    console.print(f"  APIs: {len(result.api_endpoints)}")
    console.print(f"  Infrastructure: {len(result.infrastructure)}")
    console.print(f"  Data flows: {len(result.data_flows)}")

    if all_failures:
        console.print(
            f"\n[yellow bold]Warnings:[/] {len(all_failures)} file(s) "
            f"could not be fully processed:"
        )
        for f in all_failures:
            console.print(f"  [yellow]-[/] {f.file_path}: {f.error_type}: {f.message}")

    console.print(f"\nRun [bold]teach generate {root}[/] to produce documentation.")

    db.close()


def _read_source_files(root: Path, source_files: list[str]) -> PartialResult[dict[str, str]]:
    """Read source files into memory, collecting failures."""
    contents: dict[str, str] = {}
    failures: list[FileFailure] = []
    for rel_path in source_files:
        try:
            text = (root / rel_path).read_text(encoding="utf-8", errors="ignore")
        except OSError as e:
            failures.append(FileFailure(
                file_path=rel_path,
                error_type="OSError",
                message=str(e),
            ))
            continue
        if text:
            contents[rel_path] = text
    return PartialResult(value=contents, failures=failures)


def _read_file_safe(root: Path, rel_path: str) -> str:
    """Read a single file for infra detection context. Returns empty on failure.

    Used only for supplementary context (config/infra files), not for
    primary analysis input, so an empty fallback is acceptable here.
    """
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


def _compute_hash(
    source_files: list[str],
    root: Path,
    learner_info_bytes: bytes = b"",
) -> tuple[str, list[FileFailure]]:
    """Compute a hash of all source file contents for caching.

    Files that cannot be read are hashed as a sentinel so the hash
    changes if the file later becomes readable. LEARNER-INFO.md bytes
    are mixed in so edits to the learner's priorities invalidate the
    cached analysis.
    """
    h = hashlib.sha256()
    failures: list[FileFailure] = []
    for rel_path in sorted(source_files):
        try:
            content = (root / rel_path).read_bytes()
            h.update(content)
        except OSError as e:
            h.update(f"UNREADABLE:{rel_path}".encode())
            failures.append(FileFailure(
                file_path=rel_path,
                error_type="OSError",
                message=str(e),
            ))
    h.update(b"LEARNER-INFO:")
    h.update(learner_info_bytes)
    return h.hexdigest()[:16], failures
