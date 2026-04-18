"""Structured output parsing — extract JSON/pydantic models from LLM responses."""

from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from codebase_teacher.core.exceptions import LLMResponseError
from codebase_teacher.llm.provider import LLMProvider, LLMResponse, Message

T = TypeVar("T", bound=BaseModel)


def extract_json(text: str) -> str:
    """Extract JSON from LLM response text.

    Handles cases where the LLM wraps JSON in markdown code fences.
    """
    # Try to find JSON in code fences first
    fence_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()

    # Try to find a JSON array or object directly
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        start = text.find(start_char)
        if start == -1:
            continue
        # Find the matching closing bracket
        depth = 0
        for i in range(start, len(text)):
            if text[i] == start_char:
                depth += 1
            elif text[i] == end_char:
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]

    return text.strip()


def parse_json_response(text: str) -> dict | list:
    """Parse JSON from an LLM response, handling common issues."""
    json_str = extract_json(text)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise LLMResponseError(f"Failed to parse JSON from LLM response: {e}\nRaw: {text[:500]}") from e


def parse_model(text: str, model_class: type[T]) -> T:
    """Parse an LLM response into a pydantic model."""
    data = parse_json_response(text)
    if not isinstance(data, dict):
        raise LLMResponseError(f"Expected JSON object, got {type(data).__name__}")
    try:
        return model_class.model_validate(data)
    except ValidationError as e:
        raise LLMResponseError(f"Failed to validate LLM response: {e}") from e


def parse_model_list(text: str, model_class: type[T]) -> list[T]:
    """Parse an LLM response into a list of pydantic models."""
    data = parse_json_response(text)
    if not isinstance(data, list):
        raise LLMResponseError(f"Expected JSON array, got {type(data).__name__}")
    try:
        return [model_class.model_validate(item) for item in data]
    except ValidationError as e:
        raise LLMResponseError(f"Failed to validate LLM response item: {e}") from e


async def complete_and_parse(
    provider: LLMProvider,
    messages: list[Message],
    model_class: type[T],
    retries: int = 2,
    temperature: float | None = None,
) -> T:
    """Send a completion request and parse the response into a pydantic model.

    Retries on parse failure with a lower temperature. ``temperature=None``
    resolves to ``provider.temperature``.
    """
    base_temp = provider.temperature if temperature is None else temperature
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        temp = base_temp if attempt == 0 else max(0.1, base_temp - 0.1 * attempt)
        response: LLMResponse = await provider.complete(
            messages, temperature=temp, response_format=model_class
        )
        try:
            return parse_model(response.content, model_class)
        except LLMResponseError as e:
            last_error = e
            continue

    raise last_error or LLMResponseError("Failed to parse LLM response after retries")


async def complete_and_parse_list(
    provider: LLMProvider,
    messages: list[Message],
    model_class: type[T],
    retries: int = 2,
    temperature: float | None = None,
) -> list[T]:
    """Send a completion request and parse the response into a list of pydantic models."""
    base_temp = provider.temperature if temperature is None else temperature
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        temp = base_temp if attempt == 0 else max(0.1, base_temp - 0.1 * attempt)
        response: LLMResponse = await provider.complete(
            messages, temperature=temp, response_format=model_class
        )
        try:
            return parse_model_list(response.content, model_class)
        except LLMResponseError as e:
            last_error = e
            continue

    raise last_error or LLMResponseError("Failed to parse LLM response after retries")
