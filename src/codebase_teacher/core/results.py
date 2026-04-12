"""Result containers for operations that can partially succeed.

Used by parsers, file readers, and the context manager to return
successes alongside collected per-file failures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class FileFailure:
    """A single file that could not be processed."""

    file_path: str
    error_type: str  # e.g. "SyntaxError", "OSError"
    message: str


@dataclass
class PartialResult(Generic[T]):
    """A result that may include per-file failures alongside the successful value."""

    value: T
    failures: list[FileFailure] = field(default_factory=list)

    @property
    def has_failures(self) -> bool:
        return len(self.failures) > 0

    def failure_summary(self) -> str:
        """Human-readable summary of failures."""
        if not self.failures:
            return ""
        lines = [f"{len(self.failures)} file(s) could not be processed:"]
        for f in self.failures:
            lines.append(f"  - {f.file_path}: {f.error_type}: {f.message}")
        return "\n".join(lines)
