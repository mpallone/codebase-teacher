"""Tests for codebase discovery."""

from pathlib import Path

from codebase_teacher.scanner.discovery import discover_folders, build_folder_tree


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
