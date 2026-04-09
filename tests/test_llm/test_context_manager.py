"""Tests for context window management."""

import pytest

from codebase_teacher.llm.context_manager import (
    ContextManager,
    FileSummary,
    ModuleSummary,
    ProjectSummary,
    estimate_tokens,
)


def test_estimate_tokens():
    """Test rough token estimation."""
    assert estimate_tokens("") == 0
    assert estimate_tokens("hello world") > 0
    # ~4 chars per token
    assert estimate_tokens("a" * 400) == 100


def test_context_manager_available_tokens(mock_provider):
    """Test token budget calculation."""
    cm = ContextManager(mock_provider)
    available = cm.available_tokens
    # Should be context_window - reserved (system + response)
    assert available == 100_000 - 4000 - 16384


def test_context_manager_available_tokens_custom_reservations(mock_provider):
    """Reserved budgets are configurable for non-default models."""
    cm = ContextManager(
        mock_provider,
        reserved_system=1000,
        reserved_response=2000,
    )
    assert cm.available_tokens == 100_000 - 1000 - 2000


def test_fits_in_context(mock_provider):
    """Test context size checking."""
    cm = ContextManager(mock_provider)
    assert cm.fits_in_context("short text")
    assert cm.fits_in_context("x" * 100)
    # Very large text should not fit
    assert not cm.fits_in_context("x" * 1_000_000)


@pytest.mark.asyncio
async def test_summarize_file(mock_provider):
    """Test file summarization."""
    cm = ContextManager(mock_provider)
    summary = await cm.summarize_file("test.py", "def hello(): pass")
    assert isinstance(summary, FileSummary)
    assert summary.path == "test.py"
    assert len(summary.summary) > 0


@pytest.mark.asyncio
async def test_summarize_file_caching(mock_provider):
    """Test that file summaries are cached."""
    cm = ContextManager(mock_provider)
    s1 = await cm.summarize_file("test.py", "def hello(): pass")
    s2 = await cm.summarize_file("test.py", "def hello(): pass")
    assert s1 is s2  # Same object, cached


@pytest.mark.asyncio
async def test_summarize_files_concurrent(mock_provider):
    """Test concurrent file summarization."""
    cm = ContextManager(mock_provider, max_concurrent=2)
    files = {
        "a.py": "def a(): pass",
        "b.py": "def b(): pass",
        "c.py": "def c(): pass",
    }
    summaries = await cm.summarize_files(files)
    assert len(summaries) == 3


def test_build_context(mock_provider):
    """Test building context with budget management."""
    cm = ContextManager(mock_provider)
    project = ProjectSummary(
        summary="A test project",
        module_summaries=[
            ModuleSummary(
                path="src",
                summary="Source module",
                file_summaries=[FileSummary(path="src/main.py", summary="Main file")],
            ),
        ],
    )
    context = cm.build_context(project)
    assert "A test project" in context


def test_build_context_with_focus(mock_provider):
    """Test building context focused on a specific module."""
    cm = ContextManager(mock_provider)
    project = ProjectSummary(
        summary="A test project",
        module_summaries=[
            ModuleSummary(path="src", summary="Source code"),
            ModuleSummary(path="tests", summary="Test code"),
        ],
    )
    context = cm.build_context(project, focus_module="src")
    assert "Source code" in context
