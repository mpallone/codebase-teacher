"""Detect infrastructure components using LLM analysis."""

from __future__ import annotations

from codebase_teacher.llm.prompt_registry import PROMPTS
from codebase_teacher.llm.provider import LLMProvider, Message
from codebase_teacher.llm.structured import parse_model_list
from codebase_teacher.storage.models import InfraComponent


async def detect_infrastructure(
    provider: LLMProvider,
    file_contents: dict[str, str],
    infra_hints: list[str] | None = None,
) -> list[InfraComponent]:
    """Detect infrastructure components from source code using LLM analysis.

    The LLM is the primary source of infrastructure knowledge.  Scanner
    ``infra_hints`` are passed into the prompt as confirmed context so the
    LLM can enrich them with details from the actual source files.

    If the LLM returns an empty list or fails to parse, a minimal fallback
    preserves each scanner hint as a bare :class:`InfraComponent` (technology
    name only, no hardcoded explanation).  The downstream doc-generation LLM
    fills in descriptions at ``teach generate`` time.

    Args:
        provider: LLM provider to use.
        file_contents: Dict of {relative_path: file_content} for relevant files.
        infra_hints: Pre-detected infrastructure hints from dependency scanning.

    Returns:
        List of detected infrastructure components.
    """
    hints = infra_hints or []

    if not file_contents and not hints:
        return []

    # No files to analyse — skip the LLM call but keep the scanner signals.
    if not file_contents:
        return _fallback_from_hints(hints)

    code_chunks = _build_code_chunks(file_contents, hints)

    prompt = PROMPTS["detect_infrastructure"]
    messages = [
        Message(role="system", content=prompt.format_system()),
        Message(role="user", content=prompt.format_user(code_chunks=code_chunks)),
    ]

    response = await provider.complete(messages)
    try:
        components = parse_model_list(response.content, InfraComponent)
    except Exception:
        components = []

    if components:
        return components

    # LLM returned nothing (or parse failed) — fall back to scanner hints
    # so the signal is not silently lost.
    return _fallback_from_hints(hints)


def _build_code_chunks(
    file_contents: dict[str, str],
    infra_hints: list[str] | None = None,
) -> str:
    """Format file contents and hints for inclusion in a prompt."""
    parts: list[str] = []

    if infra_hints:
        parts.append(
            "Infrastructure hints from dependency analysis (already confirmed "
            "by repo scanning — include each as a component in your response):\n"
            + "\n".join(f"- {h}" for h in infra_hints)
        )

    for path, content in file_contents.items():
        parts.append(f"### File: {path}\n```\n{content}\n```")

    return "\n\n".join(parts)


def _fallback_from_hints(hints: list[str]) -> list[InfraComponent]:
    """Build minimal InfraComponents from scanner hints.

    Contains **no hardcoded domain knowledge** — each hint becomes an
    :class:`InfraComponent` with only the technology name populated.  The
    doc-generation LLM (``teach generate``) is expected to fill in
    explanations from its own training data.
    """
    return [
        InfraComponent(
            technology=hint,
            usage="Detected by repository scanning.",
        )
        for hint in hints
    ]
