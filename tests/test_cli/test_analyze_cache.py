"""Tests for the analyze-cache content hash.

Confirms that editing LEARNER-INFO.md invalidates the cache so docs always
reflect the learner's current priorities.
"""

from __future__ import annotations

from codebase_teacher.cli.analyze import _compute_hash


def _write(path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_hash_stable_for_same_inputs(tmp_path):
    _write(tmp_path / "a.py", "print('hi')\n")

    h1, _ = _compute_hash(["a.py"], tmp_path, b"")
    h2, _ = _compute_hash(["a.py"], tmp_path, b"")

    assert h1 == h2


def test_hash_changes_when_learner_info_changes(tmp_path):
    _write(tmp_path / "a.py", "print('hi')\n")

    baseline, _ = _compute_hash(["a.py"], tmp_path, b"")
    with_info, _ = _compute_hash(["a.py"], tmp_path, b"focus on module X")
    edited, _ = _compute_hash(["a.py"], tmp_path, b"focus on module Y")

    assert baseline != with_info
    assert with_info != edited
    assert baseline != edited


def test_hash_stable_when_learner_info_identical(tmp_path):
    _write(tmp_path / "a.py", "print('hi')\n")

    h1, _ = _compute_hash(["a.py"], tmp_path, b"same text")
    h2, _ = _compute_hash(["a.py"], tmp_path, b"same text")

    assert h1 == h2
