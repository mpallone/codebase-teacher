"""Global configuration for codebase-teacher."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables and CLI flags."""

    model: str = Field(
        default="anthropic/claude-sonnet-4-20250514",
        description="LLM model in litellm format (provider/model)",
    )
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(default=16384, gt=0)
    output_dir: str = Field(
        default=".teacher-output",
        description="Directory for generated artifacts (relative to target project)",
    )
    db_dir: str = Field(
        default=".teacher",
        description="Directory for SQLite database (relative to target project)",
    )
    verbose: bool = False
    max_concurrent_llm_calls: int = Field(default=5, gt=0)

    model_config = {"env_prefix": "CODEBASE_TEACHER_"}

    def output_path(self, project_root: Path) -> Path:
        return project_root / self.output_dir

    def db_path(self, project_root: Path) -> Path:
        db_dir = project_root / self.db_dir
        db_dir.mkdir(parents=True, exist_ok=True)
        return db_dir / "teacher.db"
