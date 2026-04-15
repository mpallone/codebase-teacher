"""Single-page HTML documentation generator.

Produces a self-contained index.html that combines all docs and diagrams
into one page with sidebar navigation, light/dark theme toggle,
collapsible sections, and live-rendered Mermaid diagrams.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

import markdown as md
from jinja2 import Environment, FileSystemLoader

from codebase_teacher.core.exceptions import LLMError
from codebase_teacher.generator.diagrams import _clean_mermaid
from codebase_teacher.generator.docs import (
    API_CHUNK_SIZE,
    _format_apis,
    _format_data_flows,
    _format_infrastructure,
    _format_module_summaries,
    _generate_api_chunk_with_retry,
    console,
)
from codebase_teacher.llm.prompt_registry import PROMPTS
from codebase_teacher.llm.provider import LLMProvider, Message
from codebase_teacher.storage.artifact_store import ArtifactStore
from codebase_teacher.storage.models import AnalysisResult

TEMPLATE_DIR = Path(__file__).parent / "templates"


@dataclass
class Section:
    """A single section of the HTML page."""

    title: str
    slug: str
    html_content: str


def _slugify(text: str) -> str:
    """Convert a title to a URL-safe slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug.strip("-")


def _markdown_to_html(md_content: str) -> str:
    """Convert markdown to HTML and transform mermaid blocks for live rendering."""
    html_content = md.markdown(
        md_content,
        extensions=["fenced_code", "tables", "toc"],
    )
    return _convert_mermaid_blocks(html_content)


def _convert_mermaid_blocks(html_content: str) -> str:
    """Replace fenced mermaid code blocks with <pre class="mermaid"> tags.

    The markdown library renders ```mermaid blocks as:
      <pre><code class="language-mermaid">...</code></pre>
    We convert these to:
      <pre class="mermaid">...</pre>
    so mermaid.js can pick them up for live rendering.
    """
    return re.sub(
        r'<pre><code class="language-mermaid">(.*?)</code></pre>',
        lambda m: f'<pre class="mermaid">{_sanitize_mermaid(html.unescape(m.group(1)))}</pre>',
        html_content,
        flags=re.DOTALL,
    )


def _sanitize_mermaid(code: str) -> str:
    """Clean up LLM-generated mermaid code to reduce rendering failures.

    Common issues:
    - Unquoted special characters in node labels (parentheses, brackets, etc.)
    - Smart quotes that Mermaid can't parse
    - Leading/trailing whitespace that confuses the parser
    """
    # Strip leading/trailing whitespace
    code = code.strip()
    # Replace smart quotes with straight quotes
    code = code.replace("\u201c", '"').replace("\u201d", '"')
    code = code.replace("\u2018", "'").replace("\u2019", "'")
    # Replace em/en dashes with regular dashes (can break arrow syntax)
    code = code.replace("\u2014", "--").replace("\u2013", "-")
    return code


async def _generate_section(
    provider: LLMProvider,
    prompt_name: str,
    prompt_kwargs: dict[str, str],
    title: str,
) -> Section:
    """Call the LLM with a named prompt and return a Section with HTML content."""
    prompt = PROMPTS[prompt_name]
    messages = [
        Message(role="system", content=prompt.format_system()),
        Message(role="user", content=prompt.format_user(**prompt_kwargs)),
    ]
    response = await provider.complete(messages)
    return Section(
        title=title,
        slug=_slugify(title),
        html_content=_markdown_to_html(response.content),
    )


async def _generate_api_section_chunked(
    provider: LLMProvider,
    analysis: AnalysisResult,
    data_flows_formatted: str,
) -> Section:
    """Generate the API Reference section in chunks for large endpoint sets."""
    endpoints = analysis.api_endpoints
    chunks = [
        endpoints[i : i + API_CHUNK_SIZE]
        for i in range(0, len(endpoints), API_CHUNK_SIZE)
    ]

    console.print(
        f"  API Reference: {len(endpoints)} endpoints in {len(chunks)} chunks"
    )

    html_parts: list[str] = []
    for idx, chunk in enumerate(chunks, 1):
        markdown_content = await _generate_api_chunk_with_retry(
            provider,
            chunk,
            chunk_index=idx,
            chunk_total=len(chunks),
            data_flows_formatted=data_flows_formatted,
        )
        html_parts.append(_markdown_to_html(markdown_content))

    return Section(
        title="API Reference",
        slug="api-reference",
        html_content="\n<hr />\n".join(html_parts),
    )


async def _generate_diagram_section(
    provider: LLMProvider,
    analysis: AnalysisResult,
    diagram_type: str,
) -> Section:
    """Generate a diagram section with mermaid content."""
    if diagram_type == "architecture":
        messages = [
            Message(
                role="system",
                content=(
                    "You are generating a Mermaid diagram showing the high-level architecture "
                    "of a software system. Use a flowchart (graph TD) or C4-style diagram. "
                    "Keep it readable — no more than 15 nodes. Group related components. "
                    "Output ONLY the Mermaid diagram code, nothing else."
                ),
            ),
            Message(
                role="user",
                content=(
                    f"Generate a Mermaid architecture diagram for this system.\n\n"
                    f"Project overview:\n{analysis.project_summary}\n\n"
                    f"Modules:\n{_format_module_summaries(analysis.module_summaries)}\n\n"
                    f"Infrastructure:\n{_format_infrastructure(analysis.infrastructure)}\n\n"
                    f"APIs:\n{_format_apis(analysis.api_endpoints)}"
                ),
            ),
        ]
        response = await provider.complete(messages)
        mermaid_code = _sanitize_mermaid(_clean_mermaid(response.content))
        html_content = f'<pre class="mermaid">{html.escape(mermaid_code)}</pre>'
        return Section(
            title="Architecture Diagram",
            slug="architecture-diagram",
            html_content=html_content,
        )
    else:
        # Data flow diagrams — may have pre-generated mermaid
        if analysis.data_flows:
            parts: list[str] = []
            for flow in analysis.data_flows:
                if flow.mermaid_diagram:
                    cleaned = _sanitize_mermaid(flow.mermaid_diagram)
                    parts.append(
                        f"<h3>{html.escape(flow.name)}</h3>\n"
                        f'<pre class="mermaid">{html.escape(cleaned)}</pre>'
                    )
                else:
                    parts.append(
                        f"<h3>{html.escape(flow.name)}</h3>\n"
                        f"<p>Entry: {html.escape(', '.join(flow.entry_points))}</p>\n"
                        f"<p>Steps: {html.escape(' → '.join(flow.steps))}</p>\n"
                        f"<p>Output: {html.escape(', '.join(flow.outputs))}</p>"
                    )
            return Section(
                title="Data Flow Diagrams",
                slug="data-flow-diagrams",
                html_content="\n".join(parts),
            )

        # Generate from scratch via LLM
        messages = [
            Message(
                role="system",
                content=(
                    "You are generating Mermaid sequence diagrams showing data flows through "
                    "a software system. Show how requests/data enter, get processed, and exit. "
                    "Output ONLY Mermaid diagram code."
                ),
            ),
            Message(
                role="user",
                content=(
                    f"Generate data flow diagrams for this system.\n\n"
                    f"Project: {analysis.project_summary}\n\n"
                    f"Modules: {_format_module_summaries(analysis.module_summaries)}"
                ),
            ),
        ]
        response = await provider.complete(messages)
        mermaid_code = _sanitize_mermaid(_clean_mermaid(response.content))
        html_content = f'<pre class="mermaid">{html.escape(mermaid_code)}</pre>'
        return Section(
            title="Data Flow Diagrams",
            slug="data-flow-diagrams",
            html_content=html_content,
        )


async def generate_html_page(
    provider: LLMProvider,
    analysis: AnalysisResult,
    store: ArtifactStore,
    project_name: str,
) -> tuple[Path, list[tuple[str, Exception]]]:
    """Generate a single-page HTML document with all docs and diagrams.

    Returns (path_to_index_html, errors).
    """
    # Prepare prompt kwargs shared across doc sections
    module_summaries = _format_module_summaries(analysis.module_summaries)
    data_flows = _format_data_flows(analysis.data_flows)
    infrastructure = _format_infrastructure(analysis.infrastructure)
    apis = _format_apis(analysis.api_endpoints)

    # Define the doc sections to generate
    doc_specs = [
        (
            "generate_overview_doc",
            {
                "project_summary": analysis.project_summary or "No project summary available.",
                "module_summaries": module_summaries,
                "infrastructure": infrastructure,
                "apis": apis,
                "data_flows": data_flows,
            },
            "Start Here",
        ),
        (
            "generate_architecture_doc",
            {
                "project_summary": analysis.project_summary,
                "module_summaries": module_summaries,
                "data_flows": data_flows,
                "infrastructure": infrastructure,
                "apis": apis,
            },
            "Architecture Overview",
        ),
        (
            "generate_api_doc",
            {"apis": apis, "data_flows": data_flows},
            "API Reference",
        ),
        (
            "generate_infra_doc",
            {"infrastructure": infrastructure},
            "Infrastructure",
        ),
    ]

    sections: list[Section] = []
    errors: list[tuple[str, Exception]] = []

    # Generate doc sections
    for prompt_name, kwargs, title in doc_specs:
        # Skip API doc prompt if no endpoints; write a placeholder instead
        if prompt_name == "generate_api_doc" and not analysis.api_endpoints:
            sections.append(Section(
                title=title,
                slug=_slugify(title),
                html_content="<p>No API endpoints were detected in this codebase.</p>",
            ))
            continue
        if prompt_name == "generate_infra_doc" and not analysis.infrastructure:
            sections.append(Section(
                title=title,
                slug=_slugify(title),
                html_content="<p>No infrastructure components were detected in this codebase.</p>",
            ))
            continue

        # API doc generation routes through the retry/validation helper,
        # chunking automatically when there are more endpoints than
        # API_CHUNK_SIZE.
        if prompt_name == "generate_api_doc":
            try:
                if len(analysis.api_endpoints) > API_CHUNK_SIZE:
                    section = await _generate_api_section_chunked(
                        provider, analysis, data_flows,
                    )
                else:
                    markdown_content = await _generate_api_chunk_with_retry(
                        provider,
                        analysis.api_endpoints,
                        chunk_index=1,
                        chunk_total=1,
                        data_flows_formatted=data_flows,
                    )
                    section = Section(
                        title=title,
                        slug=_slugify(title),
                        html_content=_markdown_to_html(markdown_content),
                    )
                sections.append(section)
            except LLMError as e:
                errors.append((title, e))
            continue

        try:
            section = await _generate_section(provider, prompt_name, kwargs, title)
            sections.append(section)
        except LLMError as e:
            errors.append((title, e))

    # Generate diagram sections
    for diagram_type in ("architecture", "data-flow"):
        try:
            section = await _generate_diagram_section(provider, analysis, diagram_type)
            sections.append(section)
        except LLMError as e:
            errors.append((f"{diagram_type} diagram", e))

    # Render the HTML template
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=False,  # We handle escaping ourselves; template receives pre-built HTML
    )
    template = env.get_template("doc_page.html.j2")
    page = template.render(project_name=project_name, sections=sections)

    path = store.write(".", "index.html", page)
    return path, errors
