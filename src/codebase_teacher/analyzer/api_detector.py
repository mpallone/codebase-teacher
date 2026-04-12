"""Detect API endpoints and external interfaces using LLM analysis."""

from __future__ import annotations

import json

from codebase_teacher.llm.prompt_registry import PROMPTS
from codebase_teacher.llm.provider import LLMProvider, Message
from codebase_teacher.llm.structured import complete_and_parse_list
from codebase_teacher.storage.models import APIEndpoint


async def detect_apis(
    provider: LLMProvider,
    file_contents: dict[str, str],
) -> list[APIEndpoint]:
    """Detect API endpoints from source code using LLM analysis.

    Args:
        provider: LLM provider to use.
        file_contents: Dict of {relative_path: file_content} for source files.

    Returns:
        List of detected API endpoints.
    """
    if not file_contents:
        return []

    # Build code chunks for the prompt
    code_chunks = _build_code_chunks(file_contents)

    prompt = PROMPTS["detect_apis"]
    messages = [
        Message(role="system", content=prompt.format_system()),
        Message(role="user", content=prompt.format_user(code_chunks=code_chunks)),
    ]

    return await complete_and_parse_list(provider, messages, APIEndpoint)


def _build_code_chunks(file_contents: dict[str, str]) -> str:
    """Format file contents for inclusion in a prompt."""
    chunks: list[str] = []
    for path, content in file_contents.items():
        chunks.append(f"### File: {path}\n```\n{content}\n```")
    return "\n\n".join(chunks)


def detect_apis_from_ast(
    functions: list,
    classes: list,
) -> list[APIEndpoint]:
    """Detect likely API endpoints from AST data without LLM.

    Looks for common decorators: @app.route, @router.get, @api_view, etc.
    """
    endpoints: list[APIEndpoint] = []
    route_decorators = {
        "route", "get", "post", "put", "delete", "patch",
        "api_view", "action",
    }

    for func in functions:
        for dec in func.decorators:
            dec_lower = dec.lower()
            if any(rd in dec_lower for rd in route_decorators):
                # Try to extract path from decorator
                path = _extract_path_from_decorator(dec)
                method = _extract_method_from_decorator(dec)
                endpoints.append(APIEndpoint(
                    method=method,
                    path=path,
                    handler=func.name,
                    file=func.file_path,
                    description=func.docstring or "",
                ))

    for cls in classes:
        for method_info in cls.methods:
            for dec in method_info.decorators:
                dec_lower = dec.lower()
                if any(rd in dec_lower for rd in route_decorators):
                    path = _extract_path_from_decorator(dec)
                    method = _extract_method_from_decorator(dec)
                    endpoints.append(APIEndpoint(
                        method=method,
                        path=path,
                        handler=f"{cls.name}.{method_info.name}",
                        file=method_info.file_path,
                        description=method_info.docstring or "",
                    ))

    return endpoints


def _extract_path_from_decorator(decorator: str) -> str:
    """Try to extract a URL path from a decorator string."""
    import re
    match = re.search(r'["\'](/[^"\']*)["\']', decorator)
    return match.group(1) if match else ""


def _extract_method_from_decorator(decorator: str) -> str:
    """Try to extract HTTP method from a decorator string."""
    dec_lower = decorator.lower()
    for method in ("get", "post", "put", "delete", "patch"):
        if method in dec_lower:
            return method.upper()
    return "GET"
