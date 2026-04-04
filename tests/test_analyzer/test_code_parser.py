"""Tests for AST code parser."""

from pathlib import Path

from codebase_teacher.analyzer.code_parser import parse_python_file, parse_codebase


def test_parse_python_file(sample_project):
    """Test parsing a Python file with Flask routes."""
    graph = parse_python_file(sample_project / "app.py", sample_project)

    # Should find functions
    func_names = [f.name for f in graph.functions]
    assert "list_users" in func_names
    assert "create_user" in func_names
    assert "get_user" in func_names

    # Should find imports
    import_modules = [i.module for i in graph.imports]
    assert "flask" in import_modules

    # Check function details
    create_user = next(f for f in graph.functions if f.name == "create_user")
    assert create_user.docstring == "Create a new user."
    assert any("route" in d for d in create_user.decorators)


def test_parse_python_file_with_class(sample_project):
    """Test parsing a file with class definitions."""
    graph = parse_python_file(sample_project / "models.py", sample_project)

    class_names = [c.name for c in graph.classes]
    assert "User" in class_names

    user_class = next(c for c in graph.classes if c.name == "User")
    method_names = [m.name for m in user_class.methods]
    assert "to_dict" in method_names


def test_parse_codebase(sample_project):
    """Test parsing multiple files into a single graph."""
    source_files = ["app.py", "models.py", "tasks.py"]
    graph = parse_codebase(sample_project, source_files)

    # Should have functions from all files
    func_names = [f.name for f in graph.functions]
    assert "list_users" in func_names
    assert "send_welcome_email" in func_names

    # Should have classes
    class_names = [c.name for c in graph.classes]
    assert "User" in class_names


def test_parse_async_function(tmp_path):
    """Test parsing async functions."""
    py_file = tmp_path / "async_module.py"
    py_file.write_text(
        "async def fetch_data(url: str) -> dict:\n"
        '    """Fetch data from URL."""\n'
        "    pass\n"
    )
    graph = parse_python_file(py_file, tmp_path)

    assert len(graph.functions) == 1
    assert graph.functions[0].is_async is True
    assert graph.functions[0].name == "fetch_data"


def test_parse_invalid_python(tmp_path):
    """Test that invalid Python files don't crash the parser."""
    bad_file = tmp_path / "bad.py"
    bad_file.write_text("def this is not valid python {{{")
    graph = parse_python_file(bad_file, tmp_path)
    # Should return empty graph, not raise
    assert graph.functions == []
    assert graph.classes == []
