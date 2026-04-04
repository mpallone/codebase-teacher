"""Write generated artifacts (markdown, diagrams) to the output directory."""

from __future__ import annotations

from pathlib import Path

from codebase_teacher.storage.database import Database


class ArtifactStore:
    """Manages writing generated content to the output directory."""

    def __init__(self, output_dir: Path, db: Database, project_id: int):
        self.output_dir = output_dir
        self.db = db
        self.project_id = project_id

    def write(self, artifact_type: str, filename: str, content: str) -> Path:
        """Write an artifact to disk and record it in the database.

        Args:
            artifact_type: Category subdirectory (e.g., "docs", "diagrams")
            filename: Name of the file to write
            content: Content to write

        Returns:
            Path to the written file.
        """
        subdir = self.output_dir / artifact_type
        subdir.mkdir(parents=True, exist_ok=True)

        filepath = subdir / filename
        filepath.write_text(content, encoding="utf-8")

        self.db.record_artifact(
            self.project_id, artifact_type, str(filepath.relative_to(self.output_dir))
        )
        return filepath

    def read(self, artifact_type: str, filename: str) -> str | None:
        """Read an existing artifact."""
        filepath = self.output_dir / artifact_type / filename
        if filepath.exists():
            return filepath.read_text(encoding="utf-8")
        return None

    def list_artifacts(self, artifact_type: str | None = None) -> list[dict]:
        """List recorded artifacts."""
        return self.db.get_artifacts(self.project_id, artifact_type)
