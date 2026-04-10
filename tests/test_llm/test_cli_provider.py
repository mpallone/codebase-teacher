"""Tests for the Claude Code CLI provider."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codebase_teacher.core.exceptions import CLIProviderError, LLMError
from codebase_teacher.llm.provider import Message


SAMPLE_JSON_OUTPUT = json.dumps({
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "result": "This is the LLM response.",
    "usage": {
        "input_tokens": 100,
        "output_tokens": 25,
    },
    "total_cost_usd": 0.003,
    "modelUsage": {
        "claude-sonnet-4-6": {
            "contextWindow": 200000,
            "maxOutputTokens": 32000,
        }
    },
})


def _make_process(stdout: str = SAMPLE_JSON_OUTPUT, stderr: str = "", returncode: int = 0):
    """Create a mock subprocess."""
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(
        stdout.encode(),
        stderr.encode(),
    ))
    proc.returncode = returncode
    return proc


@pytest.fixture
def provider():
    """Create a ClaudeCodeProvider with mocked shutil.which."""
    with patch("codebase_teacher.llm.cli_provider.shutil.which", return_value="/usr/bin/claude"):
        from codebase_teacher.llm.cli_provider import ClaudeCodeProvider
        return ClaudeCodeProvider(max_tokens=8192)


class TestClaudeCodeProviderInit:
    def test_raises_when_claude_not_found(self):
        with patch("codebase_teacher.llm.cli_provider.shutil.which", return_value=None):
            from codebase_teacher.llm.cli_provider import ClaudeCodeProvider
            with pytest.raises(CLIProviderError, match="claude CLI not found"):
                ClaudeCodeProvider()

    def test_init_succeeds_when_claude_found(self):
        with patch("codebase_teacher.llm.cli_provider.shutil.which", return_value="/usr/bin/claude"):
            from codebase_teacher.llm.cli_provider import ClaudeCodeProvider
            p = ClaudeCodeProvider()
            assert p.model_name == "claude-code"
            assert p.max_tokens == 16384


class TestBuildPrompt:
    def test_system_and_user_messages(self, provider):
        messages = [
            Message(role="system", content="You are a code analyst."),
            Message(role="user", content="Analyze this code."),
        ]
        user_prompt, system_prompt = provider._build_prompt(messages)
        assert user_prompt == "Analyze this code."
        assert system_prompt == "You are a code analyst."

    def test_user_only(self, provider):
        messages = [Message(role="user", content="Hello")]
        user_prompt, system_prompt = provider._build_prompt(messages)
        assert user_prompt == "Hello"
        assert system_prompt is None

    def test_multiple_messages(self, provider):
        messages = [
            Message(role="system", content="Part 1"),
            Message(role="system", content="Part 2"),
            Message(role="user", content="Question 1"),
            Message(role="user", content="Question 2"),
        ]
        user_prompt, system_prompt = provider._build_prompt(messages)
        assert system_prompt == "Part 1\n\nPart 2"
        assert user_prompt == "Question 1\n\nQuestion 2"


class TestComplete:
    async def test_successful_completion(self, provider):
        proc = _make_process()
        with patch("codebase_teacher.llm.cli_provider.asyncio.create_subprocess_exec", return_value=proc):
            messages = [
                Message(role="system", content="Be helpful."),
                Message(role="user", content="Say hello."),
            ]
            response = await provider.complete(messages)

        assert response.content == "This is the LLM response."
        assert response.usage.prompt_tokens == 100
        assert response.usage.completion_tokens == 25
        assert response.usage.total_tokens == 125
        assert response.model == "claude-sonnet-4-6"

    async def test_passes_correct_cli_args(self, provider):
        proc = _make_process()
        with patch("codebase_teacher.llm.cli_provider.asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            messages = [
                Message(role="system", content="System prompt."),
                Message(role="user", content="User prompt."),
            ]
            await provider.complete(messages)

        args = mock_exec.call_args[0]
        assert args[0] == "/usr/bin/claude"
        assert "-p" in args
        assert "User prompt." in args
        assert "--output-format" in args
        assert "json" in args
        assert "--tools" in args
        assert "" in args
        assert "--append-system-prompt" in args
        assert "System prompt." in args

    async def test_no_system_prompt_skips_flag(self, provider):
        proc = _make_process()
        with patch("codebase_teacher.llm.cli_provider.asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            messages = [Message(role="user", content="Just a question.")]
            await provider.complete(messages)

        args = mock_exec.call_args[0]
        assert "--append-system-prompt" not in args

    async def test_nonzero_exit_raises(self, provider):
        proc = _make_process(stdout="", stderr="Error: something went wrong", returncode=1)
        with patch("codebase_teacher.llm.cli_provider.asyncio.create_subprocess_exec", return_value=proc):
            with pytest.raises(LLMError, match="exited with code 1"):
                await provider.complete([Message(role="user", content="test")])

    async def test_invalid_json_raises(self, provider):
        proc = _make_process(stdout="not valid json")
        with patch("codebase_teacher.llm.cli_provider.asyncio.create_subprocess_exec", return_value=proc):
            with pytest.raises(LLMError, match="Failed to parse"):
                await provider.complete([Message(role="user", content="test")])

    async def test_timeout_raises(self, provider):
        async def slow_communicate():
            await asyncio.sleep(10)
            return (b"", b"")

        proc = AsyncMock()
        proc.communicate = slow_communicate
        proc.returncode = 0

        with patch("codebase_teacher.llm.cli_provider.shutil.which", return_value="/usr/bin/claude"):
            from codebase_teacher.llm.cli_provider import ClaudeCodeProvider
            short_timeout_provider = ClaudeCodeProvider(timeout=0)

        with patch("codebase_teacher.llm.cli_provider.asyncio.create_subprocess_exec", return_value=proc):
            with pytest.raises(CLIProviderError, match="timed out"):
                await short_timeout_provider.complete([Message(role="user", content="test")])

    async def test_context_window_cached_from_response(self, provider):
        assert provider.context_window == 200_000  # default before any call

        proc = _make_process()
        with patch("codebase_teacher.llm.cli_provider.asyncio.create_subprocess_exec", return_value=proc):
            await provider.complete([Message(role="user", content="test")])

        assert provider.context_window == 200_000  # now from modelUsage


class TestStream:
    async def test_stream_yields_full_response(self, provider):
        proc = _make_process()
        with patch("codebase_teacher.llm.cli_provider.asyncio.create_subprocess_exec", return_value=proc):
            chunks = []
            async for chunk in provider.stream([Message(role="user", content="test")]):
                chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0] == "This is the LLM response."
