"""Tests for the prompt registry helpers."""

from __future__ import annotations

from codebase_teacher.llm.prompt_registry import with_learner_context


def test_with_learner_context_empty_is_noop():
    base = "Summarize this file: ..."
    assert with_learner_context(base, "") is base
    assert with_learner_context(base, "   \n\t  ") is base


def test_with_learner_context_prepends_preamble():
    base = "Summarize this file: ..."
    learner = "I care about module X."
    out = with_learner_context(base, learner)

    assert out != base
    assert out.endswith(base)
    assert "Learner Context" in out
    assert "module X" in out


def test_with_learner_context_strips_whitespace():
    base = "Body"
    out = with_learner_context(base, "\n\n  Focus on ingestion.  \n")
    assert "Focus on ingestion." in out
    # No leading/trailing whitespace wrapping the learner text.
    assert "  Focus on ingestion." not in out
