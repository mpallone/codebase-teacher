"""AST-based code parsing for Python, Java, C, Scala, and Terraform/HCL files.

Extracts functions, classes, imports, decorators, and Terraform resources
deterministically (no LLM).
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

from rich.console import Console

from codebase_teacher.analyzer.c_parser import parse_c_file
from codebase_teacher.analyzer.java_parser import parse_java_file
from codebase_teacher.analyzer.scala_parser import parse_scala_file
from codebase_teacher.analyzer.terraform_parser import parse_terraform_file
from codebase_teacher.scanner.file_classifier import LANGUAGE_MAP
from codebase_teacher.storage.models import (
    ClassInfo,
    CodebaseGraph,
    FunctionInfo,
    ImportInfo,
    TerraformResource,
)


def parse_python_file(file_path: Path, root: Path) -> CodebaseGraph:
    """Parse a Python file and extract structural information."""
    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source, filename=str(file_path))
    except (SyntaxError, OSError):
        return CodebaseGraph()

    rel_path = str(file_path.relative_to(root))
    functions: list[FunctionInfo] = []
    classes: list[ClassInfo] = []
    imports: list[ImportInfo] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Skip methods (they'll be captured in class processing)
            if _is_top_level_or_module_level(node, tree):
                functions.append(_extract_function(node, rel_path))

        elif isinstance(node, ast.ClassDef):
            classes.append(_extract_class(node, rel_path))

        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(ImportInfo(
                    module=alias.name,
                    names=[alias.asname or alias.name],
                ))

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(ImportInfo(
                    module=node.module,
                    names=[alias.name for alias in node.names],
                    is_relative=node.level > 0,
                ))

    return CodebaseGraph(functions=functions, classes=classes, imports=imports)


def _is_top_level_or_module_level(node: ast.AST, tree: ast.Module) -> bool:
    """Check if a function is at module level (not nested in a class)."""
    for top_node in tree.body:
        if top_node is node:
            return True
    return False


def _extract_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef, file_path: str
) -> FunctionInfo:
    """Extract function information from an AST node."""
    # Build signature
    args = node.args
    arg_strs: list[str] = []
    for arg in args.args:
        annotation = ""
        if arg.annotation:
            annotation = f": {ast.unparse(arg.annotation)}"
        arg_strs.append(f"{arg.arg}{annotation}")

    returns = ""
    if node.returns:
        returns = f" -> {ast.unparse(node.returns)}"

    signature = f"def {node.name}({', '.join(arg_strs)}){returns}"

    # Extract decorators
    decorators = [ast.unparse(d) for d in node.decorator_list]

    # Extract docstring
    docstring = ast.get_docstring(node)

    return FunctionInfo(
        name=node.name,
        file_path=file_path,
        line_number=node.lineno,
        signature=signature,
        decorators=decorators,
        docstring=docstring,
        is_async=isinstance(node, ast.AsyncFunctionDef),
    )


def _extract_class(node: ast.ClassDef, file_path: str) -> ClassInfo:
    """Extract class information from an AST node."""
    bases = [ast.unparse(base) for base in node.bases]
    docstring = ast.get_docstring(node)

    methods: list[FunctionInfo] = []
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods.append(_extract_function(item, file_path))

    return ClassInfo(
        name=node.name,
        file_path=file_path,
        line_number=node.lineno,
        bases=bases,
        methods=methods,
        docstring=docstring,
    )


def parse_codebase(
    root: Path,
    source_files: list[str],
    console: Console | None = None,
) -> CodebaseGraph:
    """Parse Python, Java, C, Scala, and Terraform/HCL source files into a single CodebaseGraph.

    Source files whose extension is recognized as a language (present in
    ``LANGUAGE_MAP``) but which have no AST parser wired up are skipped.
    A yellow warning is emitted via ``console`` (or a default stderr
    ``Console`` if none is provided), aggregated per unique extension so
    the user sees one line per unsupported language rather than one line
    per file.
    """
    all_functions: list[FunctionInfo] = []
    all_classes: list[ClassInfo] = []
    all_imports: list[ImportInfo] = []
    all_terraform_resources: list[TerraformResource] = []
    skipped: Counter[str] = Counter()

    for rel_path in source_files:
        file_path = root / rel_path
        suffix = file_path.suffix.lower()

        if suffix == ".py":
            graph = parse_python_file(file_path, root)
        elif suffix == ".java":
            graph = parse_java_file(file_path, root)
        elif suffix in (".c", ".h"):
            graph = parse_c_file(file_path, root)
        elif suffix == ".scala":
            graph = parse_scala_file(file_path, root)
        elif suffix in (".tf", ".hcl"):
            graph = parse_terraform_file(file_path, root)
        else:
            skipped[suffix] += 1
            continue

        all_functions.extend(graph.functions)
        all_classes.extend(graph.classes)
        all_imports.extend(graph.imports)
        all_terraform_resources.extend(graph.terraform_resources)

    if skipped:
        warn_console = console or Console(stderr=True)
        for suffix, count in sorted(skipped.items()):
            language = LANGUAGE_MAP.get(suffix, "unknown")
            warn_console.print(
                f"[yellow]Warning:[/] skipped {count} source file(s) "
                f"with extension '{suffix}' (language '{language}') "
                f"— no AST parser configured."
            )

    return CodebaseGraph(
        functions=all_functions,
        classes=all_classes,
        imports=all_imports,
        terraform_resources=all_terraform_resources,
    )
