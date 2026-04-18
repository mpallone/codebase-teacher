"""Tests for the LEARNER-INFO.md loader."""

from __future__ import annotations

import pytest

from codebase_teacher.core.exceptions import LearnerInfoTooLarge
from codebase_teacher.scanner.learner_info import (
    LEARNER_INFO_FILENAME,
    MAX_LEARNER_INFO_CHARS,
    learner_info_bytes,
    load_learner_info,
)


def test_returns_empty_string_when_file_absent(tmp_path):
    assert load_learner_info(tmp_path) == ""
    assert learner_info_bytes(tmp_path) == b""


def test_round_trips_present_file(tmp_path):
    content = "I care about repo X. Treat its dependencies as supporting context only."
    (tmp_path / LEARNER_INFO_FILENAME).write_text(content, encoding="utf-8")

    assert load_learner_info(tmp_path) == content
    assert learner_info_bytes(tmp_path) == content.encode("utf-8")


def test_raises_when_file_exceeds_limit(tmp_path):
    oversized = "x" * (MAX_LEARNER_INFO_CHARS + 1)
    (tmp_path / LEARNER_INFO_FILENAME).write_text(oversized, encoding="utf-8")

    with pytest.raises(LearnerInfoTooLarge) as exc_info:
        load_learner_info(tmp_path)

    assert exc_info.value.actual_chars == MAX_LEARNER_INFO_CHARS + 1
    assert exc_info.value.limit_chars == MAX_LEARNER_INFO_CHARS
    # Error message mentions both numbers so the user knows how much to trim.
    assert str(MAX_LEARNER_INFO_CHARS + 1) in str(exc_info.value)
    assert str(MAX_LEARNER_INFO_CHARS) in str(exc_info.value)


def test_accepts_file_at_exact_limit(tmp_path):
    at_limit = "y" * MAX_LEARNER_INFO_CHARS
    (tmp_path / LEARNER_INFO_FILENAME).write_text(at_limit, encoding="utf-8")

    assert load_learner_info(tmp_path) == at_limit
