"""Context window budget management and hierarchical summarization.

Handles chunking large codebases to fit within LLM context windows.
Strategy: file-level summaries -> module-level summaries -> project summary.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from codebase_teacher.core.exceptions import ContextBudgetExceeded
from codebase_teacher.core.results import FileFailure, PartialResult
from codebase_teacher.llm.provider import LLMProvider, LLMResponse, Message
from codebase_teacher.llm.prompt_registry import PROMPTS, with_learner_context


@dataclass
class FileSummary:
    """Summary of a single source file."""

    path: str
    summary: str
    token_estimate: int = 0


@dataclass
class ModuleSummary:
    """Summary of a directory/module (aggregated from file summaries)."""

    path: str
    summary: str
    file_summaries: list[FileSummary] = field(default_factory=list)


@dataclass
class ProjectSummary:
    """Top-level project summary (aggregated from module summaries)."""

    summary: str
    module_summaries: list[ModuleSummary] = field(default_factory=list)


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 characters per token for English/code."""
    return len(text) // 4


class ContextManager:
    """Manages context window budget and hierarchical summarization."""

    def __init__(
        self,
        provider: LLMProvider,
        max_concurrent: int = 5,
        learner_info: str = "",
    ):
        self.provider = provider
        self.max_concurrent = max_concurrent
        self.learner_info = learner_info
        self._file_summaries: dict[str, FileSummary] = {}
        self._module_summaries: dict[str, ModuleSummary] = {}
        self._project_summary: ProjectSummary | None = None

    @property
    def available_tokens(self) -> int:
        """Tokens available for content (after reserving for system prompt + response).

        reserved_response tracks the provider's actual configured output cap so a larger
        Settings.max_tokens cannot overflow the input budget.
        """
        reserved_system = 4000  # headroom for our longest system prompts (trace_data_flow, generate_architecture_doc)
        reserved_response = self.provider.max_tokens
        return self.provider.context_window - reserved_system - reserved_response

    def fits_in_context(self, content: str) -> bool:
        return estimate_tokens(content) <= self.available_tokens

    async def summarize_file(self, file_path: str, code: str) -> FileSummary:
        """Produce a structured summary of a single file using the LLM."""
        if file_path in self._file_summaries:
            return self._file_summaries[file_path]

        prompt = PROMPTS["summarize_file"]
        user_content = prompt.format_user(file_path=file_path, code=code)
        messages = [
            Message(role="system", content=prompt.format_system()),
            Message(role="user", content=with_learner_context(user_content, self.learner_info)),
        ]
        response: LLMResponse = await self.provider.complete(messages)
        summary = FileSummary(
            path=file_path,
            summary=response.content,
            token_estimate=estimate_tokens(response.content),
        )
        self._file_summaries[file_path] = summary
        return summary

    async def summarize_files(
        self, files: dict[str, str]
    ) -> PartialResult[list[FileSummary]]:
        """Summarize multiple files with concurrency control.

        Returns a ``PartialResult`` so individual file failures don't crash
        the entire batch.
        """
        semaphore = asyncio.Semaphore(self.max_concurrent)
        paths = list(files.keys())

        async def _summarize(path: str, code: str) -> FileSummary:
            async with semaphore:
                return await self.summarize_file(path, code)

        tasks = [_summarize(path, code) for path, code in files.items()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        summaries: list[FileSummary] = []
        failures: list[FileFailure] = []
        for path, result in zip(paths, results):
            if isinstance(result, BaseException):
                failures.append(FileFailure(
                    file_path=path,
                    error_type=type(result).__name__,
                    message=str(result),
                ))
            else:
                summaries.append(result)

        return PartialResult(value=summaries, failures=failures)

    async def summarize_module(
        self, module_path: str, file_summaries: list[FileSummary]
    ) -> ModuleSummary:
        """Aggregate file summaries into a module-level summary."""
        if module_path in self._module_summaries:
            return self._module_summaries[module_path]

        combined = "\n\n".join(
            f"### {fs.path}\n{fs.summary}" for fs in file_summaries
        )
        user_content = f"Module: {module_path}\n\nFile summaries:\n{combined}"
        messages = [
            Message(
                role="system",
                content=(
                    "You are summarizing a code module/package. Combine the file summaries "
                    "into a concise module overview: purpose, key abstractions, dependencies, "
                    "and data flow role."
                ),
            ),
            Message(
                role="user",
                content=with_learner_context(user_content, self.learner_info),
            ),
        ]
        response = await self.provider.complete(messages)
        module_summary = ModuleSummary(
            path=module_path,
            summary=response.content,
            file_summaries=file_summaries,
        )
        self._module_summaries[module_path] = module_summary
        return module_summary

    async def summarize_project(
        self, module_summaries: list[ModuleSummary]
    ) -> ProjectSummary:
        """Aggregate module summaries into a project-level summary."""
        if self._project_summary is not None:
            return self._project_summary

        combined = "\n\n".join(
            f"### {ms.path}\n{ms.summary}" for ms in module_summaries
        )
        user_content = f"Module summaries:\n{combined}"
        messages = [
            Message(
                role="system",
                content=(
                    "You are producing a high-level project overview. Synthesize these module "
                    "summaries into a concise project description: what the system does, its "
                    "major components, how they connect, and key infrastructure dependencies."
                ),
            ),
            Message(role="user", content=with_learner_context(user_content, self.learner_info)),
        ]
        response = await self.provider.complete(messages)
        self._project_summary = ProjectSummary(
            summary=response.content,
            module_summaries=module_summaries,
        )
        return self._project_summary

    def build_context(
        self,
        project_summary: ProjectSummary,
        focus_module: str | None = None,
        focus_files: list[tuple[str, str]] | None = None,
    ) -> str:
        """Build a context string that fits within the token budget.

        Includes project summary always, module summary if focused,
        and raw file content if there's room.
        """
        parts: list[str] = []
        budget = self.available_tokens

        # Always include project summary
        project_text = f"# Project Overview\n{project_summary.summary}"
        parts.append(project_text)
        budget -= estimate_tokens(project_text)

        # Include focused module summary if specified
        if focus_module:
            for ms in project_summary.module_summaries:
                if ms.path == focus_module:
                    module_text = f"\n# Module: {ms.path}\n{ms.summary}"
                    cost = estimate_tokens(module_text)
                    if cost <= budget:
                        parts.append(module_text)
                        budget -= cost
                    break

        # Include raw file content if there's room
        if focus_files:
            for path, content in focus_files:
                file_text = f"\n# File: {path}\n```\n{content}\n```"
                cost = estimate_tokens(file_text)
                if cost <= budget:
                    parts.append(file_text)
                    budget -= cost
                else:
                    break

        if budget < 0:
            raise ContextBudgetExceeded(
                f"Context exceeded by {-budget} tokens even after summarization"
            )

        return "\n".join(parts)

    def get_cached_summary(self, file_path: str) -> FileSummary | None:
        return self._file_summaries.get(file_path)
