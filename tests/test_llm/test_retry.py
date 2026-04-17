"""Tests for the complete_with_retry helper."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from codebase_teacher.core.exceptions import CLIProviderError, LLMError
from codebase_teacher.llm.provider import (
    LLMResponse,
    Message,
    TokenUsage,
    complete_with_retry,
)


class FlakyProvider:
    """Provider that fails N times before returning a successful response."""

    def __init__(self, failures: int, exc: Exception | None = None):
        self._remaining_failures = failures
        self._exc = exc or LLMError("claude CLI exited with code 1: ")
        self.call_count = 0

    async def complete(self, messages, **kwargs) -> LLMResponse:
        self.call_count += 1
        if self._remaining_failures > 0:
            self._remaining_failures -= 1
            raise self._exc
        return LLMResponse(
            content="ok",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            model="mock",
        )


@pytest.fixture(autouse=True)
def _patch_sleep():
    """Make sleep a no-op so tests run instantly."""
    with patch("codebase_teacher.llm.provider.asyncio.sleep", new=AsyncMock()) as m:
        yield m


@pytest.mark.asyncio
async def test_returns_first_response_when_no_failures():
    provider = FlakyProvider(failures=0)
    response = await complete_with_retry(
        provider, [Message(role="user", content="hi")], label="Test"
    )
    assert response.content == "ok"
    assert provider.call_count == 1


@pytest.mark.asyncio
async def test_retries_on_llm_error_then_succeeds(_patch_sleep):
    provider = FlakyProvider(failures=2)
    response = await complete_with_retry(
        provider,
        [Message(role="user", content="hi")],
        label="Infrastructure",
        attempts=3,
    )
    assert response.content == "ok"
    assert provider.call_count == 3
    # Two sleeps before the final successful attempt
    assert _patch_sleep.await_count == 2


@pytest.mark.asyncio
async def test_raises_last_exception_after_all_attempts_exhausted():
    provider = FlakyProvider(failures=5, exc=LLMError("persistent boom"))
    with pytest.raises(LLMError, match="persistent boom"):
        await complete_with_retry(
            provider,
            [Message(role="user", content="hi")],
            label="Test",
            attempts=3,
        )
    assert provider.call_count == 3


@pytest.mark.asyncio
async def test_exponential_backoff_delays(_patch_sleep):
    provider = FlakyProvider(failures=2)
    await complete_with_retry(
        provider,
        [Message(role="user", content="hi")],
        label="Test",
        attempts=3,
        base_delay=2.0,
    )
    # Delays should be 2s (after attempt 1) then 4s (after attempt 2)
    call_delays = [call.args[0] for call in _patch_sleep.await_args_list]
    assert call_delays == [2.0, 4.0]


@pytest.mark.asyncio
async def test_cli_provider_error_is_retried_as_llm_error_subclass():
    # CLIProviderError subclasses LLMError, so it should also be retried.
    provider = FlakyProvider(failures=1, exc=CLIProviderError("timeout"))
    response = await complete_with_retry(
        provider, [Message(role="user", content="hi")], label="Test", attempts=3
    )
    assert response.content == "ok"
    assert provider.call_count == 2


@pytest.mark.asyncio
async def test_single_attempt_does_not_retry():
    provider = FlakyProvider(failures=1)
    with pytest.raises(LLMError):
        await complete_with_retry(
            provider,
            [Message(role="user", content="hi")],
            label="Test",
            attempts=1,
        )
    assert provider.call_count == 1
