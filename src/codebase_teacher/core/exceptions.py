"""Custom exception hierarchy for codebase-teacher."""


class CodebaseTeacherError(Exception):
    """Base exception for all codebase-teacher errors."""


class ScanError(CodebaseTeacherError):
    """Error during codebase scanning."""


class LearnerInfoTooLarge(ScanError):
    """LEARNER-INFO.md exists but exceeds the size limit."""

    def __init__(self, actual_chars: int, limit_chars: int) -> None:
        self.actual_chars = actual_chars
        self.limit_chars = limit_chars
        super().__init__(
            f"LEARNER-INFO.md is {actual_chars} characters, which exceeds the "
            f"limit of {limit_chars}. Trim the file or split it into smaller, "
            f"more focused priorities."
        )


class AnalysisError(CodebaseTeacherError):
    """Error during code analysis."""


class GenerationError(CodebaseTeacherError):
    """Error during content generation."""


class LLMError(CodebaseTeacherError):
    """Error communicating with LLM provider."""


class LLMResponseError(LLMError):
    """LLM returned an unparseable or invalid response."""


class ContextBudgetExceeded(LLMError):
    """Content exceeds the model's context window."""


class CLIProviderError(LLMError):
    """Error running a CLI-based LLM provider (tool not found, timeout, etc.)."""


class FileProcessingError(CodebaseTeacherError):
    """A single file could not be parsed or read."""

    def __init__(self, file_path: str, message: str) -> None:
        self.file_path = file_path
        super().__init__(f"{file_path}: {message}")


class StorageError(CodebaseTeacherError):
    """Error with database or file storage."""
