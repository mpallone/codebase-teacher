"""Load optional LEARNER-INFO.md so the user can steer analysis and doc emphasis.

The file is free-form Markdown at the project root. When present, its contents are
threaded into LLM prompts so the generated docs emphasize what the learner cares
about (e.g. "focus on root repo X, treat its dependencies as supporting context").
When absent, behavior is unchanged.
"""

from __future__ import annotations

from pathlib import Path

from codebase_teacher.core.exceptions import LearnerInfoTooLarge

LEARNER_INFO_FILENAME = "LEARNER-INFO.md"
MAX_LEARNER_INFO_CHARS = 20_000


def _path(root: Path) -> Path:
    return root / LEARNER_INFO_FILENAME


def load_learner_info(root: Path) -> str:
    """Read LEARNER-INFO.md from the project root.

    Returns the file's text when present. Returns an empty string when absent
    (not an error — the file is optional).

    Raises LearnerInfoTooLarge if the file exceeds MAX_LEARNER_INFO_CHARS.
    OSError (permission denied, etc.) propagates so the user learns about
    unreadable files instead of silently losing their context.
    """
    path = _path(root)
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    if len(text) > MAX_LEARNER_INFO_CHARS:
        raise LearnerInfoTooLarge(len(text), MAX_LEARNER_INFO_CHARS)
    return text


def learner_info_bytes(root: Path) -> bytes:
    """Return raw bytes of LEARNER-INFO.md for cache hashing.

    Empty bytes when the file is absent. Does not enforce the size limit —
    hashing a too-large file is harmless and load_learner_info will raise
    separately before anything consumes the content.
    """
    path = _path(root)
    if not path.exists():
        return b""
    return path.read_bytes()
