"""Documentation generation orchestrator.

Produces markdown documentation from analysis results using LLM + Jinja2 templates.
"""

from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from codebase_teacher.llm.prompt_registry import PROMPTS
from codebase_teacher.llm.provider import LLMProvider, Message
from codebase_teacher.storage.artifact_store import ArtifactStore
from codebase_teacher.storage.models import AnalysisResult


TEMPLATE_DIR = Path(__file__).parent / "templates"


def _get_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape([]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


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


async def generate_api_doc(
    provider: LLMProvider,
    analysis: AnalysisResult,
    store: ArtifactStore,
) -> Path:
    """Generate API reference documentation."""
    if not analysis.api_endpoints:
        # Still write a doc noting no APIs were found
        env = _get_jinja_env()
        template = env.get_template("doc_page.md.j2")
        content = template.render(
            title="API Reference",
            body="No API endpoints were detected in this codebase.",
        )
        return store.write("docs", "api-reference.md", content)

    prompt = PROMPTS["generate_api_doc"]
    messages = [
        Message(role="system", content=prompt.format_system()),
        Message(
            role="user",
            content=prompt.format_user(
                apis=_format_apis(analysis.api_endpoints),
                data_flows=_format_data_flows(analysis.data_flows),
            ),
        ),
    ]

    response = await provider.complete(messages)

    env = _get_jinja_env()
    template = env.get_template("doc_page.md.j2")
    content = template.render(
        title="API Reference",
        body=response.content,
    )

    return store.write("docs", "api-reference.md", content)


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
) -> list[Path]:
    """Generate all documentation files."""
    paths: list[Path] = []
    paths.append(await generate_architecture_doc(provider, analysis, store))
    paths.append(await generate_api_doc(provider, analysis, store))
    paths.append(await generate_infra_doc(provider, analysis, store))
    return paths


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
