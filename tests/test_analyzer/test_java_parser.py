"""Tests for Java AST parser."""

from __future__ import annotations

import pytest

pytest.importorskip("tree_sitter_java", reason="tree-sitter-java not installed")

from codebase_teacher.analyzer.java_parser import parse_java_file  # noqa: E402


SIMPLE_CLASS = """\
package com.example;

import java.util.List;
import java.util.ArrayList;

public class UserService {

    public List<User> findAll() {
        return new ArrayList<>();
    }

    public User findById(Long id) {
        return null;
    }

    private void deleteById(Long id) {
    }
}
"""

INTERFACE_SOURCE = """\
package com.example;

import java.util.List;

public interface UserRepository {

    List<User> findAll();

    User findById(Long id);
}
"""

ANNOTATED_CLASS = """\
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;

@Service
public class OrderService {

    @Autowired
    private OrderRepository repository;

    @Override
    public String toString() {
        return "OrderService";
    }
}
"""

ENUM_SOURCE = """\
public enum Status {
    ACTIVE,
    INACTIVE;

    public boolean isActive() {
        return this == ACTIVE;
    }
}
"""

MULTI_CLASS = """\
package com.example;

public class Foo {
    public void foo() {}
}

class Bar {
    public void bar() {}
}
"""


def test_parse_simple_class(tmp_path):
    java_file = tmp_path / "UserService.java"
    java_file.write_text(SIMPLE_CLASS)

    graph = parse_java_file(java_file, tmp_path)

    class_names = [c.name for c in graph.classes]
    assert "UserService" in class_names

    user_service = next(c for c in graph.classes if c.name == "UserService")
    method_names = [m.name for m in user_service.methods]
    assert "findAll" in method_names
    assert "findById" in method_names
    assert "deleteById" in method_names


def test_parse_imports(tmp_path):
    java_file = tmp_path / "UserService.java"
    java_file.write_text(SIMPLE_CLASS)

    graph = parse_java_file(java_file, tmp_path)

    import_modules = [i.module for i in graph.imports]
    assert "java.util" in import_modules

    names_for_java_util = [
        n for i in graph.imports if i.module == "java.util" for n in i.names
    ]
    assert "List" in names_for_java_util or "ArrayList" in names_for_java_util


def test_parse_package_declaration(tmp_path):
    java_file = tmp_path / "UserService.java"
    java_file.write_text(SIMPLE_CLASS)

    graph = parse_java_file(java_file, tmp_path)

    # Package should appear as an import with names=["<package>"]
    package_imports = [i for i in graph.imports if "<package>" in i.names]
    assert package_imports, "Expected package declaration to be extracted"
    assert package_imports[0].module == "com.example"


def test_parse_interface(tmp_path):
    java_file = tmp_path / "UserRepository.java"
    java_file.write_text(INTERFACE_SOURCE)

    graph = parse_java_file(java_file, tmp_path)

    class_names = [c.name for c in graph.classes]
    assert "UserRepository" in class_names

    repo = next(c for c in graph.classes if c.name == "UserRepository")
    assert "<interface>" in repo.bases
    method_names = [m.name for m in repo.methods]
    assert "findAll" in method_names
    assert "findById" in method_names


def test_parse_annotated_class(tmp_path):
    java_file = tmp_path / "OrderService.java"
    java_file.write_text(ANNOTATED_CLASS)

    graph = parse_java_file(java_file, tmp_path)

    class_names = [c.name for c in graph.classes]
    assert "OrderService" in class_names

    order_service = next(c for c in graph.classes if c.name == "OrderService")
    method_names = [m.name for m in order_service.methods]
    assert "toString" in method_names


def test_parse_enum(tmp_path):
    java_file = tmp_path / "Status.java"
    java_file.write_text(ENUM_SOURCE)

    graph = parse_java_file(java_file, tmp_path)

    class_names = [c.name for c in graph.classes]
    assert "Status" in class_names

    status = next(c for c in graph.classes if c.name == "Status")
    assert "<enum>" in status.bases


def test_parse_multiple_classes(tmp_path):
    java_file = tmp_path / "Multi.java"
    java_file.write_text(MULTI_CLASS)

    graph = parse_java_file(java_file, tmp_path)

    class_names = [c.name for c in graph.classes]
    assert "Foo" in class_names
    assert "Bar" in class_names


def test_method_line_numbers(tmp_path):
    java_file = tmp_path / "UserService.java"
    java_file.write_text(SIMPLE_CLASS)

    graph = parse_java_file(java_file, tmp_path)
    user_service = next(c for c in graph.classes if c.name == "UserService")

    find_all = next(m for m in user_service.methods if m.name == "findAll")
    assert find_all.line_number > 0


def test_file_path_in_results(tmp_path):
    java_file = tmp_path / "UserService.java"
    java_file.write_text(SIMPLE_CLASS)

    graph = parse_java_file(java_file, tmp_path)

    assert all(c.file_path == "UserService.java" for c in graph.classes)


def test_graceful_on_invalid_java(tmp_path):
    java_file = tmp_path / "Bad.java"
    java_file.write_text("this is not valid java {{{{")

    # tree-sitter is error-tolerant; we just verify it doesn't raise
    graph = parse_java_file(java_file, tmp_path)
    assert isinstance(graph.classes, list)


def test_graceful_when_file_missing(tmp_path):
    missing = tmp_path / "NonExistent.java"
    graph = parse_java_file(missing, tmp_path)
    assert graph.classes == []
    assert graph.imports == []


def test_terraform_resources_empty_for_java(tmp_path):
    java_file = tmp_path / "UserService.java"
    java_file.write_text(SIMPLE_CLASS)

    graph = parse_java_file(java_file, tmp_path)
    assert graph.terraform_resources == []
