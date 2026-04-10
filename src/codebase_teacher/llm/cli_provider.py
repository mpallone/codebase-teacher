"""Claude Code CLI-based LLM provider.

Shells out to the `claude` CLI tool instead of calling an API directly.
No API key required — uses the user's existing Claude Code auth.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from typing import AsyncIterator

from codebase_teacher.core.exceptions import CLIProviderError, LLMError
from codebase_teacher.llm.provider import LLMResponse, Message, TokenUsage

logger = logging.getLogger(__name__)

# Default timeout for CLI calls (seconds). CLI invocations are slower than API calls.
DEFAULT_TIMEOUT = 300


class ClaudeCodeProvider:
    """LLM provider that shells out to the `claude` CLI."""

    def __init__(self, max_tokens: int = 16384, timeout: int = DEFAULT_TIMEOUT):
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._context_window_cache: int | None = None

        exe = shutil.which("claude")
        if exe is None:
            raise CLIProviderError(
                "claude CLI not found on PATH. "
                "Install Claude Code: https://docs.anthropic.com/en/docs/claude-code"
            )
        self._exe = exe

    @staticmethod
    def _build_prompt(messages: list[Message]) -> tuple[str, str | None]:
        """Combine messages into a user prompt and optional system prompt.

        Returns (user_prompt, system_prompt_or_none).
        """
        system_parts: list[str] = []
        user_parts: list[str] = []

        for msg in messages:
            if msg.role == "system":
                system_parts.append(msg.content)
            else:
                user_parts.append(msg.content)

        user_prompt = "\n\n".join(user_parts)
        system_prompt = "\n\n".join(system_parts) if system_parts else None
        return user_prompt, system_prompt

    async def complete(
        self,
        messages: list[Message],
        temperature: float = 0.3,
        max_tokens: int | None = None,
        response_format=None,
    ) -> LLMResponse:
        user_prompt, system_prompt = self._build_prompt(messages)

        cmd: list[str] = [
            self._exe,
            "-p", user_prompt,
            "--output-format", "json",
            "--tools", "",
            "--setting-sources", "",
        ]
        if system_prompt:
            cmd.extend(["--system-prompt", system_prompt])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout
            )
        except asyncio.TimeoutError:
            raise CLIProviderError(
                f"claude CLI timed out after {self._timeout}s"
            )
        except Exception as e:
            raise CLIProviderError(f"Failed to run claude CLI: {e}") from e

        if proc.returncode != 0:
            err_msg = stderr.decode(errors="replace").strip()
            raise LLMError(f"claude CLI exited with code {proc.returncode}: {err_msg}")

        raw = stdout.decode(errors="replace")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise LLMError(f"Failed to parse claude CLI JSON output: {e}") from e

        content = data.get("result", "")
        usage_data = data.get("usage", {})
        model_usage = data.get("modelUsage", {})

        # Extract model name from modelUsage keys
        model_name = next(iter(model_usage), "claude")

        # Cache context window from modelUsage if available
        if model_usage and self._context_window_cache is None:
            first_model = next(iter(model_usage.values()), {})
            cw = first_model.get("contextWindow")
            if cw:
                self._context_window_cache = cw

        return LLMResponse(
            content=content,
            usage=TokenUsage(
                prompt_tokens=usage_data.get("input_tokens", 0),
                completion_tokens=usage_data.get("output_tokens", 0),
                total_tokens=usage_data.get("input_tokens", 0)
                + usage_data.get("output_tokens", 0),
            ),
            model=model_name,
        )

    async def stream(
        self,
        messages: list[Message],
        temperature: float = 0.3,
    ) -> AsyncIterator[str]:
        response = await self.complete(messages, temperature)
        yield response.content

    @property
    def context_window(self) -> int:
        return self._context_window_cache or 200_000

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    @property
    def model_name(self) -> str:
        return "claude-code"
