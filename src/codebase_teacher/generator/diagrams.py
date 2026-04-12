"""Mermaid diagram generation from analysis results."""

from __future__ import annotations

from pathlib import Path

from codebase_teacher.core.exceptions import LLMError
from codebase_teacher.llm.provider import LLMProvider, Message
from codebase_teacher.storage.artifact_store import ArtifactStore
from codebase_teacher.storage.models import AnalysisResult


async def generate_architecture_diagram(
    provider: LLMProvider,
    analysis: AnalysisResult,
    store: ArtifactStore,
) -> Path:
    """Generate a Mermaid architecture diagram."""
    messages = [
        Message(
            role="system",
            content=(
                "You are generating a Mermaid diagram showing the high-level architecture "
                "of a software system. Use a flowchart (graph TD) or C4-style diagram. "
                "Keep it readable — no more than 15 nodes. Group related components. "
                "Output ONLY the Mermaid diagram code, nothing else."
            ),
        ),
        Message(
            role="user",
            content=(
                f"Generate a Mermaid architecture diagram for this system.\n\n"
                f"Project overview:\n{analysis.project_summary}\n\n"
                f"Modules:\n{_format_modules(analysis.module_summaries)}\n\n"
                f"Infrastructure:\n{_format_infra(analysis.infrastructure)}\n\n"
                f"APIs:\n{_format_apis(analysis.api_endpoints)}"
            ),
        ),
    ]

    response = await provider.complete(messages)
    mermaid_code = _clean_mermaid(response.content)

    content = f"# Architecture Diagram\n\n```mermaid\n{mermaid_code}\n```\n"
    return store.write("diagrams", "architecture.md", content)


async def generate_data_flow_diagram(
    provider: LLMProvider,
    analysis: AnalysisResult,
    store: ArtifactStore,
) -> Path:
    """Generate a Mermaid data flow diagram."""
    # If we have data flows with pre-generated diagrams, use those
    if analysis.data_flows:
        diagrams: list[str] = []
        for flow in analysis.data_flows:
            if flow.mermaid_diagram:
                diagrams.append(
                    f"## {flow.name}\n\n```mermaid\n{flow.mermaid_diagram}\n```"
                )
            else:
                diagrams.append(
                    f"## {flow.name}\n\n"
                    f"Entry: {', '.join(flow.entry_points)}\n"
                    f"Steps: {' -> '.join(flow.steps)}\n"
                    f"Output: {', '.join(flow.outputs)}"
                )
        content = "# Data Flow Diagrams\n\n" + "\n\n".join(diagrams) + "\n"
        return store.write("diagrams", "data-flow.md", content)

    # Otherwise, generate from scratch
    messages = [
        Message(
            role="system",
            content=(
                "You are generating Mermaid sequence diagrams showing data flows through "
                "a software system. Show how requests/data enter, get processed, and exit. "
                "Output ONLY Mermaid diagram code."
            ),
        ),
        Message(
            role="user",
            content=(
                f"Generate data flow diagrams for this system.\n\n"
                f"Project: {analysis.project_summary}\n\n"
                f"Modules: {_format_modules(analysis.module_summaries)}"
            ),
        ),
    ]

    response = await provider.complete(messages)
    mermaid_code = _clean_mermaid(response.content)

    content = f"# Data Flow Diagram\n\n```mermaid\n{mermaid_code}\n```\n"
    return store.write("diagrams", "data-flow.md", content)


async def generate_all_diagrams(
    provider: LLMProvider,
    analysis: AnalysisResult,
    store: ArtifactStore,
) -> tuple[list[Path], list[tuple[str, Exception]]]:
    """Generate all diagram files.

    Returns (successful_paths, errors) so a single diagram failure
    does not prevent the remaining diagrams from being generated.
    """
    generators = [
        ("architecture diagram", generate_architecture_diagram),
        ("data flow diagram", generate_data_flow_diagram),
    ]
    paths: list[Path] = []
    errors: list[tuple[str, Exception]] = []
    for name, gen_func in generators:
        try:
            paths.append(await gen_func(provider, analysis, store))
        except LLMError as e:
            errors.append((name, e))
    return paths, errors


def _clean_mermaid(text: str) -> str:
    """Extract mermaid code from LLM response, stripping fences if present."""
    import re
    match = re.search(r"```(?:mermaid)?\s*\n(.*?)\n```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def _format_modules(summaries: dict[str, str]) -> str:
    if not summaries:
        return "None"
    return "\n".join(f"- {path}: {summary[:200]}" for path, summary in summaries.items())


def _format_infra(components: list) -> str:
    if not components:
        return "None"
    return "\n".join(
        f"- {c.technology}: {c.usage}" if hasattr(c, "technology")
        else f"- {c.get('technology', '')}: {c.get('usage', '')}"
        for c in components
    )


def _format_apis(endpoints: list) -> str:
    if not endpoints:
        return "None"
    return "\n".join(
        f"- {e.method} {e.path}" if hasattr(e, "method")
        else f"- {e.get('method', '')} {e.get('path', '')}"
        for e in endpoints
    )
