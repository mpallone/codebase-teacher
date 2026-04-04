"""SQLite database setup and operations."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scan_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    folder_path TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('relevant', 'irrelevant', 'unknown')),
    UNIQUE(project_id, folder_path)
);

CREATE TABLE IF NOT EXISTS file_classifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    file_path TEXT NOT NULL,
    category TEXT NOT NULL,
    language TEXT,
    token_estimate INTEGER DEFAULT 0,
    UNIQUE(project_id, file_path)
);

CREATE TABLE IF NOT EXISTS analysis_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    analyzer_name TEXT NOT NULL,
    file_path TEXT,
    content_hash TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, analyzer_name, file_path)
);

CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    artifact_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class Database:
    """SQLite database for codebase-teacher state."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._initialize()
        return self._conn

    def _initialize(self) -> None:
        self.conn.executescript(SCHEMA_SQL)
        # Check/set schema version
        row = self.conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        if row[0] is None:
            self.conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
            self.conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # --- Project operations ---

    def get_or_create_project(self, path: str, name: str) -> int:
        row = self.conn.execute("SELECT id FROM projects WHERE path = ?", (path,)).fetchone()
        if row:
            return row["id"]
        cursor = self.conn.execute(
            "INSERT INTO projects (path, name) VALUES (?, ?)", (path, name)
        )
        self.conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    # --- Scan state operations ---

    def set_folder_status(self, project_id: int, folder_path: str, status: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO scan_state (project_id, folder_path, status) VALUES (?, ?, ?)",
            (project_id, folder_path, status),
        )
        self.conn.commit()

    def get_folder_statuses(self, project_id: int) -> dict[str, str]:
        rows = self.conn.execute(
            "SELECT folder_path, status FROM scan_state WHERE project_id = ?",
            (project_id,),
        ).fetchall()
        return {row["folder_path"]: row["status"] for row in rows}

    def get_relevant_folders(self, project_id: int) -> list[str]:
        rows = self.conn.execute(
            "SELECT folder_path FROM scan_state WHERE project_id = ? AND status = 'relevant'",
            (project_id,),
        ).fetchall()
        return [row["folder_path"] for row in rows]

    # --- File classification operations ---

    def set_file_classification(
        self, project_id: int, file_path: str, category: str,
        language: str | None = None, token_estimate: int = 0,
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO file_classifications "
            "(project_id, file_path, category, language, token_estimate) VALUES (?, ?, ?, ?, ?)",
            (project_id, file_path, category, language, token_estimate),
        )
        self.conn.commit()

    def get_files_by_category(self, project_id: int, category: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT file_path, language, token_estimate FROM file_classifications "
            "WHERE project_id = ? AND category = ?",
            (project_id, category),
        ).fetchall()
        return [dict(row) for row in rows]

    # --- Analysis cache operations ---

    def cache_analysis(
        self, project_id: int, analyzer_name: str, content_hash: str,
        result: dict | list, file_path: str | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO analysis_cache "
            "(project_id, analyzer_name, file_path, content_hash, result_json) VALUES (?, ?, ?, ?, ?)",
            (project_id, analyzer_name, file_path, content_hash, json.dumps(result)),
        )
        self.conn.commit()

    def get_cached_analysis(
        self, project_id: int, analyzer_name: str, content_hash: str,
        file_path: str | None = None,
    ) -> dict | list | None:
        row = self.conn.execute(
            "SELECT result_json FROM analysis_cache "
            "WHERE project_id = ? AND analyzer_name = ? AND file_path IS ? AND content_hash = ?",
            (project_id, analyzer_name, file_path, content_hash),
        ).fetchone()
        if row:
            return json.loads(row["result_json"])
        return None

    # --- Artifact operations ---

    def record_artifact(self, project_id: int, artifact_type: str, file_path: str) -> None:
        self.conn.execute(
            "INSERT INTO artifacts (project_id, artifact_type, file_path) VALUES (?, ?, ?)",
            (project_id, artifact_type, file_path),
        )
        self.conn.commit()

    def get_artifacts(self, project_id: int, artifact_type: str | None = None) -> list[dict]:
        if artifact_type:
            rows = self.conn.execute(
                "SELECT artifact_type, file_path, created_at FROM artifacts "
                "WHERE project_id = ? AND artifact_type = ?",
                (project_id, artifact_type),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT artifact_type, file_path, created_at FROM artifacts WHERE project_id = ?",
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]
