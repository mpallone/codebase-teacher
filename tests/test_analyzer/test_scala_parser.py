"""Tests for Scala AST parser."""

from __future__ import annotations

import pytest

pytest.importorskip("tree_sitter_scala", reason="tree-sitter-scala not installed")

from codebase_teacher.analyzer.scala_parser import parse_scala_file  # noqa: E402


SIMPLE_CLASS = """\
package com.example

import scala.collection.mutable
import scala.util.{Try, Success}
import java.util._

class UserService {

  def findAll(): List[User] = List()

  def findById(id: Long): Option[User] = None

  private def deleteById(id: Long): Unit = ()
}
"""

TRAIT_SOURCE = """\
package com.example

trait UserRepository[T] {
  def findAll(): List[T]
  def findById(id: Long): Option[T]
}
"""

OBJECT_SOURCE = """\
object Main {
  def main(args: Array[String]): Unit = println("hello")
}
"""

CASE_CLASS_SOURCE = """\
case class User(id: Long, name: String)
"""

ENUM_SOURCE = """\
enum Status {
  case Active, Inactive
}
"""

EXTENDS_WITH_SOURCE = """\
class OrderService extends BaseService with Logging with Metrics {
  def process(): Unit = ()
}
"""

ANNOTATED_CLASS = """\
import org.springframework.stereotype.Service

@Service
class OrderService {

  @Autowired
  private def repo(): Unit = ()

  override def toString(): String = "OrderService"
}
"""

MULTI_CLASS = """\
package com.example

class Foo {
  def foo(): Unit = ()
}

class Bar {
  def bar(): Unit = ()
}
"""


def test_parse_simple_class(tmp_path):
    scala_file = tmp_path / "UserService.scala"
    scala_file.write_text(SIMPLE_CLASS)

    graph = parse_scala_file(scala_file, tmp_path)

    class_names = [c.name for c in graph.classes]
    assert "UserService" in class_names

    user_service = next(c for c in graph.classes if c.name == "UserService")
    method_names = [m.name for m in user_service.methods]
    assert "findAll" in method_names
    assert "findById" in method_names
    assert "deleteById" in method_names


def test_parse_plain_import(tmp_path):
    scala_file = tmp_path / "UserService.scala"
    scala_file.write_text(SIMPLE_CLASS)

    graph = parse_scala_file(scala_file, tmp_path)

    # `import scala.collection.mutable` -> module="scala.collection", names=["mutable"]
    plain = next(
        (i for i in graph.imports if i.module == "scala.collection"), None
    )
    assert plain is not None
    assert "mutable" in plain.names


def test_parse_selector_import(tmp_path):
    scala_file = tmp_path / "UserService.scala"
    scala_file.write_text(SIMPLE_CLASS)

    graph = parse_scala_file(scala_file, tmp_path)

    # `import scala.util.{Try, Success}` -> module="scala.util"
    selector = next((i for i in graph.imports if i.module == "scala.util"), None)
    assert selector is not None
    assert "Try" in selector.names
    assert "Success" in selector.names


def test_parse_wildcard_import(tmp_path):
    scala_file = tmp_path / "UserService.scala"
    scala_file.write_text(SIMPLE_CLASS)

    graph = parse_scala_file(scala_file, tmp_path)

    # `import java.util._` -> module="java.util", names=["*"]
    wildcard = next((i for i in graph.imports if i.module == "java.util"), None)
    assert wildcard is not None
    assert wildcard.names == ["*"]


def test_parse_package_declaration(tmp_path):
    scala_file = tmp_path / "UserService.scala"
    scala_file.write_text(SIMPLE_CLASS)

    graph = parse_scala_file(scala_file, tmp_path)

    package_imports = [i for i in graph.imports if "<package>" in i.names]
    assert package_imports, "Expected package declaration to be extracted"
    assert package_imports[0].module == "com.example"


def test_parse_trait(tmp_path):
    scala_file = tmp_path / "UserRepository.scala"
    scala_file.write_text(TRAIT_SOURCE)

    graph = parse_scala_file(scala_file, tmp_path)

    class_names = [c.name for c in graph.classes]
    assert "UserRepository" in class_names

    repo = next(c for c in graph.classes if c.name == "UserRepository")
    assert "<trait>" in repo.bases
    method_names = [m.name for m in repo.methods]
    assert "findAll" in method_names
    assert "findById" in method_names


def test_parse_object(tmp_path):
    scala_file = tmp_path / "Main.scala"
    scala_file.write_text(OBJECT_SOURCE)

    graph = parse_scala_file(scala_file, tmp_path)

    class_names = [c.name for c in graph.classes]
    assert "Main" in class_names

    main = next(c for c in graph.classes if c.name == "Main")
    assert "<object>" in main.bases
    assert "main" in [m.name for m in main.methods]


def test_parse_case_class(tmp_path):
    scala_file = tmp_path / "User.scala"
    scala_file.write_text(CASE_CLASS_SOURCE)

    graph = parse_scala_file(scala_file, tmp_path)

    class_names = [c.name for c in graph.classes]
    assert "User" in class_names
    # Case classes are still class_definition nodes; no <object>/<trait> tag.
    user = next(c for c in graph.classes if c.name == "User")
    assert "<object>" not in user.bases
    assert "<trait>" not in user.bases
    assert "<enum>" not in user.bases


def test_parse_enum(tmp_path):
    scala_file = tmp_path / "Status.scala"
    scala_file.write_text(ENUM_SOURCE)

    graph = parse_scala_file(scala_file, tmp_path)

    class_names = [c.name for c in graph.classes]
    assert "Status" in class_names

    status = next(c for c in graph.classes if c.name == "Status")
    assert "<enum>" in status.bases


def test_parse_extends_with(tmp_path):
    scala_file = tmp_path / "OrderService.scala"
    scala_file.write_text(EXTENDS_WITH_SOURCE)

    graph = parse_scala_file(scala_file, tmp_path)

    order = next(c for c in graph.classes if c.name == "OrderService")
    # extends_clause unifies `extends` and `with` into a flat list of parents.
    assert "BaseService" in order.bases
    assert "Logging" in order.bases
    assert "Metrics" in order.bases


def test_parse_annotated_class(tmp_path):
    scala_file = tmp_path / "OrderService.scala"
    scala_file.write_text(ANNOTATED_CLASS)

    graph = parse_scala_file(scala_file, tmp_path)

    class_names = [c.name for c in graph.classes]
    assert "OrderService" in class_names

    order = next(c for c in graph.classes if c.name == "OrderService")
    method_names = [m.name for m in order.methods]
    assert "repo" in method_names
    assert "toString" in method_names

    # @Autowired annotation must land in decorators for repo()
    repo = next(m for m in order.methods if m.name == "repo")
    assert any("Autowired" in d for d in repo.decorators)

    # `override` modifier must appear in the toString signature
    to_string = next(m for m in order.methods if m.name == "toString")
    assert "override" in to_string.signature


def test_parse_multiple_classes(tmp_path):
    scala_file = tmp_path / "Multi.scala"
    scala_file.write_text(MULTI_CLASS)

    graph = parse_scala_file(scala_file, tmp_path)

    class_names = [c.name for c in graph.classes]
    assert "Foo" in class_names
    assert "Bar" in class_names


def test_method_line_numbers(tmp_path):
    scala_file = tmp_path / "UserService.scala"
    scala_file.write_text(SIMPLE_CLASS)

    graph = parse_scala_file(scala_file, tmp_path)
    user_service = next(c for c in graph.classes if c.name == "UserService")

    find_all = next(m for m in user_service.methods if m.name == "findAll")
    assert find_all.line_number > 0


def test_file_path_in_results(tmp_path):
    scala_file = tmp_path / "UserService.scala"
    scala_file.write_text(SIMPLE_CLASS)

    graph = parse_scala_file(scala_file, tmp_path)

    assert all(c.file_path == "UserService.scala" for c in graph.classes)


def test_top_level_function(tmp_path):
    # Scala 3 allows top-level `def` declarations outside any class/object.
    scala_file = tmp_path / "Top.scala"
    scala_file.write_text("def topLevel(x: Int): Int = x + 1\n")

    graph = parse_scala_file(scala_file, tmp_path)
    assert any(f.name == "topLevel" for f in graph.functions)


def test_graceful_on_invalid_scala(tmp_path):
    scala_file = tmp_path / "Bad.scala"
    scala_file.write_text("this is not valid scala {{{{")

    # tree-sitter is error-tolerant; we just verify it doesn't raise
    graph = parse_scala_file(scala_file, tmp_path)
    assert isinstance(graph.classes, list)


def test_graceful_when_file_missing(tmp_path):
    missing = tmp_path / "NonExistent.scala"
    graph = parse_scala_file(missing, tmp_path)
    assert graph.classes == []
    assert graph.imports == []


def test_terraform_resources_empty_for_scala(tmp_path):
    scala_file = tmp_path / "UserService.scala"
    scala_file.write_text(SIMPLE_CLASS)

    graph = parse_scala_file(scala_file, tmp_path)
    assert graph.terraform_resources == []
