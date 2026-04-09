"""AST-based code parsing for Scala files using tree-sitter-scala.

Extracts classes, objects, traits, enums, case classes, methods, imports,
and package declarations deterministically (no LLM). Supports both Scala 2
and Scala 3 syntax.
"""

from __future__ import annotations

from pathlib import Path

from codebase_teacher.storage.models import (
    ClassInfo,
    CodebaseGraph,
    FunctionInfo,
    ImportInfo,
)

# Lazy-initialize tree-sitter at module load to catch ImportError once.
try:
    import tree_sitter_scala as _tsscala
    from tree_sitter import Language, Parser as _TSParser

    _SCALA_LANGUAGE = Language(_tsscala.language())
    _SCALA_AVAILABLE = True
except Exception:  # ImportError, OSError, AttributeError, etc.
    _SCALA_AVAILABLE = False
    _SCALA_LANGUAGE = None  # type: ignore[assignment]


# Node types that represent top-level class-like definitions.
_CLASS_LIKE_NODE_TYPES = frozenset(
    {
        "class_definition",
        "object_definition",
        "trait_definition",
        "enum_definition",
    }
)

# Node types that represent methods/functions (with and without bodies).
_FUNCTION_NODE_TYPES = frozenset({"function_definition", "function_declaration"})


def parse_scala_file(file_path: Path, root: Path) -> CodebaseGraph:
    """Parse a Scala file and extract structural information."""
    if not _SCALA_AVAILABLE:
        return CodebaseGraph()

    try:
        source = file_path.read_bytes()
        parser = _TSParser(_SCALA_LANGUAGE)
        tree = parser.parse(source)
    except Exception:
        return CodebaseGraph()

    rel_path = str(file_path.relative_to(root))
    classes: list[ClassInfo] = []
    functions: list[FunctionInfo] = []
    imports: list[ImportInfo] = []

    root_node = tree.root_node
    for child in root_node.named_children:
        node_type = child.type

        if node_type == "import_declaration":
            imports.extend(_extract_imports(child, source))

        elif node_type == "package_clause":
            pkg = _extract_package(child, source)
            if pkg:
                imports.append(pkg)

        elif node_type in _CLASS_LIKE_NODE_TYPES:
            cls = _extract_class(child, rel_path, source, node_type)
            if cls:
                classes.append(cls)

        elif node_type in _FUNCTION_NODE_TYPES:
            fn = _extract_method(child, rel_path, source)
            if fn:
                functions.append(fn)

    return CodebaseGraph(classes=classes, functions=functions, imports=imports)


# ---------------------------------------------------------------------------
# Import / package extraction
# ---------------------------------------------------------------------------


def _extract_imports(node, source: bytes) -> list[ImportInfo]:
    """Extract ImportInfo(s) from an import_declaration node.

    Scala imports can take several forms:
        import a.b.C               -> module="a.b", names=["C"]
        import a.b._               -> module="a.b", names=["*"]
        import a.b.{X, Y}          -> module="a.b", names=["X", "Y"]
        import a.b.{X => Z, Y}     -> module="a.b", names=["Z", "Y"]  (alias kept)
    """
    path_parts: list[str] = []
    names: list[str] = []
    wildcard = False

    for child in node.named_children:
        if child.type == "identifier":
            path_parts.append(_node_text(child, source))
        elif child.type == "stable_identifier":
            # Dotted path like a.b.c appears as a single stable_identifier
            # in some Scala grammar versions; split on dots.
            for part in _node_text(child, source).split("."):
                if part:
                    path_parts.append(part)
        elif child.type == "namespace_selectors":
            for sel in child.named_children:
                if sel.type == "identifier":
                    names.append(_node_text(sel, source))
                elif sel.type == "arrow_selector":
                    # `X => Z`: use the alias (right side) if present,
                    # otherwise the original name.
                    alias = _first_child_of_type(sel, "identifier")
                    last: str | None = None
                    for ident in sel.named_children:
                        if ident.type == "identifier":
                            last = _node_text(ident, source)
                    names.append(last or (_node_text(alias, source) if alias else ""))
                elif sel.type == "wildcard":
                    names.append("*")
        elif child.type == "namespace_wildcard":
            wildcard = True

    if not path_parts:
        return []

    if wildcard:
        module = ".".join(path_parts)
        return [ImportInfo(module=module, names=["*"])]

    if names:
        module = ".".join(path_parts)
        return [ImportInfo(module=module, names=[n for n in names if n])]

    # Plain `import a.b.C`: last segment is the imported name.
    if len(path_parts) > 1:
        module = ".".join(path_parts[:-1])
        return [ImportInfo(module=module, names=[path_parts[-1]])]

    return [ImportInfo(module=path_parts[0], names=[path_parts[0]])]


def _extract_package(node, source: bytes) -> ImportInfo | None:
    """Extract the package declaration as an ImportInfo.

    The grammar uses `package_clause` with a `package_identifier` child
    whose children are individual identifiers.
    """
    pkg_id = _first_child_of_type(node, "package_identifier")
    if pkg_id is None:
        # Fallback: grab the raw text and strip the keyword.
        text = _node_text(node, source).strip()
        text = text.removeprefix("package").strip()
        if not text:
            return None
        return ImportInfo(module=text, names=["<package>"])

    parts = [
        _node_text(c, source)
        for c in pkg_id.named_children
        if c.type == "identifier"
    ]
    if not parts:
        # package_identifier may itself be a single dotted identifier.
        text = _node_text(pkg_id, source).strip()
        if not text:
            return None
        return ImportInfo(module=text, names=["<package>"])

    return ImportInfo(module=".".join(parts), names=["<package>"])


# ---------------------------------------------------------------------------
# Class / object / trait / enum extraction
# ---------------------------------------------------------------------------


def _extract_class(
    node, file_path: str, source: bytes, node_type: str
) -> ClassInfo | None:
    """Extract a ClassInfo from a class/object/trait/enum definition node."""
    name_node = node.child_by_field_name("name")
    if name_node is None:
        name_node = _first_child_of_type(node, "identifier")
    if name_node is None:
        return None

    name = _node_text(name_node, source)
    line_number = node.start_point[0] + 1
    bases: list[str] = []

    # Tag the kind so downstream consumers can distinguish.
    if node_type == "object_definition":
        bases.append("<object>")
    elif node_type == "trait_definition":
        bases.append("<trait>")
    elif node_type == "enum_definition":
        bases.append("<enum>")
    # Regular class_definition (including case class) has no tag.

    # Parent types come from the `extend` field (an extends_clause with one
    # or more `type` fields — grammar treats `extends X with Y` uniformly).
    extend_node = node.child_by_field_name("extend")
    if extend_node is None:
        extend_node = _first_child_of_type(node, "extends_clause")
    if extend_node is not None:
        for child in extend_node.named_children:
            if child.type in (
                "type_identifier",
                "generic_type",
                "projected_type",
                "stable_type_identifier",
            ):
                bases.append(_node_text(child, source))

    # Extract members.
    methods: list[FunctionInfo] = []
    body_node = node.child_by_field_name("body")
    if body_node is None:
        # enum_definition uses `body` field pointing at enum_body; class/trait
        # use template_body. Fall back to searching named children.
        body_node = _first_child_of_type(
            node, "template_body"
        ) or _first_child_of_type(node, "enum_body")

    if body_node is not None:
        for member in body_node.named_children:
            if member.type in _FUNCTION_NODE_TYPES:
                method = _extract_method(member, file_path, source)
                if method:
                    methods.append(method)

    return ClassInfo(
        name=name,
        file_path=file_path,
        line_number=line_number,
        bases=bases,
        methods=methods,
    )


# ---------------------------------------------------------------------------
# Method / function extraction
# ---------------------------------------------------------------------------


def _extract_method(node, file_path: str, source: bytes) -> FunctionInfo | None:
    """Extract a FunctionInfo from a function_definition/function_declaration."""
    name_node = node.child_by_field_name("name")
    if name_node is None:
        name_node = _first_child_of_type(node, "identifier")
    if name_node is None:
        return None

    name = _node_text(name_node, source)
    line_number = node.start_point[0] + 1

    # Parameters
    params_node = node.child_by_field_name("parameters")
    params_text = _node_text(params_node, source) if params_node else "()"

    # Return type (optional in Scala; omitted when inferred).
    return_type_node = node.child_by_field_name("return_type")
    return_type = _node_text(return_type_node, source) if return_type_node else ""

    # Modifiers and annotations. In tree-sitter-scala, annotations appear as
    # direct children of the function node, while visibility/other modifiers
    # are wrapped in a `modifiers` node whose children mix named nodes
    # (`access_modifier`, `annotation`) with unnamed keyword tokens
    # (`override`, `final`, `abstract`, `sealed`, `implicit`, `lazy`, ...).
    # We therefore walk ALL children (not just named) of the modifiers
    # wrapper to capture keyword-only modifiers like `override`.
    _MODIFIER_KEYWORDS = {
        "override",
        "final",
        "abstract",
        "sealed",
        "implicit",
        "lazy",
        "inline",
        "open",
        "private",
        "protected",
    }
    modifier_parts: list[str] = []
    annotations: list[str] = []
    for child in node.children:
        if child.type == "annotation":
            annotations.append(_node_text(child, source))
        elif child.type == "modifiers":
            for mod_child in child.children:
                if mod_child.type == "annotation":
                    annotations.append(_node_text(mod_child, source))
                elif mod_child.type == "access_modifier":
                    modifier_parts.append(_node_text(mod_child, source))
                elif mod_child.type in _MODIFIER_KEYWORDS:
                    modifier_parts.append(_node_text(mod_child, source))

    # Build signature: "private def foo(x: Int): String"
    sig_parts: list[str] = []
    if modifier_parts:
        sig_parts.append(" ".join(modifier_parts))
    sig_parts.append(f"def {name}{params_text}")
    if return_type:
        sig_parts.append(f": {return_type}")
    # Join with spaces, but keep the ": return_type" attached to the name.
    if return_type:
        signature = " ".join(sig_parts[:-1]) + sig_parts[-1]
    else:
        signature = " ".join(sig_parts)

    return FunctionInfo(
        name=name,
        file_path=file_path,
        line_number=line_number,
        signature=signature.strip(),
        decorators=annotations,
        is_async=False,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _node_text(node, source: bytes) -> str:
    """Extract the source text for a tree-sitter node."""
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _first_child_of_type(node, type_name: str):
    """Return the first named child with the given type, or None."""
    for child in node.named_children:
        if child.type == type_name:
            return child
    return None
