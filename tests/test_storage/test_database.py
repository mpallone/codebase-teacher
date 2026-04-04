"""Tests for SQLite database operations."""

from codebase_teacher.storage.database import Database


def test_create_project(tmp_db):
    """Test creating and retrieving a project."""
    project_id = tmp_db.get_or_create_project("/path/to/project", "my-project")
    assert project_id > 0

    # Getting the same project should return the same ID
    same_id = tmp_db.get_or_create_project("/path/to/project", "my-project")
    assert same_id == project_id


def test_folder_status(tmp_db):
    """Test setting and getting folder statuses."""
    pid = tmp_db.get_or_create_project("/test", "test")

    tmp_db.set_folder_status(pid, "src", "relevant")
    tmp_db.set_folder_status(pid, "vendor", "irrelevant")
    tmp_db.set_folder_status(pid, "docs", "unknown")

    statuses = tmp_db.get_folder_statuses(pid)
    assert statuses["src"] == "relevant"
    assert statuses["vendor"] == "irrelevant"
    assert statuses["docs"] == "unknown"


def test_get_relevant_folders(tmp_db):
    """Test filtering for relevant folders only."""
    pid = tmp_db.get_or_create_project("/test", "test")

    tmp_db.set_folder_status(pid, "src", "relevant")
    tmp_db.set_folder_status(pid, "lib", "relevant")
    tmp_db.set_folder_status(pid, "vendor", "irrelevant")

    relevant = tmp_db.get_relevant_folders(pid)
    assert set(relevant) == {"src", "lib"}


def test_file_classification(tmp_db):
    """Test file classification storage."""
    pid = tmp_db.get_or_create_project("/test", "test")

    tmp_db.set_file_classification(pid, "main.py", "source", "python", 100)
    tmp_db.set_file_classification(pid, "test_main.py", "test", "python", 50)

    source_files = tmp_db.get_files_by_category(pid, "source")
    assert len(source_files) == 1
    assert source_files[0]["file_path"] == "main.py"
    assert source_files[0]["language"] == "python"


def test_analysis_cache(tmp_db):
    """Test caching and retrieving analysis results."""
    pid = tmp_db.get_or_create_project("/test", "test")

    result = {"apis": [{"path": "/health"}]}
    tmp_db.cache_analysis(pid, "api_detector", "abc123", result)

    cached = tmp_db.get_cached_analysis(pid, "api_detector", "abc123")
    assert cached == result

    # Different hash should return None
    assert tmp_db.get_cached_analysis(pid, "api_detector", "different") is None


def test_artifacts(tmp_db):
    """Test recording and listing artifacts."""
    pid = tmp_db.get_or_create_project("/test", "test")

    tmp_db.record_artifact(pid, "docs", "docs/architecture.md")
    tmp_db.record_artifact(pid, "docs", "docs/api-reference.md")
    tmp_db.record_artifact(pid, "diagrams", "diagrams/architecture.md")

    all_artifacts = tmp_db.get_artifacts(pid)
    assert len(all_artifacts) == 3

    doc_artifacts = tmp_db.get_artifacts(pid, "docs")
    assert len(doc_artifacts) == 2
