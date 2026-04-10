"""Tests for infrastructure detection.

Regression coverage for TODO #9: infrastructure detection returned 0 results
for httpbin despite a Dockerfile existing. The scanner correctly reported
``Docker (containerization)`` as an infra hint but the analyze step's LLM
call produced an empty list, so ``infrastructure.md`` was empty.

The fix guarantees scanner-confirmed hints are always reflected in the
result, even if the LLM returns nothing or fails to parse.
"""

from __future__ import annotations

from typing import AsyncIterator

from codebase_teacher.analyzer.infra_detector import (
    _baseline_from_hints,
    _merge_components,
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
        temperature: float = 0.3,
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
        self, messages: list[Message], temperature: float = 0.3
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
    def model_name(self) -> str:
        return "stub"


# --- _baseline_from_hints ---


def test_baseline_from_docker_hint():
    """Docker hint from the scanner should always produce a component."""
    baseline = _baseline_from_hints(["Docker (containerization)"])
    assert len(baseline) == 1
    assert baseline[0].technology == "Docker"
    assert baseline[0].type == "container"
    assert "container" in baseline[0].explanation.lower()


def test_baseline_from_multiple_hints():
    """Multiple hints should produce one component each."""
    baseline = _baseline_from_hints(
        [
            "Docker (containerization)",
            "Redis (cache/store)",
            "PostgreSQL",
        ]
    )
    techs = {c.technology for c in baseline}
    assert "Docker" in techs
    assert "Redis" in techs
    assert "PostgreSQL" in techs


def test_baseline_dedupes_hints():
    """Duplicate hints shouldn't produce duplicate components."""
    baseline = _baseline_from_hints(
        ["Docker (containerization)", "Docker (containerization)"]
    )
    assert len(baseline) == 1
    assert baseline[0].technology == "Docker"


def test_baseline_empty_for_empty_hints():
    assert _baseline_from_hints([]) == []


def test_baseline_preserves_unknown_hints():
    """Unknown hints still produce components so nothing is silently lost."""
    baseline = _baseline_from_hints(["SomeCustomThing (widget)"])
    assert len(baseline) == 1
    assert baseline[0].technology == "SomeCustomThing (widget)"
    assert baseline[0].type == "other"


def test_baseline_matches_terraform_hint():
    baseline = _baseline_from_hints(["Terraform (infrastructure as code)"])
    assert len(baseline) == 1
    assert baseline[0].technology == "Terraform"
    assert baseline[0].type == "iac"


# --- _merge_components ---


def test_merge_llm_replaces_matching_baseline():
    """LLM output with richer details should replace the baseline entry."""
    baseline = [
        InfraComponent(
            type="container",
            technology="Docker",
            explanation="Docker packages apps into portable images.",
            usage="Dockerfile detected.",
        )
    ]
    llm = [
        InfraComponent(
            type="container",
            technology="Docker",
            explanation="Docker is used here for containerization.",
            usage="Dockerfile builds a Python 3.11 slim image running gunicorn.",
            config="EXPOSE 80, CMD gunicorn httpbin:app",
        )
    ]
    merged = _merge_components(baseline, llm)
    assert len(merged) == 1
    assert merged[0].usage.startswith("Dockerfile builds")
    assert "gunicorn" in merged[0].config


def test_merge_appends_new_llm_components():
    """LLM components the scanner didn't see should be appended."""
    baseline = [
        InfraComponent(type="container", technology="Docker", explanation="", usage="")
    ]
    llm = [
        InfraComponent(
            type="database",
            technology="PostgreSQL",
            explanation="Relational DB",
            usage="Stores users",
        )
    ]
    merged = _merge_components(baseline, llm)
    assert len(merged) == 2
    techs = {c.technology for c in merged}
    assert techs == {"Docker", "PostgreSQL"}


def test_merge_empty_llm_preserves_baseline():
    baseline = [
        InfraComponent(type="container", technology="Docker", explanation="", usage="")
    ]
    merged = _merge_components(baseline, [])
    assert len(merged) == 1
    assert merged[0].technology == "Docker"


def test_merge_substring_match_is_deduped():
    """`Docker` and `Docker (containerization)` should be treated as the same tech."""
    baseline = [
        InfraComponent(type="container", technology="Docker", explanation="", usage="")
    ]
    llm = [
        InfraComponent(
            type="container",
            technology="Docker (containerization)",
            explanation="rich",
            usage="rich usage",
        )
    ]
    merged = _merge_components(baseline, llm)
    assert len(merged) == 1
    assert merged[0].usage == "rich usage"


def test_merge_generic_sql_does_not_replace_postgresql():
    """Regression: a generic LLM 'SQL' entry must not replace a specific baseline.

    The original substring-based dedup collapsed 'SQL' into 'PostgreSQL' because
    'sql' is a substring of 'postgresql', silently downgrading the richer
    baseline. Normalized exact-match dedup should keep them distinct.
    """
    baseline = [
        InfraComponent(
            type="database",
            technology="PostgreSQL",
            explanation="Rich baseline explanation",
            usage="Baseline usage",
        )
    ]
    llm = [
        InfraComponent(
            type="database",
            technology="SQL",
            explanation="Generic SQL",
            usage="generic",
        )
    ]
    merged = _merge_components(baseline, llm)
    techs = {c.technology for c in merged}
    assert "PostgreSQL" in techs
    assert "SQL" in techs
    # The baseline PostgreSQL entry must still be present unchanged.
    postgres = next(c for c in merged if c.technology == "PostgreSQL")
    assert postgres.explanation == "Rich baseline explanation"


def test_merge_docker_does_not_replace_kubernetes():
    """Two distinct container-related technologies should stay separate."""
    baseline = [
        InfraComponent(
            type="orchestration",
            technology="Kubernetes",
            explanation="K8s",
            usage="",
        )
    ]
    llm = [
        InfraComponent(
            type="container",
            technology="Docker",
            explanation="docker",
            usage="",
        )
    ]
    merged = _merge_components(baseline, llm)
    techs = {c.technology for c in merged}
    assert techs == {"Kubernetes", "Docker"}


# --- detect_infrastructure integration ---


async def test_detect_infrastructure_preserves_docker_hint_when_llm_returns_empty():
    """Regression: Docker hint must survive even if LLM returns [] (httpbin bug)."""
    # LLM returns an empty array — the old behaviour would drop Docker entirely.
    provider = _StubProvider(response="[]")
    file_contents = {
        "Dockerfile": "FROM python:3.11\nCMD gunicorn httpbin:app\n",
    }
    result = await detect_infrastructure(
        provider,
        file_contents,
        infra_hints=["Docker (containerization)"],
    )
    assert len(result) == 1
    assert result[0].technology == "Docker"
    assert result[0].type == "container"


async def test_detect_infrastructure_preserves_hint_when_llm_parse_fails():
    """If the LLM returns unparseable text, the hint-based baseline is used."""
    provider = _StubProvider(response="not valid json at all")
    result = await detect_infrastructure(
        provider,
        {"Dockerfile": "FROM alpine\n"},
        infra_hints=["Docker (containerization)"],
    )
    assert len(result) == 1
    assert result[0].technology == "Docker"


async def test_detect_infrastructure_merges_llm_and_hints():
    """LLM-found infra is merged with hint-based baseline, no duplicates."""
    llm_response = (
        '[{"type": "container", "technology": "Docker", '
        '"explanation": "Containerizes the app", '
        '"usage": "Dockerfile builds a python image", '
        '"config": "EXPOSE 80"}, '
        '{"type": "database", "technology": "PostgreSQL", '
        '"explanation": "Relational DB", '
        '"usage": "Stores data", "config": ""}]'
    )
    provider = _StubProvider(response=llm_response)
    result = await detect_infrastructure(
        provider,
        {"Dockerfile": "FROM python:3.11\n"},
        infra_hints=["Docker (containerization)"],
    )
    techs = {c.technology for c in result}
    assert "Docker" in techs
    assert "PostgreSQL" in techs
    # Exactly 2 — the baseline Docker entry was replaced by the richer LLM one.
    assert len(result) == 2
    docker = next(c for c in result if c.technology == "Docker")
    assert "python image" in docker.usage


async def test_detect_infrastructure_no_files_no_hints_returns_empty():
    provider = _StubProvider()
    result = await detect_infrastructure(provider, {}, infra_hints=[])
    assert result == []
    # LLM should not be called when there is nothing to analyze.
    assert provider.calls == []


async def test_detect_infrastructure_hints_only_no_files():
    """If there are hints but no files to send to the LLM, we still return baseline."""
    provider = _StubProvider()
    result = await detect_infrastructure(
        provider,
        {},
        infra_hints=["Docker (containerization)"],
    )
    assert len(result) == 1
    assert result[0].technology == "Docker"
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
    # Regression: these categories were missing from the original prompt.
    assert "docker" in system_content
    assert "container" in system_content
    user_content = provider.calls[0][1].content
    # The hints block should be labelled as already-confirmed infrastructure.
    assert "Infrastructure hints from dependency analysis" in user_content
    assert "Docker (containerization)" in user_content
