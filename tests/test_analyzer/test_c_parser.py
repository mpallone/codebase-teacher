"""Tests for C AST parser."""

from __future__ import annotations

import pytest

pytest.importorskip("tree_sitter_c", reason="tree-sitter-c not installed")

from codebase_teacher.analyzer.c_parser import parse_c_file  # noqa: E402


SIMPLE_FUNCTION = """\
int add(int a, int b) {
    return a + b;
}
"""

MULTI_FUNCTION = """\
#include <stdio.h>

int add(int a, int b) {
    return a + b;
}

static void greet(const char *name) {
    printf("hello, %s\\n", name);
}
"""

STRUCT_SOURCE = """\
struct Point {
    int x;
    int y;
};
"""

UNION_SOURCE = """\
union Value {
    int i;
    float f;
};
"""

ENUM_SOURCE = """\
enum Color {
    RED,
    GREEN,
    BLUE
};
"""

TYPEDEF_STRUCT_SOURCE = """\
typedef struct {
    int x;
    int y;
} Point;
"""

INCLUDE_ANGLE_SOURCE = """\
#include <stdio.h>

int main(void) {
    return 0;
}
"""

INCLUDE_QUOTED_SOURCE = """\
#include "myheader.h"

int main(void) {
    return 0;
}
"""

FORWARD_DECL_SOURCE = """\
struct Foo;

int touch(struct Foo *f);
"""


def test_parse_simple_function(tmp_path):
    c_file = tmp_path / "add.c"
    c_file.write_text(SIMPLE_FUNCTION)

    graph = parse_c_file(c_file, tmp_path)

    func_names = [f.name for f in graph.functions]
    assert "add" in func_names

    add = next(f for f in graph.functions if f.name == "add")
    assert "int" in add.signature
    assert "(int a, int b)" in add.signature
    assert add.line_number > 0
    assert add.file_path == "add.c"


def test_parse_multiple_functions(tmp_path):
    c_file = tmp_path / "multi.c"
    c_file.write_text(MULTI_FUNCTION)

    graph = parse_c_file(c_file, tmp_path)

    func_names = [f.name for f in graph.functions]
    assert "add" in func_names
    assert "greet" in func_names


def test_parse_struct(tmp_path):
    c_file = tmp_path / "point.c"
    c_file.write_text(STRUCT_SOURCE)

    graph = parse_c_file(c_file, tmp_path)

    class_names = [c.name for c in graph.classes]
    assert "Point" in class_names

    point = next(c for c in graph.classes if c.name == "Point")
    assert "<struct>" in point.bases


def test_parse_union(tmp_path):
    c_file = tmp_path / "value.c"
    c_file.write_text(UNION_SOURCE)

    graph = parse_c_file(c_file, tmp_path)

    class_names = [c.name for c in graph.classes]
    assert "Value" in class_names

    value = next(c for c in graph.classes if c.name == "Value")
    assert "<union>" in value.bases


def test_parse_enum(tmp_path):
    c_file = tmp_path / "color.c"
    c_file.write_text(ENUM_SOURCE)

    graph = parse_c_file(c_file, tmp_path)

    class_names = [c.name for c in graph.classes]
    assert "Color" in class_names

    color = next(c for c in graph.classes if c.name == "Color")
    assert "<enum>" in color.bases


def test_parse_typedef_struct(tmp_path):
    c_file = tmp_path / "point.c"
    c_file.write_text(TYPEDEF_STRUCT_SOURCE)

    graph = parse_c_file(c_file, tmp_path)

    class_names = [c.name for c in graph.classes]
    assert "Point" in class_names

    point = next(c for c in graph.classes if c.name == "Point")
    assert "<struct>" in point.bases


def test_parse_include_angle_bracket(tmp_path):
    c_file = tmp_path / "main.c"
    c_file.write_text(INCLUDE_ANGLE_SOURCE)

    graph = parse_c_file(c_file, tmp_path)

    stdio_imports = [i for i in graph.imports if i.module == "stdio.h"]
    assert stdio_imports, "Expected #include <stdio.h> to be extracted"
    assert stdio_imports[0].names == ["<include>"]


def test_parse_include_quoted(tmp_path):
    c_file = tmp_path / "main.c"
    c_file.write_text(INCLUDE_QUOTED_SOURCE)

    graph = parse_c_file(c_file, tmp_path)

    import_modules = [i.module for i in graph.imports]
    assert "myheader.h" in import_modules


def test_skips_forward_declaration(tmp_path):
    c_file = tmp_path / "forward.c"
    c_file.write_text(FORWARD_DECL_SOURCE)

    graph = parse_c_file(c_file, tmp_path)

    # `struct Foo;` is a forward declaration — no body, so no ClassInfo.
    class_names = [c.name for c in graph.classes]
    assert "Foo" not in class_names


def test_parse_header_file(tmp_path):
    header_file = tmp_path / "api.h"
    header_file.write_text(STRUCT_SOURCE)

    graph = parse_c_file(header_file, tmp_path)

    class_names = [c.name for c in graph.classes]
    assert "Point" in class_names


def test_graceful_on_invalid_c(tmp_path):
    c_file = tmp_path / "bad.c"
    c_file.write_text("this is not valid c {{{{")

    # tree-sitter is error-tolerant; we just verify it doesn't raise
    graph = parse_c_file(c_file, tmp_path)
    assert isinstance(graph.classes, list)
    assert isinstance(graph.functions, list)


def test_raises_when_file_missing(tmp_path):
    missing = tmp_path / "nonexistent.c"
    with pytest.raises(FileNotFoundError):
        parse_c_file(missing, tmp_path)


def test_file_path_in_results(tmp_path):
    c_file = tmp_path / "multi.c"
    c_file.write_text(MULTI_FUNCTION)

    graph = parse_c_file(c_file, tmp_path)

    assert all(f.file_path == "multi.c" for f in graph.functions)


def test_terraform_resources_empty_for_c(tmp_path):
    c_file = tmp_path / "multi.c"
    c_file.write_text(MULTI_FUNCTION)

    graph = parse_c_file(c_file, tmp_path)
    assert graph.terraform_resources == []
