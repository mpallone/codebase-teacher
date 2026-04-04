"""Project context — holds state for a codebase-teacher session."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from codebase_teacher.core.config import Settings


class ProjectContext(BaseModel):
    """Immutable context for a single project analysis session."""

    root: Path = Field(description="Root directory of the target codebase")
    settings: Settings = Field(default_factory=Settings)

    model_config = {"arbitrary_types_allowed": True}

    @property
    def output_path(self) -> Path:
        return self.settings.output_path(self.root)

    @property
    def db_path(self) -> Path:
        return self.settings.db_path(self.root)
