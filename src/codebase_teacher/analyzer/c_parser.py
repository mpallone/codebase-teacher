"""AST-based code parsing for C files using tree-sitter-c.

Extracts functions, structs, unions, enums, and #include directives
deterministically (no LLM).
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
    import tree_sitter_c as _tsc
    from tree_sitter import Language, Parser as _TSParser

    _C_LANGUAGE = Language(_tsc.language())
    _C_AVAILABLE = True
except Exception:  # ImportError, OSError, AttributeError, etc.
    _C_AVAILABLE = False
    _C_LANGUAGE = None  # type: ignore[assignment]


_RECORD_KINDS = {
    "struct_specifier": "struct",
    "union_specifier": "union",
    "enum_specifier": "enum",
}


def parse_c_file(file_path: Path, root: Path) -> CodebaseGraph:
    """Parse a C file and extract structural information."""
    if not _C_AVAILABLE:
        return CodebaseGraph()

    try:
        source = file_path.read_bytes()
        parser = _TSParser(_C_LANGUAGE)
        tree = parser.parse(source)
    except Exception:
        return CodebaseGraph()

    rel_path = str(file_path.relative_to(root))
    functions: list[FunctionInfo] = []
    classes: list[ClassInfo] = []
    imports: list[ImportInfo] = []

    for child in tree.root_node.named_children:
        _dispatch(child, rel_path, source, functions, classes, imports)

    return CodebaseGraph(functions=functions, classes=classes, imports=imports)


def _dispatch(
    node,
    file_path: str,
    source: bytes,
    functions: list[FunctionInfo],
    classes: list[ClassInfo],
    imports: list[ImportInfo],
) -> None:
    """Dispatch a top-level node to the appropriate extractor."""
    node_type = node.type

    if node_type == "preproc_include":
        imp = _extract_include(node, source)
        if imp:
            imports.append(imp)
        return

    if node_type == "function_definition":
        func = _extract_function(node, file_path, source)
        if func:
            functions.append(func)
        return

    if node_type in _RECORD_KINDS:
        cls = _extract_record(
            node, file_path, source, kind=_RECORD_KINDS[node_type]
        )
        if cls:
            classes.append(cls)
        return

    if node_type == "type_definition":
        cls = _extract_typedef_record(node, file_path, source)
        if cls:
            classes.append(cls)
        return


# ---------------------------------------------------------------------------
# Include extraction
# ---------------------------------------------------------------------------


def _extract_include(node, source: bytes) -> ImportInfo | None:
    """Extract an ImportInfo from a preproc_include node."""
    # Prefer the grammar's "path" field when available.
    path_node = node.child_by_field_name("path")
    if path_node is not None:
        raw = _node_text(path_node, source).strip()
    else:
        # Fallback: strip the leading "#include" token from full text.
        raw = _node_text(node, source).strip()
        if raw.startswith("#"):
            raw = raw[1:].lstrip()
        if raw.startswith("include"):
            raw = raw[len("include"):].strip()

    # Strip surrounding <...> or "..." delimiters.
    if len(raw) >= 2 and raw[0] in ("<", '"') and raw[-1] in (">", '"'):
        raw = raw[1:-1]

    raw = raw.strip()
    if not raw:
        return None

    return ImportInfo(module=raw, names=["<include>"])


# ---------------------------------------------------------------------------
# Function extraction
# ---------------------------------------------------------------------------


def _extract_function(
    node, file_path: str, source: bytes
) -> FunctionInfo | None:
    """Extract a FunctionInfo from a function_definition node."""
    declarator_node = node.child_by_field_name("declarator")
    if declarator_node is None:
        return None

    func_declarator = _find_function_declarator(declarator_node)
    if func_declarator is None:
        return None

    name_node = func_declarator.child_by_field_name("declarator")
    if name_node is None:
        return None
    name = _node_text(name_node, source).strip()
    if not name:
        return None

    # Return type (includes storage-class specifiers, qualifiers, etc.)
    type_node = node.child_by_field_name("type")
    return_type = _node_text(type_node, source).strip() if type_node else ""

    # Pointer wrappers between the return type and the function declarator
    # (e.g., `int *foo(void)`) live on the declarator chain. Capture them so
    # the signature reflects the real return type.
    pointer_prefix = _pointer_prefix(declarator_node, source)

    params_node = func_declarator.child_by_field_name("parameters")
    params_text = _node_text(params_node, source) if params_node else "()"

    sig_parts: list[str] = []
    if return_type:
        sig_parts.append(return_type)
    if pointer_prefix:
        sig_parts.append(pointer_prefix)
    head = " ".join(sig_parts).strip()
    signature = f"{head} {name}{params_text}".strip() if head else f"{name}{params_text}"

    return FunctionInfo(
        name=name,
        file_path=file_path,
        line_number=node.start_point[0] + 1,
        signature=signature,
        decorators=[],
        is_async=False,
    )


def _find_function_declarator(node):
    """Walk down pointer/parenthesized declarator wrappers to the function_declarator."""
    current = node
    while current is not None:
        if current.type == "function_declarator":
            return current
        inner = current.child_by_field_name("declarator")
        if inner is None or inner is current:
            return None
        current = inner
    return None


def _pointer_prefix(node, source: bytes) -> str:
    """Collect any pointer ``*`` tokens on the declarator chain."""
    stars: list[str] = []
    current = node
    while current is not None and current.type != "function_declarator":
        if current.type == "pointer_declarator":
            stars.append("*")
        inner = current.child_by_field_name("declarator")
        if inner is None or inner is current:
            break
        current = inner
    return "".join(stars)


# ---------------------------------------------------------------------------
# Struct / union / enum extraction
# ---------------------------------------------------------------------------


def _extract_record(
    node,
    file_path: str,
    source: bytes,
    kind: str,
    name_override: str | None = None,
) -> ClassInfo | None:
    """Extract a ClassInfo from a struct/union/enum specifier.

    Returns None for forward declarations (no body) unless a name_override is
    supplied and the body is still present via the typedef path.
    """
    body_node = node.child_by_field_name("body")
    if body_node is None:
        return None

    if name_override:
        name = name_override
    else:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return None
        name = _node_text(name_node, source).strip()

    if not name:
        return None

    return ClassInfo(
        name=name,
        file_path=file_path,
        line_number=node.start_point[0] + 1,
        bases=[f"<{kind}>"],
        methods=[],
    )


def _extract_typedef_record(node, file_path: str, source: bytes) -> ClassInfo | None:
    """Handle `typedef struct { ... } Name;` and friends.

    If the typedef wraps an anonymous struct/union/enum, use the typedef name
    as the ClassInfo name. If the wrapped record already has a name, prefer
    that (the typedef alias is secondary here).
    """
    record_node = None
    kind: str | None = None
    for child in node.named_children:
        if child.type in _RECORD_KINDS:
            record_node = child
            kind = _RECORD_KINDS[child.type]
            break

    if record_node is None or kind is None:
        return None

    # Resolve a name: prefer the record's own name; fall back to the typedef
    # alias (the last type_identifier child of the type_definition).
    name_node = record_node.child_by_field_name("name")
    name: str | None
    if name_node is not None:
        name = _node_text(name_node, source).strip() or None
    else:
        name = None

    if not name:
        alias_node = None
        for child in node.named_children:
            if child.type == "type_identifier":
                alias_node = child
        if alias_node is not None:
            name = _node_text(alias_node, source).strip() or None

    if not name:
        return None

    return _extract_record(
        record_node, file_path, source, kind=kind, name_override=name
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _node_text(node, source: bytes) -> str:
    """Extract the source text for a tree-sitter node."""
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
