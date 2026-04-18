"""Tests for infrastructure detection.

Regression coverage for TODO #9: infrastructure detection returned 0 results
for httpbin despite a Dockerfile existing.  The fix uses the LLM as the
primary source of infra knowledge (via a strengthened prompt) and falls back
to minimal hint-based components — with no hardcoded domain knowledge — when
the LLM returns nothing or fails to parse.
"""

from __future__ import annotations

from typing import AsyncIterator

from codebase_teacher.analyzer.infra_detector import (
    _fallback_from_hints,
    detect_infrastructure,
)
from codebase_teacher.llm.provider import LLMResponse, Message, TokenUsage
from codebase_teacher.storage.models import InfraComponent


class _StubProvider:
    """Tiny LLM provider stub that returns a canned string."""

    def __init__(self, response: str = "[]") -> None:
        self._response = response
        self.calls: list[list[Message]] = []

    async def complete(
        self,
        messages: list[Message],
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format=None,
    ) -> LLMResponse:
        self.calls.append(messages)
        return LLMResponse(
            content=self._response,
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            model="stub",
        )

    async def stream(
        self, messages: list[Message], temperature: float | None = None
    ) -> AsyncIterator[str]:
        self.calls.append(messages)
        yield self._response

    @property
    def context_window(self) -> int:
        return 100_000

    @property
    def max_tokens(self) -> int:
        return 16_384

    @property
    def temperature(self) -> float:
        return 0.3

    @property
    def model_name(self) -> str:
        return "stub"


# --- _fallback_from_hints ---


def test_fallback_produces_minimal_components():
    """Each hint becomes an InfraComponent with only technology populated."""
    hints = ["Docker (containerization)", "Redis (cache/store)"]
    result = _fallback_from_hints(hints)
    assert len(result) == 2

    for comp in result:
        # No hardcoded domain knowledge — explanation is empty.
        assert comp.explanation == ""
        assert comp.type == ""
        assert comp.usage == "Detected by repository scanning."

    techs = [c.technology for c in result]
    assert techs == ["Docker (containerization)", "Redis (cache/store)"]


def test_fallback_empty_for_no_hints():
    assert _fallback_from_hints([]) == []


# --- detect_infrastructure (integration) ---


async def test_detect_infrastructure_returns_llm_result_on_success():
    """When the LLM returns valid components, they pass through as-is."""
    llm_response = (
        '[{"type": "container", "technology": "Docker", '
        '"explanation": "Containerizes the app", '
        '"usage": "Dockerfile present", "config": "EXPOSE 80"}]'
    )
    provider = _StubProvider(response=llm_response)
    result = await detect_infrastructure(
        provider,
        {"Dockerfile": "FROM python:3.11\n"},
        infra_hints=["Docker (containerization)"],
    )
    assert len(result) == 1
    assert result[0].technology == "Docker"
    assert result[0].explanation == "Containerizes the app"


async def test_detect_infrastructure_falls_back_when_llm_returns_empty():
    """Regression (TODO #9): Docker hint must survive even if LLM returns []."""
    provider = _StubProvider(response="[]")
    result = await detect_infrastructure(
        provider,
        {"Dockerfile": "FROM python:3.11\nCMD gunicorn httpbin:app\n"},
        infra_hints=["Docker (containerization)"],
    )
    assert len(result) == 1
    assert result[0].technology == "Docker (containerization)"
    # Fallback components have no hardcoded explanation.
    assert result[0].explanation == ""
    assert result[0].usage == "Detected by repository scanning."


async def test_detect_infrastructure_falls_back_on_parse_failure():
    """If the LLM returns unparseable text, fallback components are used."""
    provider = _StubProvider(response="not valid json at all")
    result = await detect_infrastructure(
        provider,
        {"Dockerfile": "FROM alpine\n"},
        infra_hints=["Docker (containerization)"],
    )
    assert len(result) == 1
    assert result[0].technology == "Docker (containerization)"


async def test_detect_infrastructure_no_files_no_hints_returns_empty():
    provider = _StubProvider()
    result = await detect_infrastructure(provider, {}, infra_hints=[])
    assert result == []
    # LLM should not be called when there is nothing to analyze.
    assert provider.calls == []


async def test_detect_infrastructure_hints_only_no_files():
    """Hints but no files — return fallback without calling LLM."""
    provider = _StubProvider()
    result = await detect_infrastructure(
        provider,
        {},
        infra_hints=["Docker (containerization)"],
    )
    assert len(result) == 1
    assert result[0].technology == "Docker (containerization)"
    # LLM should not be called when no files were provided.
    assert provider.calls == []


async def test_detect_infrastructure_prompt_mentions_containers():
    """The strengthened prompt must cover containers/IaC, not just databases."""
    provider = _StubProvider(response="[]")
    await detect_infrastructure(
        provider,
        {"Dockerfile": "FROM python:3.11\n"},
        infra_hints=["Docker (containerization)"],
    )
    assert provider.calls, "expected at least one LLM call"
    system_content = provider.calls[0][0].content.lower()
    assert "docker" in system_content
    assert "container" in system_content
    assert "terraform" in system_content
    user_content = provider.calls[0][1].content
    assert "Infrastructure hints from dependency analysis" in user_content
    assert "Docker (containerization)" in user_content


async def test_detect_infrastructure_llm_result_with_multiple_hints():
    """LLM success with multiple hints — all LLM components returned."""
    llm_response = (
        '[{"type": "container", "technology": "Docker", '
        '"explanation": "Docker containers", "usage": "Dockerfile", "config": ""},'
        '{"type": "cache", "technology": "Redis", '
        '"explanation": "In-memory cache", "usage": "Used for sessions", "config": ""}]'
    )
    provider = _StubProvider(response=llm_response)
    result = await detect_infrastructure(
        provider,
        {"Dockerfile": "FROM python:3.11\n", "app.py": "import redis\n"},
        infra_hints=["Docker (containerization)", "Redis (cache/store)"],
    )
    assert len(result) == 2
    techs = {c.technology for c in result}
    assert techs == {"Docker", "Redis"}
    # All components have LLM-written explanations, not empty strings.
    for comp in result:
        assert comp.explanation != ""


async def test_detect_infrastructure_threads_learner_info():
    """learner_info must reach the user message as a preamble."""
    provider = _StubProvider(response="[]")
    await detect_infrastructure(
        provider,
        {"Dockerfile": "FROM python:3.11\n"},
        infra_hints=["Docker (containerization)"],
        learner_info="Focus on Kafka; treat containers as supporting context.",
    )
    assert provider.calls
    user_content = provider.calls[0][1].content
    assert "Learner Context" in user_content
    assert "Focus on Kafka" in user_content


async def test_detect_infrastructure_no_learner_info_no_preamble():
    """Default empty learner_info leaves the prompt untouched."""
    provider = _StubProvider(response="[]")
    await detect_infrastructure(
        provider,
        {"Dockerfile": "FROM python:3.11\n"},
        infra_hints=["Docker (containerization)"],
    )
    assert provider.calls
    user_content = provider.calls[0][1].content
    assert "Learner Context" not in user_content


async def test_detect_infrastructure_no_hardcoded_descriptions_in_fallback():
    """Fallback must contain zero hardcoded domain knowledge."""
    provider = _StubProvider(response="[]")
    result = await detect_infrastructure(
        provider,
        {"main.tf": "resource \"aws_instance\" \"web\" {}\n"},
        infra_hints=[
            "Terraform (infrastructure as code)",
            "Docker (containerization)",
            "SomeNewTech2030",
        ],
    )
    assert len(result) == 3
    for comp in result:
        # No canned type, no canned explanation.
        assert comp.type == ""
        assert comp.explanation == ""
        assert comp.usage == "Detected by repository scanning."
