"""Tests for AST code parser."""

from pathlib import Path

from rich.console import Console

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


def test_parse_codebase_warns_on_unsupported_language(tmp_path, capsys):
    """Unsupported source languages should surface an aggregated warning."""
    (tmp_path / "a.rb").write_text("class Foo; end")
    (tmp_path / "b.rb").write_text("class Bar; end")
    (tmp_path / "c.kt").write_text("fun main() {}")

    console = Console(force_terminal=False, width=200)
    graph = parse_codebase(
        tmp_path, ["a.rb", "b.rb", "c.kt"], console=console
    )

    captured = capsys.readouterr()
    # One aggregated warning per unique extension (not one per file).
    assert "skipped 2 source file(s) with extension '.rb'" in captured.out
    assert "skipped 1 source file(s) with extension '.kt'" in captured.out
    assert "language 'ruby'" in captured.out
    assert "language 'kotlin'" in captured.out
    assert graph.classes == []


def test_parse_codebase_no_warning_when_all_supported(tmp_path, capsys):
    """Pure-supported codebases must not emit a skip warning."""
    (tmp_path / "a.py").write_text("def foo(): pass\n")

    console = Console(force_terminal=False, width=200)
    parse_codebase(tmp_path, ["a.py"], console=console)

    captured = capsys.readouterr()
    assert "skipped" not in captured.out
    assert "Warning" not in captured.out


def test_parse_codebase_skip_warning_without_console(tmp_path, capsys):
    """When no console is passed, warnings still appear on stderr."""
    (tmp_path / "a.go").write_text("package main")

    parse_codebase(tmp_path, ["a.go"])

    captured = capsys.readouterr()
    # Default console uses stderr=True
    assert "skipped 1 source file(s) with extension '.go'" in captured.err
    assert "language 'go'" in captured.err
