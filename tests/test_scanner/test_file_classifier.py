"""Tests for file classifier."""

from codebase_teacher.scanner.file_classifier import classify_file, classify_directory


def test_classify_python_source(tmp_project):
    """Test that .py files in src/ are classified as source."""
    result = classify_file(tmp_project / "src" / "utils.py", tmp_project)
    assert result.category == "source"
    assert result.language == "python"
    assert result.token_estimate > 0


def test_classify_test_file(tmp_project):
    """Test that test files are classified as test."""
    result = classify_file(tmp_project / "tests" / "test_utils.py", tmp_project)
    assert result.category == "test"


def test_classify_requirements(tmp_project):
    """Test that requirements.txt is classified as build."""
    result = classify_file(tmp_project / "requirements.txt", tmp_project)
    assert result.category == "build"


def test_classify_directory(tmp_project):
    """Test classifying all files in a directory."""
    files = classify_directory(tmp_project, ["."])
    assert len(files) > 0

    categories = {f.category for f in files}
    assert "source" in categories


def test_classify_with_relevant_folders(tmp_project):
    """Test classifying only specific relevant folders."""
    files = classify_directory(tmp_project, ["src"])
    paths = [f.path for f in files]
    # Should only have files from src/
    assert all("src" in p for p in paths)


def test_classify_scala_source(tmp_project):
    """Test that .scala files are classified as source with scala language."""
    scala_file = tmp_project / "src" / "Main.scala"
    scala_file.parent.mkdir(exist_ok=True, parents=True)
    scala_file.write_text("object Main")
    result = classify_file(scala_file, tmp_project)
    assert result.category == "source"
    assert result.language == "scala"
