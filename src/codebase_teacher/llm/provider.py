"""LLM provider protocol and data models.

All modules depend on this protocol — never on a concrete adapter.
"""

from __future__ import annotations

from typing import AsyncIterator, Protocol

from pydantic import BaseModel


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
