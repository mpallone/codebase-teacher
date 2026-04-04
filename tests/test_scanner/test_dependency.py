"""Tests for dependency detection."""

from codebase_teacher.scanner.dependency import detect_dependencies


def test_detect_requirements_txt(tmp_project):
    """Test detecting dependencies from requirements.txt."""
    report = detect_dependencies(tmp_project)
    assert "requirements.txt" in report.config_files

    dep_names = [d.name for d in report.dependencies]
    assert "flask" in dep_names
    assert "redis" in dep_names


def test_detect_infra_hints(tmp_project):
    """Test that infrastructure hints are detected from dependencies."""
    report = detect_dependencies(tmp_project)
    # redis should be detected as infrastructure
    hints_lower = [h.lower() for h in report.infra_hints]
    assert any("redis" in h for h in hints_lower)


def test_detect_no_dependencies(tmp_path):
    """Test behavior when no dependency files exist."""
    report = detect_dependencies(tmp_path)
    assert report.dependencies == []
    assert report.config_files == []


def test_detect_sample_project(sample_project):
    """Test against the full sample project fixture."""
    report = detect_dependencies(sample_project)
    dep_names = [d.name for d in report.dependencies]
    assert "flask" in dep_names
    assert "celery" in dep_names
    assert "redis" in dep_names
