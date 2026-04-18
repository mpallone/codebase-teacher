"""Tests for codebase discovery."""

from pathlib import Path

import pytest

from codebase_teacher.scanner.discovery import (
    build_folder_tree,
    discover_folders,
    folders_from_file,
)


def test_discover_folders(tmp_project):
    """Test that folder discovery finds directories and skips hidden ones."""
    folders = discover_folders(tmp_project)
    folder_names = [f.name for f in folders]

    assert "src" in folder_names
    assert "tests" in folder_names
    # Should not include hidden directories
    assert ".git" not in folder_names


def test_discover_folders_skips_pycache(tmp_project):
    """Test that __pycache__ is skipped."""
    (tmp_project / "__pycache__").mkdir()
    folders = discover_folders(tmp_project)
    folder_names = [f.name for f in folders]
    assert "__pycache__" not in folder_names


def test_discover_folders_empty_dir(tmp_path):
    """Test discovery on a directory with no subdirectories."""
    folders = discover_folders(tmp_path)
    assert folders == []


def test_build_folder_tree(tmp_project):
    """Test that a folder tree can be built without errors."""
    tree = build_folder_tree(tmp_project)
    # Just verify it doesn't crash and produces something
    assert tree is not None


def _project_id(db, root):
    return db.get_or_create_project(str(root), root.name)


def test_folders_from_file_relative_paths(tmp_project, tmp_db):
    folders_file = tmp_project / "folders.txt"
    folders_file.write_text("src\ntests\n")
    project_id = _project_id(tmp_db, tmp_project)

    result = folders_from_file(tmp_project, folders_file, tmp_db, project_id)

    assert result == ["src", "tests"]
    statuses = tmp_db.get_folder_statuses(project_id)
    assert statuses == {"src": "relevant", "tests": "relevant"}


def test_folders_from_file_absolute_paths(tmp_project, tmp_db):
    folders_file = tmp_project / "folders.txt"
    folders_file.write_text(f"{tmp_project / 'src'}\n{tmp_project / 'tests'}\n")
    project_id = _project_id(tmp_db, tmp_project)

    result = folders_from_file(tmp_project, folders_file, tmp_db, project_id)

    assert result == ["src", "tests"]


def test_folders_from_file_skips_blanks_and_comments(tmp_project, tmp_db):
    folders_file = tmp_project / "folders.txt"
    folders_file.write_text("# top-level comment\n\nsrc\n   \n# another\ntests\n")
    project_id = _project_id(tmp_db, tmp_project)

    result = folders_from_file(tmp_project, folders_file, tmp_db, project_id)

    assert result == ["src", "tests"]


def test_folders_from_file_rejects_outside_root(tmp_project, tmp_db, tmp_path):
    outside = tmp_path / "other_project"
    outside.mkdir()
    folders_file = tmp_project / "folders.txt"
    folders_file.write_text(f"{outside}\n")
    project_id = _project_id(tmp_db, tmp_project)

    with pytest.raises(ValueError, match="outside the scan root"):
        folders_from_file(tmp_project, folders_file, tmp_db, project_id)


def test_folders_from_file_rejects_nonexistent(tmp_project, tmp_db):
    folders_file = tmp_project / "folders.txt"
    folders_file.write_text("does_not_exist\n")
    project_id = _project_id(tmp_db, tmp_project)

    with pytest.raises(ValueError, match="does not exist"):
        folders_from_file(tmp_project, folders_file, tmp_db, project_id)


def test_folders_from_file_rejects_non_directory(tmp_project, tmp_db):
    folders_file = tmp_project / "folders.txt"
    # main.py exists as a file, not a directory
    folders_file.write_text("main.py\n")
    project_id = _project_id(tmp_db, tmp_project)

    with pytest.raises(ValueError, match="not a directory"):
        folders_from_file(tmp_project, folders_file, tmp_db, project_id)


def test_folders_from_file_empty_file_errors(tmp_project, tmp_db):
    folders_file = tmp_project / "folders.txt"
    folders_file.write_text("# only comments\n\n   \n")
    project_id = _project_id(tmp_db, tmp_project)

    with pytest.raises(ValueError, match="no directories listed"):
        folders_from_file(tmp_project, folders_file, tmp_db, project_id)
