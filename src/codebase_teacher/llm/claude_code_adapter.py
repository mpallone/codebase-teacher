"""LLM provider that shells out to the `claude` CLI.

Uses `claude --print` to route LLM calls through the user's Claude Code
subscription instead of requiring an API key. This means `teach analyze`
can run at zero additional cost beyond the monthly subscription.

The claude CLI must be installed and authenticated (i.e., the user must be
logged in to Claude Code).
"""

from __future__ import annotations

import subprocess
import tempfile
from typing import AsyncIterator

from codebase_teacher.core.exceptions import LLMError
from codebase_teacher.llm.provider import LLMResponse, Message, TokenUsage


class ClaudeCodeProvider:
    """LLM provider backed by the `claude` CLI in --print mode."""

    def __init__(self, model: str = "sonnet", max_tokens: int = 16384):
        self._model = model
        self._max_tokens = max_tokens

    async def complete(
        self,
        messages: list[Message],
        temperature: float = 0.3,
        max_tokens: int | None = None,
        response_format=None,
    ) -> LLMResponse:
        system_parts = []
        user_parts = []
        for m in messages:
            if m.role == "system":
                system_parts.append(m.content)
            else:
                user_parts.append(m.content)

        system_prompt = "\n\n".join(system_parts)
        user_prompt = "\n\n".join(user_parts)

        # Write the user prompt to a temp file to avoid shell escaping issues
        # and to handle large prompts that would exceed argument limits.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(user_prompt)
            prompt_file = f.name

        cmd = [
            "claude",
            "--print",
            "--output-format", "text",
            "--no-session-persistence",
            "--model", self._model,
            "--disallowedTools", "Bash,Edit,Write,Read,Glob,Grep,Agent,NotebookEdit,WebFetch,WebSearch",
        ]
        if system_prompt:
            cmd.extend(["--system-prompt", system_prompt])

        try:
            proc = subprocess.run(
                cmd,
                input=user_prompt,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout per call
            )
        except subprocess.TimeoutExpired as e:
            raise LLMError("Claude CLI timed out after 300s") from e
        except FileNotFoundError as e:
            raise LLMError(
                "claude CLI not found. Install Claude Code and log in to use "
                "the claude-code provider."
            ) from e
        finally:
            import os
            os.unlink(prompt_file)

        if proc.returncode != 0:
            raise LLMError(f"Claude CLI failed (exit {proc.returncode}): {proc.stderr}")

        content = proc.stdout.strip()

        # We don't get exact token counts from the CLI, so estimate.
        prompt_tokens = len(user_prompt) // 4 + len(system_prompt) // 4
        completion_tokens = len(content) // 4

        return LLMResponse(
            content=content,
            usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
            model=f"claude-code/{self._model}",
        )

    async def stream(
        self,
        messages: list[Message],
        temperature: float = 0.3,
    ) -> AsyncIterator[str]:
        # For simplicity, just do a complete call and yield the whole thing.
        response = await self.complete(messages, temperature)
        yield response.content

    @property
    def context_window(self) -> int:
        return 200_000

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    @property
    def model_name(self) -> str:
        return f"claude-code/{self._model}"
