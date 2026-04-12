"""AST-based parsing for Terraform / HCL files using tree-sitter-hcl.

Extracts resources, data sources, modules, variables, outputs, and providers
deterministically (no LLM).
"""

from __future__ import annotations

from pathlib import Path

from codebase_teacher.storage.models import CodebaseGraph, TerraformResource

# Terraform block types we want to capture.
_TERRAFORM_BLOCK_TYPES = frozenset({
    "resource",
    "data",
    "module",
    "variable",
    "output",
    "provider",
    "terraform",
    "locals",
})

# Lazy-initialize tree-sitter at module load to catch ImportError once.
try:
    import tree_sitter_hcl as _tshcl
    from tree_sitter import Language, Parser as _TSParser

    _HCL_LANGUAGE = Language(_tshcl.language())
    _HCL_AVAILABLE = True
except Exception:  # ImportError, OSError, AttributeError, etc.
    _HCL_AVAILABLE = False
    _HCL_LANGUAGE = None  # type: ignore[assignment]


def parse_terraform_file(file_path: Path, root: Path) -> CodebaseGraph:
    """Parse a Terraform/HCL file and extract structural information."""
    if not _HCL_AVAILABLE:
        return CodebaseGraph()

    source = file_path.read_bytes()
    parser = _TSParser(_HCL_LANGUAGE)
    tree = parser.parse(source)

    rel_path = str(file_path.relative_to(root))
    resources: list[TerraformResource] = []
    _collect_blocks(tree.root_node, source, rel_path, resources)

    return CodebaseGraph(terraform_resources=resources)


# ---------------------------------------------------------------------------
# Tree traversal
# ---------------------------------------------------------------------------


def _collect_blocks(
    node,
    source: bytes,
    file_path: str,
    resources: list[TerraformResource],
) -> None:
    """Walk the AST and collect all top-level Terraform blocks."""
    for child in node.children:
        if child.type == "block":
            resource = _parse_block(child, source, file_path)
            if resource:
                resources.append(resource)
        else:
            # Recurse into body/config containers but not into block bodies
            # (nested blocks like `lifecycle {}` inside a resource won't match
            # _TERRAFORM_BLOCK_TYPES, so they're harmlessly skipped).
            _collect_blocks(child, source, file_path, resources)


# ---------------------------------------------------------------------------
# Block parsing
# ---------------------------------------------------------------------------


def _parse_block(node, source: bytes, file_path: str) -> TerraformResource | None:
    """Parse a single HCL block node into a TerraformResource."""
    block_type, labels = _block_type_and_labels(node, source)
    if not block_type or block_type not in _TERRAFORM_BLOCK_TYPES:
        return None

    line_number = node.start_point[0] + 1

    if block_type == "resource" and len(labels) >= 2:
        return TerraformResource(
            kind="resource",
            type=labels[0],
            name=labels[1],
            file_path=file_path,
            line_number=line_number,
        )

    if block_type == "data" and len(labels) >= 2:
        return TerraformResource(
            kind="data",
            type=labels[0],
            name=labels[1],
            file_path=file_path,
            line_number=line_number,
        )

    if block_type in ("module", "variable", "output", "provider") and labels:
        return TerraformResource(
            kind=block_type,
            type="",
            name=labels[0],
            file_path=file_path,
            line_number=line_number,
        )

    if block_type in ("terraform", "locals"):
        return TerraformResource(
            kind=block_type,
            type="",
            name="",
            file_path=file_path,
            line_number=line_number,
        )

    return None


def _block_type_and_labels(node, source: bytes) -> tuple[str, list[str]]:
    """Return (block_type, [label, ...]) for a block node.

    Handles two common grammar layouts:

    Layout A (field-based grammar, e.g. nickel-lang tree-sitter-hcl):
      block has field "type" (identifier) and field "label" (string/identifier).

    Layout B (positional grammar, fallback):
      First named identifier child is the block type; subsequent string
      children are labels until we hit a body/object child.
    """
    # --- Layout A: use field names ---
    type_node = node.child_by_field_name("type")
    if type_node and type_node.type == "identifier":
        block_type = _node_text(type_node, source)
        labels: list[str] = []
        # Collect all "label" fields
        cursor = node.walk()
        cursor.goto_first_child()
        while True:
            if cursor.node.type not in ("identifier", "quoted_template", "string_lit", "template_literal"):
                # Gather via the API instead: iterate named_children
                break
            cursor.goto_next_sibling()
        # Simpler: just collect by child_by_field_name cycling isn't available,
        # so walk named_children and collect labels after the type node.
        found_type = False
        for child in node.named_children:
            if child is type_node:
                found_type = True
                continue
            if not found_type:
                continue
            label_text = _extract_label_text(child, source)
            if label_text is not None:
                labels.append(label_text)
            elif child.type in ("body", "block_end", "object", "{"):
                break
        return block_type, labels

    # --- Layout B: positional fallback ---
    named = node.named_children
    if not named:
        return "", []

    first = named[0]
    if first.type != "identifier":
        return "", []

    block_type = _node_text(first, source)
    labels = []
    for child in named[1:]:
        label_text = _extract_label_text(child, source)
        if label_text is not None:
            labels.append(label_text)
        elif child.type not in ("identifier",):
            # Hit something that isn't a label (the body or an unexpected node)
            break
    return block_type, labels


def _extract_label_text(node, source: bytes) -> str | None:
    """Extract string label text from a node, or None if not a label."""
    if node.type == "quoted_template":
        # Content is in template_literal children (between the quotes)
        parts: list[str] = []
        for child in node.children:
            if child.type == "template_literal":
                parts.append(_node_text(child, source))
        return "".join(parts)

    if node.type == "string_lit":
        text = _node_text(node, source)
        return text.strip('"\'')

    if node.type == "template_literal":
        return _node_text(node, source)

    # Some grammars use a bare identifier as a label (e.g. for module names)
    # but we only treat it as a label if the block type has already been found.
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _node_text(node, source: bytes) -> str:
    """Extract the source text for a tree-sitter node."""
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
