"""Trace data flows through the codebase using LLM analysis.

This is the most LLM-intensive analyzer. It uses module summaries and
API/infra inventories to identify how data moves through the system.
"""

from __future__ import annotations

from codebase_teacher.llm.prompt_registry import PROMPTS, with_learner_context
from codebase_teacher.llm.provider import LLMProvider, Message
from codebase_teacher.llm.structured import complete_and_parse_list
from codebase_teacher.storage.models import DataFlow


async def trace_data_flows(
    provider: LLMProvider,
    project_summary: str,
    module_summaries: dict[str, str],
    api_endpoints: list[dict],
    infrastructure: list[dict],
    learner_info: str = "",
) -> list[DataFlow]:
    """Trace major data flows through the system.

    Args:
        provider: LLM provider.
        project_summary: High-level project overview.
        module_summaries: Dict of {module_path: summary}.
        api_endpoints: Serialized API endpoint data.
        infrastructure: Serialized infrastructure component data.
        learner_info: Optional LEARNER-INFO.md text to prioritize in tracing.

    Returns:
        List of traced data flows with Mermaid diagrams.
    """
    summaries = _build_summaries_text(
        project_summary, module_summaries, api_endpoints, infrastructure
    )

    prompt = PROMPTS["trace_data_flow"]
    user_content = prompt.format_user(summaries=summaries)
    messages = [
        Message(role="system", content=prompt.format_system()),
        Message(role="user", content=with_learner_context(user_content, learner_info)),
    ]

    return await complete_and_parse_list(provider, messages, DataFlow)


def _build_summaries_text(
    project_summary: str,
    module_summaries: dict[str, str],
    api_endpoints: list[dict],
    infrastructure: list[dict],
) -> str:
    """Build the combined context for the data flow tracer."""
    parts = [f"## Project Overview\n{project_summary}"]

    if module_summaries:
        parts.append("## Module Summaries")
        for path, summary in module_summaries.items():
            parts.append(f"### {path}\n{summary}")

    if api_endpoints:
        parts.append("## API Endpoints")
        for ep in api_endpoints:
            parts.append(
                f"- {ep.get('method', 'GET')} {ep.get('path', '')} "
                f"-> {ep.get('handler', '')} ({ep.get('file', '')})"
            )

    if infrastructure:
        parts.append("## Infrastructure")
        for comp in infrastructure:
            parts.append(
                f"- {comp.get('technology', '')}: {comp.get('usage', '')}"
            )

    return "\n\n".join(parts)
