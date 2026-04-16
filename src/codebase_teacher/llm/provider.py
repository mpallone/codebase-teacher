"""LLM provider protocol and data models.

All modules depend on this protocol — never on a concrete adapter.
"""

from __future__ import annotations

import asyncio
import os
from typing import AsyncIterator, Protocol

from pydantic import BaseModel
from rich.console import Console

from codebase_teacher.core.exceptions import LLMError

_console = Console()

DEFAULT_MAX_ATTEMPTS = int(os.environ.get("CODEBASE_TEACHER_LLM_MAX_ATTEMPTS", "3"))
DEFAULT_RETRY_BASE_DELAY = float(os.environ.get("CODEBASE_TEACHER_LLM_RETRY_DELAY", "2.0"))


class Message(BaseModel):
    """A single message in a conversation."""

    role: str  # "system" | "user" | "assistant"
    content: str


class TokenUsage(BaseModel):
    """Token usage for a single LLM call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LLMResponse(BaseModel):
    """Response from an LLM provider."""

    content: str
    usage: TokenUsage = TokenUsage()
    model: str = ""


class LLMProvider(Protocol):
    """Swappable LLM backend.

    Implement this protocol to add a new provider.
    Only litellm_adapter.py should import litellm directly.
    """

    async def complete(
        self,
        messages: list[Message],
        temperature: float = 0.3,
        max_tokens: int | None = None,
        response_format: type[BaseModel] | None = None,
    ) -> LLMResponse:
        """Send a completion request and return the full response."""
        ...

    async def stream(
        self,
        messages: list[Message],
        temperature: float = 0.3,
    ) -> AsyncIterator[str]:
        """Stream a completion response, yielding content chunks."""
        ...

    @property
    def context_window(self) -> int:
        """Maximum context window size in tokens for this model."""
        ...

    @property
    def max_tokens(self) -> int:
        """Configured maximum output tokens per completion."""
        ...

    @property
    def model_name(self) -> str:
        """Human-readable model identifier."""
        ...


async def complete_with_retry(
    provider: LLMProvider,
    messages: list[Message],
    *,
    label: str,
    temperature: float = 0.3,
    max_tokens: int | None = None,
    response_format: type[BaseModel] | None = None,
    attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_RETRY_BASE_DELAY,
) -> LLMResponse:
    """Call ``provider.complete`` with exponential-backoff retry on ``LLMError``.

    Transient claude-CLI failures (non-zero exit, parse errors) bubble up as
    ``LLMError``. A single failure loses the whole section, so retry up to
    ``attempts`` times with delays of ``base_delay * 2**i``. Each failed attempt
    logs the underlying error and prompt size so persistent failures are
    diagnosable. The last attempt's exception is re-raised.
    """
    prompt_bytes = sum(len(m.content) for m in messages)
    last_exc: LLMError | None = None

    for attempt in range(1, attempts + 1):
        try:
            return await provider.complete(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            )
        except LLMError as exc:
            last_exc = exc
            if attempt < attempts:
                delay = base_delay * (2 ** (attempt - 1))
                _console.print(
                    f"  [yellow]{label} failed (attempt {attempt}/{attempts}, "
                    f"prompt {prompt_bytes:,} bytes): {exc} — retrying in "
                    f"{delay:.0f}s[/yellow]"
                )
                await asyncio.sleep(delay)
            else:
                _console.print(
                    f"  [red]{label} failed (attempt {attempt}/{attempts}, "
                    f"prompt {prompt_bytes:,} bytes): {exc} — giving up[/red]"
                )

    assert last_exc is not None
    raise last_exc
