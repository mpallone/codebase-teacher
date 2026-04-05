"""AST-based code parsing for Java files using tree-sitter-java.

Extracts classes, interfaces, methods, imports, annotations, and package
declarations deterministically (no LLM).
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
    import tree_sitter_java as _tsjava
    from tree_sitter import Language, Parser as _TSParser

    _JAVA_LANGUAGE = Language(_tsjava.language())
    _JAVA_AVAILABLE = True
except Exception:  # ImportError, OSError, AttributeError, etc.
    _JAVA_AVAILABLE = False
    _JAVA_LANGUAGE = None  # type: ignore[assignment]


def parse_java_file(file_path: Path, root: Path) -> CodebaseGraph:
    """Parse a Java file and extract structural information."""
    if not _JAVA_AVAILABLE:
        return CodebaseGraph()

    try:
        source = file_path.read_bytes()
        parser = _TSParser(_JAVA_LANGUAGE)
        tree = parser.parse(source)
    except Exception:
        return CodebaseGraph()

    rel_path = str(file_path.relative_to(root))
    classes: list[ClassInfo] = []
    imports: list[ImportInfo] = []

    root_node = tree.root_node
    for child in root_node.named_children:
        node_type = child.type

        if node_type == "import_declaration":
            imp = _extract_import(child, source)
            if imp:
                imports.append(imp)

        elif node_type == "package_declaration":
            pkg = _extract_package(child, source)
            if pkg:
                imports.append(pkg)

        elif node_type in (
            "class_declaration",
            "interface_declaration",
            "enum_declaration",
            "annotation_type_declaration",
            "record_declaration",
        ):
            cls = _extract_class(child, rel_path, source, node_type)
            if cls:
                classes.append(cls)

    return CodebaseGraph(classes=classes, imports=imports)


# ---------------------------------------------------------------------------
# Import / package extraction
# ---------------------------------------------------------------------------


def _extract_import(node, source: bytes) -> ImportInfo | None:
    """Extract an ImportInfo from an import_declaration node."""
    # The full text is something like "import java.util.List;"
    # or "import static java.util.Collections.sort;"
    text = _node_text(node, source).strip()
    text = text.removeprefix("import").strip()
    text = text.removeprefix("static").strip()
    text = text.removesuffix(";").strip()

    if not text:
        return None

    if text.endswith(".*"):
        module = text[:-2]
        names = ["*"]
    elif "." in text:
        parts = text.rsplit(".", 1)
        module, name = parts[0], parts[1]
        names = [name]
    else:
        module = text
        names = [text]

    return ImportInfo(module=module, names=names)


def _extract_package(node, source: bytes) -> ImportInfo | None:
    """Extract the package declaration as an ImportInfo."""
    text = _node_text(node, source).strip()
    text = text.removeprefix("package").strip().removesuffix(";").strip()
    if not text:
        return None
    return ImportInfo(module=text, names=["<package>"])


# ---------------------------------------------------------------------------
# Class / interface extraction
# ---------------------------------------------------------------------------


def _extract_class(node, file_path: str, source: bytes, node_type: str) -> ClassInfo | None:
    """Extract a ClassInfo from a class/interface/enum declaration node."""
    name_node = node.child_by_field_name("name")
    if name_node is None:
        # Fall back to first identifier child
        name_node = _first_child_of_type(node, "identifier")
    if name_node is None:
        return None

    name = _node_text(name_node, source)
    line_number = node.start_point[0] + 1
    bases: list[str] = []

    if node_type == "interface_declaration":
        bases.append("<interface>")
    elif node_type == "enum_declaration":
        bases.append("<enum>")
    elif node_type == "annotation_type_declaration":
        bases.append("<annotation>")
    elif node_type == "record_declaration":
        bases.append("<record>")

    # Superclass: class_declaration uses field "superclass"
    superclass_node = node.child_by_field_name("superclass")
    if superclass_node:
        # superclass node: "extends" <type_identifier>
        for sc_child in superclass_node.named_children:
            bases.append(_node_text(sc_child, source))

    # Implemented interfaces: class_declaration uses field "interfaces"
    # (the node type is super_interfaces, but the field name is "interfaces")
    interfaces_node = node.child_by_field_name("interfaces")
    if interfaces_node:
        _collect_type_list(interfaces_node, source, bases)

    # Extended interfaces for interface_declaration:
    # "extends_interfaces" is the node *type* but not a field name — find by type.
    extends_iface_node = _first_child_of_type(node, "extends_interfaces")
    if extends_iface_node:
        _collect_type_list(extends_iface_node, source, bases)

    # Methods from class body
    methods: list[FunctionInfo] = []
    body_node = node.child_by_field_name("body")
    if body_node:
        for member in body_node.named_children:
            if member.type in ("method_declaration", "constructor_declaration"):
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
# Method extraction
# ---------------------------------------------------------------------------


def _extract_method(node, file_path: str, source: bytes) -> FunctionInfo | None:
    """Extract a FunctionInfo from a method_declaration or constructor_declaration."""
    name_node = node.child_by_field_name("name")
    if name_node is None:
        name_node = _first_child_of_type(node, "identifier")
    if name_node is None:
        return None

    name = _node_text(name_node, source)
    line_number = node.start_point[0] + 1

    # Return type (absent for constructors)
    type_node = node.child_by_field_name("type")
    return_type = _node_text(type_node, source) if type_node else ""

    # Parameters
    params_node = node.child_by_field_name("parameters")
    params_text = _node_text(params_node, source) if params_node else "()"

    # Modifiers + annotations
    modifiers_node = _first_child_of_type(node, "modifiers")
    modifiers_parts: list[str] = []
    annotations: list[str] = []
    if modifiers_node:
        for mod_child in modifiers_node.named_children:
            if mod_child.type in ("annotation", "marker_annotation"):
                annotations.append(_node_text(mod_child, source))
            else:
                modifiers_parts.append(_node_text(mod_child, source))

    # Build signature: "public static String methodName(int x)"
    sig_parts: list[str] = []
    if modifiers_parts:
        sig_parts.append(" ".join(modifiers_parts))
    if return_type:
        sig_parts.append(return_type)
    sig_parts.append(f"{name}{params_text}")
    signature = " ".join(sig_parts)

    return FunctionInfo(
        name=name,
        file_path=file_path,
        line_number=line_number,
        signature=signature,
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


def _collect_type_list(node, source: bytes, out: list[str]) -> None:
    """Collect type names from a super_interfaces / extends_interfaces node.

    These nodes contain a ``type_list`` child whose children are individual
    type identifiers.
    """
    for child in node.named_children:
        if child.type == "type_list":
            for t in child.named_children:
                out.append(_node_text(t, source))
        elif child.type not in ("implements", "extends"):
            # Fallback: collect any type identifier directly
            out.append(_node_text(child, source))
