"""Tests for API detection."""

from codebase_teacher.analyzer.api_detector import detect_apis_from_ast
from codebase_teacher.analyzer.code_parser import parse_python_file


def test_detect_flask_routes(sample_project):
    """Test detecting Flask route decorators from AST."""
    graph = parse_python_file(sample_project / "app.py", sample_project)
    endpoints = detect_apis_from_ast(graph.functions, graph.classes)

    assert len(endpoints) >= 2

    paths = [ep.path for ep in endpoints]
    assert "/api/users" in paths

    # Check methods
    methods = {ep.path: ep.method for ep in endpoints}
    # At least one GET and one POST
    assert any(m == "GET" for m in methods.values())
    assert any(m == "POST" for m in methods.values())


def test_detect_no_apis(tmp_path):
    """Test behavior when no API routes exist."""
    py_file = tmp_path / "plain.py"
    py_file.write_text("def helper():\n    return 42\n")
    graph = parse_python_file(py_file, tmp_path)
    endpoints = detect_apis_from_ast(graph.functions, graph.classes)
    assert endpoints == []
