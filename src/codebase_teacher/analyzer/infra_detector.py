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

    Args:
        provider: LLM provider to use.
        file_contents: Dict of {relative_path: file_content} for relevant files.
        infra_hints: Pre-detected infrastructure hints from dependency scanning.

    Returns:
        List of detected infrastructure components.
    """
    if not file_contents:
        return []

    code_chunks = _build_code_chunks(file_contents, infra_hints)

    prompt = PROMPTS["detect_infrastructure"]
    messages = [
        Message(role="system", content=prompt.format_system()),
        Message(role="user", content=prompt.format_user(code_chunks=code_chunks)),
    ]

    response = await provider.complete(messages)
    try:
        return parse_model_list(response.content, InfraComponent)
    except Exception:
        return []


def _build_code_chunks(
    file_contents: dict[str, str],
    infra_hints: list[str] | None = None,
) -> str:
    """Format file contents and hints for inclusion in a prompt."""
    parts: list[str] = []

    if infra_hints:
        parts.append(
            "Infrastructure hints from dependency analysis:\n"
            + "\n".join(f"- {h}" for h in infra_hints)
        )

    for path, content in file_contents.items():
        parts.append(f"### File: {path}\n```\n{content}\n```")

    return "\n\n".join(parts)
