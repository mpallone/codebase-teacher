"""Documentation generation orchestrator.

Produces markdown documentation from analysis results using LLM + Jinja2 templates.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from rich.console import Console

from codebase_teacher.core.exceptions import LLMError
from codebase_teacher.llm.prompt_registry import PROMPTS
from codebase_teacher.llm.provider import LLMProvider, Message
from codebase_teacher.storage.artifact_store import ArtifactStore
from codebase_teacher.storage.models import AnalysisResult

console = Console()


TEMPLATE_DIR = Path(__file__).parent / "templates"


def _get_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape([]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


async def generate_overview_doc(
    provider: LLMProvider,
    analysis: AnalysisResult,
    store: ArtifactStore,
) -> Path:
    """Generate a friendly 'Start Here' overview document.

    This is the first thing a new developer should read — it answers what the
    codebase does, why it exists, and how it's laid out at a high level. It is
    deliberately kept short and skimmable so the reader can orient themselves
    before diving into the deeper architecture and API docs.
    """
    prompt = PROMPTS["generate_overview_doc"]
    messages = [
        Message(role="system", content=prompt.format_system()),
        Message(
            role="user",
            content=prompt.format_user(
                project_summary=analysis.project_summary or "No project summary available.",
                module_summaries=_format_module_summaries(analysis.module_summaries),
                infrastructure=_format_infrastructure(analysis.infrastructure),
                apis=_format_apis(analysis.api_endpoints),
                data_flows=_format_data_flows(analysis.data_flows),
            ),
        ),
    ]

    response = await provider.complete(messages)

    env = _get_jinja_env()
    template = env.get_template("doc_page.md.j2")
    content = template.render(
        title="Start Here",
        body=response.content,
    )

    return store.write("docs", "overview.md", content)


async def generate_architecture_doc(
    provider: LLMProvider,
    analysis: AnalysisResult,
    store: ArtifactStore,
) -> Path:
    """Generate the main architecture document."""
    prompt = PROMPTS["generate_architecture_doc"]
    messages = [
        Message(role="system", content=prompt.format_system()),
        Message(
            role="user",
            content=prompt.format_user(
                project_summary=analysis.project_summary,
                module_summaries=_format_module_summaries(analysis.module_summaries),
                data_flows=_format_data_flows(analysis.data_flows),
                infrastructure=_format_infrastructure(analysis.infrastructure),
                apis=_format_apis(analysis.api_endpoints),
            ),
        ),
    ]

    response = await provider.complete(messages)

    env = _get_jinja_env()
    template = env.get_template("doc_page.md.j2")
    content = template.render(
        title="Architecture Overview",
        body=response.content,
    )

    return store.write("docs", "architecture.md", content)


API_CHUNK_SIZE = int(os.environ.get("CODEBASE_TEACHER_API_CHUNK_SIZE", "10"))

# Pattern for counting `### ` headings the LLM is supposed to produce per
# endpoint. Used for per-chunk completeness validation.
_H3_PATTERN = re.compile(r"^###\s", re.MULTILINE)


async def generate_api_doc(
    provider: LLMProvider,
    analysis: AnalysisResult,
    store: ArtifactStore,
) -> Path:
    """Generate API reference documentation.

    For codebases with many endpoints (> API_CHUNK_SIZE), the generation
    is split into chunks so each LLM call covers a manageable subset.
    """
    if not analysis.api_endpoints:
        # Still write a doc noting no APIs were found
        env = _get_jinja_env()
        template = env.get_template("doc_page.md.j2")
        content = template.render(
            title="API Reference",
            body="No API endpoints were detected in this codebase.",
        )
        return store.write("docs", "api-reference.md", content)

    if len(analysis.api_endpoints) > API_CHUNK_SIZE:
        body = await _generate_api_doc_chunked(provider, analysis)
    else:
        body = await _generate_api_chunk_with_retry(
            provider,
            analysis.api_endpoints,
            chunk_index=1,
            chunk_total=1,
            data_flows_formatted=_format_data_flows(analysis.data_flows),
        )

    env = _get_jinja_env()
    template = env.get_template("doc_page.md.j2")
    content = template.render(title="API Reference", body=body)

    return store.write("docs", "api-reference.md", content)


async def _generate_api_doc_chunked(
    provider: LLMProvider,
    analysis: AnalysisResult,
) -> str:
    """Generate API docs in chunks for large endpoint sets."""
    endpoints = analysis.api_endpoints
    chunks = [
        endpoints[i : i + API_CHUNK_SIZE]
        for i in range(0, len(endpoints), API_CHUNK_SIZE)
    ]
    data_flows = _format_data_flows(analysis.data_flows)

    console.print(
        f"  API Reference: {len(endpoints)} endpoints in {len(chunks)} chunks"
    )

    parts: list[str] = []
    for idx, chunk in enumerate(chunks, 1):
        part = await _generate_api_chunk_with_retry(
            provider,
            chunk,
            chunk_index=idx,
            chunk_total=len(chunks),
            data_flows_formatted=data_flows,
        )
        parts.append(part)

    return "\n\n---\n\n".join(parts)


async def _generate_api_chunk_with_retry(
    provider: LLMProvider,
    chunk: list,
    chunk_index: int,
    chunk_total: int,
    data_flows_formatted: str,
) -> str:
    """Call the LLM for one API chunk, retry once if the output is under-produced.

    A response is "under-produced" if it is empty or contains fewer `### `
    headings than half of the chunk's endpoint count. Prints per-chunk
    progress/warnings to the rich console so the user can see silent failures
    instead of losing endpoints to the void.
    """
    prompt = PROMPTS["generate_api_doc"]
    apis_formatted = _format_apis(chunk)
    expected = len(chunk)
    threshold = max(1, expected // 2)

    def _build_messages() -> list[Message]:
        return [
            Message(role="system", content=prompt.format_system()),
            Message(
                role="user",
                content=prompt.format_user(
                    apis=apis_formatted,
                    data_flows=data_flows_formatted,
                    chunk_index=chunk_index,
                    chunk_total=chunk_total,
                    endpoint_count=expected,
                ),
            ),
        ]

    response = await provider.complete(_build_messages())
    content = response.content or ""
    heading_count = len(_H3_PATTERN.findall(content))

    if heading_count < threshold:
        console.print(
            f"  [yellow]API chunk {chunk_index}/{chunk_total} "
            f"under-produced ({heading_count}/{expected} endpoints), "
            f"retrying[/yellow]"
        )
        retry = await provider.complete(_build_messages())
        retry_content = retry.content or ""
        retry_headings = len(_H3_PATTERN.findall(retry_content))
        if retry_headings > heading_count:
            content = retry_content
            heading_count = retry_headings

    if heading_count < threshold:
        console.print(
            f"  [red]API chunk {chunk_index}/{chunk_total} produced only "
            f"{heading_count}/{expected} endpoints after retry[/red]"
        )
    else:
        console.print(
            f"  [dim]API chunk {chunk_index}/{chunk_total}: "
            f"{heading_count} endpoints documented[/dim]"
        )

    return content


async def generate_infra_doc(
    provider: LLMProvider,
    analysis: AnalysisResult,
    store: ArtifactStore,
) -> Path:
    """Generate infrastructure documentation."""
    if not analysis.infrastructure:
        env = _get_jinja_env()
        template = env.get_template("doc_page.md.j2")
        content = template.render(
            title="Infrastructure",
            body="No infrastructure components were detected in this codebase.",
        )
        return store.write("docs", "infrastructure.md", content)

    prompt = PROMPTS["generate_infra_doc"]
    messages = [
        Message(role="system", content=prompt.format_system()),
        Message(
            role="user",
            content=prompt.format_user(
                infrastructure=_format_infrastructure(analysis.infrastructure),
            ),
        ),
    ]

    response = await provider.complete(messages)

    env = _get_jinja_env()
    template = env.get_template("doc_page.md.j2")
    content = template.render(
        title="Infrastructure",
        body=response.content,
    )

    return store.write("docs", "infrastructure.md", content)


async def generate_all_docs(
    provider: LLMProvider,
    analysis: AnalysisResult,
    store: ArtifactStore,
) -> tuple[list[Path], list[tuple[str, Exception]]]:
    """Generate all documentation files.

    Returns (successful_paths, errors) so a single document failure
    does not prevent the remaining documents from being generated.
    Order matters: the overview doc comes first so CLI output presents
    it as the intended starting point for new readers.
    """
    generators = [
        ("overview.md", generate_overview_doc),
        ("architecture.md", generate_architecture_doc),
        ("api-reference.md", generate_api_doc),
        ("infrastructure.md", generate_infra_doc),
    ]
    paths: list[Path] = []
    errors: list[tuple[str, Exception]] = []
    for name, gen_func in generators:
        try:
            paths.append(await gen_func(provider, analysis, store))
        except LLMError as e:
            errors.append((name, e))
    return paths, errors


# --- Formatting helpers ---


def _format_module_summaries(summaries: dict[str, str]) -> str:
    if not summaries:
        return "No module summaries available."
    return "\n\n".join(f"### {path}\n{summary}" for path, summary in summaries.items())


def _format_data_flows(flows: list) -> str:
    if not flows:
        return "No data flows detected."
    parts = []
    for flow in flows:
        if hasattr(flow, "model_dump"):
            flow = flow.model_dump()
        parts.append(
            f"**{flow.get('name', 'Unknown')}**\n"
            f"- Entry: {', '.join(flow.get('entry_points', []))}\n"
            f"- Steps: {' -> '.join(flow.get('steps', []))}\n"
            f"- Output: {', '.join(flow.get('outputs', []))}"
        )
    return "\n\n".join(parts)


def _format_apis(endpoints: list) -> str:
    if not endpoints:
        return "No API endpoints detected."
    parts = []
    for ep in endpoints:
        if hasattr(ep, "model_dump"):
            ep = ep.model_dump()
        parts.append(
            f"- {ep.get('method', 'GET')} {ep.get('path', '')} "
            f"-> {ep.get('handler', '')} ({ep.get('file', '')}): "
            f"{ep.get('description', '')}"
        )
    return "\n".join(parts)


def _format_infrastructure(components: list) -> str:
    if not components:
        return "No infrastructure components detected."
    parts = []
    for comp in components:
        if hasattr(comp, "model_dump"):
            comp = comp.model_dump()
        parts.append(
            f"**{comp.get('technology', 'Unknown')}** ({comp.get('type', '')})\n"
            f"- What: {comp.get('explanation', '')}\n"
            f"- Usage: {comp.get('usage', '')}\n"
            f"- Config: {comp.get('config', 'N/A')}"
        )
    return "\n\n".join(parts)
