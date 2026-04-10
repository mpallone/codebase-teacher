"""Provider factory — creates the right LLM provider from settings.

Lazy imports so litellm isn't required when using the Claude Code provider.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codebase_teacher.core.config import Settings
    from codebase_teacher.llm.provider import LLMProvider


def create_provider(settings: Settings) -> LLMProvider:
    """Create the appropriate LLM provider based on settings.provider."""
    if settings.provider == "claude-code":
        from codebase_teacher.llm.cli_provider import ClaudeCodeProvider

        return ClaudeCodeProvider(max_tokens=settings.max_tokens)
    elif settings.provider == "litellm":
        from codebase_teacher.llm.litellm_adapter import LiteLLMProvider

        return LiteLLMProvider(model=settings.model, max_tokens=settings.max_tokens)
    else:
        raise ValueError(
            f"Unknown provider: {settings.provider!r}. "
            f"Supported: claude-code, litellm"
        )
