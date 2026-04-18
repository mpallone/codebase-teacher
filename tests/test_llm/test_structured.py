"""Tests for structured output parsing."""

from typing import AsyncIterator

import pytest
from pydantic import BaseModel

from codebase_teacher.llm.provider import LLMResponse, Message, TokenUsage
from codebase_teacher.llm.structured import (
    complete_and_parse_list,
    extract_json,
    parse_json_response,
    parse_model,
    parse_model_list,
)
from codebase_teacher.core.exceptions import LLMResponseError


class SampleModel(BaseModel):
    name: str
    value: int


def test_extract_json_from_code_fence():
    text = '```json\n{"name": "test", "value": 42}\n```'
    result = extract_json(text)
    assert result == '{"name": "test", "value": 42}'


def test_extract_json_bare():
    text = '{"name": "test", "value": 42}'
    result = extract_json(text)
    assert result == '{"name": "test", "value": 42}'


def test_extract_json_with_surrounding_text():
    text = 'Here is the result:\n{"name": "test", "value": 42}\nDone.'
    result = extract_json(text)
    assert result == '{"name": "test", "value": 42}'


def test_extract_json_array():
    text = '[{"name": "a", "value": 1}, {"name": "b", "value": 2}]'
    result = extract_json(text)
    assert result == text


def test_parse_json_response_valid():
    result = parse_json_response('{"key": "value"}')
    assert result == {"key": "value"}


def test_parse_json_response_invalid():
    with pytest.raises(LLMResponseError):
        parse_json_response("this is not json at all")


def test_parse_model():
    text = '{"name": "test", "value": 42}'
    result = parse_model(text, SampleModel)
    assert result.name == "test"
    assert result.value == 42


def test_parse_model_list():
    text = '[{"name": "a", "value": 1}, {"name": "b", "value": 2}]'
    result = parse_model_list(text, SampleModel)
    assert len(result) == 2
    assert result[0].name == "a"
    assert result[1].value == 2


def test_parse_model_invalid_data():
    with pytest.raises(LLMResponseError):
        parse_model('{"wrong_field": "test"}', SampleModel)


def test_parse_model_from_code_fence():
    text = '```json\n{"name": "fenced", "value": 99}\n```'
    result = parse_model(text, SampleModel)
    assert result.name == "fenced"
    assert result.value == 99


class _RecordingProvider:
    """Provider stub that records the temperature of every complete() call."""

    def __init__(self, response: str, temperature: float = 0.7):
        self._response = response
        self._temperature = temperature
        self.temperatures_seen: list[float | None] = []

    async def complete(
        self,
        messages: list[Message],
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format=None,
    ) -> LLMResponse:
        self.temperatures_seen.append(temperature)
        return LLMResponse(
            content=self._response,
            usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            model="recording",
        )

    async def stream(
        self, messages: list[Message], temperature: float | None = None
    ) -> AsyncIterator[str]:
        yield self._response

    @property
    def context_window(self) -> int:
        return 100_000

    @property
    def max_tokens(self) -> int:
        return 16_384

    @property
    def temperature(self) -> float:
        return self._temperature

    @property
    def model_name(self) -> str:
        return "recording"


@pytest.mark.asyncio
async def test_complete_and_parse_list_resolves_none_to_provider_temperature():
    """temperature=None must resolve to provider.temperature, with retry reduction."""
    # Always-failing response so we exhaust retries and observe the temperature
    # sequence across attempts.
    provider = _RecordingProvider(response="not valid json", temperature=0.7)

    with pytest.raises(LLMResponseError):
        await complete_and_parse_list(
            provider, [Message(role="user", content="x")], SampleModel
        )

    # 3 attempts: base 0.7, then 0.7 - 0.1*1 = 0.6, then 0.7 - 0.1*2 = 0.5
    assert provider.temperatures_seen == [0.7, pytest.approx(0.6), pytest.approx(0.5)]


@pytest.mark.asyncio
async def test_complete_and_parse_list_explicit_temperature_overrides_provider():
    """An explicit temperature kwarg must override provider.temperature."""
    provider = _RecordingProvider(response="not valid json", temperature=0.7)

    with pytest.raises(LLMResponseError):
        await complete_and_parse_list(
            provider,
            [Message(role="user", content="x")],
            SampleModel,
            temperature=0.4,
        )

    # Base 0.4, then 0.4 - 0.1 = 0.3, then 0.4 - 0.2 = 0.2
    assert provider.temperatures_seen == [0.4, pytest.approx(0.3), pytest.approx(0.2)]
