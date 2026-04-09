"""Concrete LLM provider using litellm.

This is the ONLY file that imports litellm. Swapping providers = replacing this file.
"""

from __future__ import annotations

from typing import AsyncIterator

import litellm
from pydantic import BaseModel

from codebase_teacher.core.exceptions import LLMError
from codebase_teacher.llm.provider import LLMResponse, Message, TokenUsage

# Suppress litellm's verbose logging by default
litellm.suppress_debug_info = True


class LiteLLMProvider:
    """LLM provider backed by litellm."""

    def __init__(self, model: str, max_tokens: int = 16384):
        self._model = model
        self._max_tokens = max_tokens
        self._context_window: int | None = None

    async def complete(
        self,
        messages: list[Message],
        temperature: float = 0.3,
        max_tokens: int | None = None,
        response_format: type[BaseModel] | None = None,
    ) -> LLMResponse:
        kwargs: dict = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens or self._max_tokens,
        }
        if response_format is not None:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = await litellm.acompletion(**kwargs)
        except Exception as e:
            raise LLMError(f"LLM call failed: {e}") from e

        choice = response.choices[0]
        usage = response.usage or {}
        return LLMResponse(
            content=choice.message.content or "",
            usage=TokenUsage(
                prompt_tokens=getattr(usage, "prompt_tokens", 0),
                completion_tokens=getattr(usage, "completion_tokens", 0),
                total_tokens=getattr(usage, "total_tokens", 0),
            ),
            model=response.model or self._model,
        )

    async def stream(
        self,
        messages: list[Message],
        temperature: float = 0.3,
    ) -> AsyncIterator[str]:
        try:
            response = await litellm.acompletion(
                model=self._model,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                temperature=temperature,
                stream=True,
            )
            async for chunk in response:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content
        except Exception as e:
            raise LLMError(f"LLM streaming failed: {e}") from e

    @property
    def context_window(self) -> int:
        if self._context_window is None:
            try:
                self._context_window = litellm.get_max_tokens(self._model)
            except Exception:
                import logging
                logging.getLogger(__name__).warning(
                    "litellm does not recognize model %r; using fallback context_window=200_000. "
                    "If this model has a larger window, upgrade litellm.",
                    self._model,
                )
                self._context_window = 200_000
        return self._context_window

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    @property
    def model_name(self) -> str:
        return self._model
