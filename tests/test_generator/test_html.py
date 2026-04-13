"""Tests for the single-page HTML generator."""

from __future__ import annotations

import pytest

from codebase_teacher.generator.html import (
    _convert_mermaid_blocks,
    _markdown_to_html,
    _sanitize_mermaid,
    _slugify,
    generate_html_page,
)
from codebase_teacher.storage.artifact_store import ArtifactStore
from codebase_teacher.storage.database import Database
from codebase_teacher.storage.models import (
    AnalysisResult,
    APIEndpoint,
    DataFlow,
    InfraComponent,
)


def _make_store(tmp_path) -> tuple[ArtifactStore, Database]:
    db = Database(tmp_path / "test.db")
    project_id = db.get_or_create_project(str(tmp_path), "test_project")
    store = ArtifactStore(tmp_path / "output", db, project_id)
    return store, db


def _make_analysis() -> AnalysisResult:
    return AnalysisResult(
        project_summary="A small Flask API that manages users and sends welcome emails.",
        module_summaries={
            "app.py": "Flask entry point. Wires routes to user handlers.",
            "users.py": "User CRUD logic backed by PostgreSQL.",
            "tasks.py": "Celery tasks for sending emails.",
        },
        api_endpoints=[
            APIEndpoint(
                method="POST",
                path="/api/users",
                handler="create_user",
                file="users.py",
                description="Create a new user",
            ),
        ],
        infrastructure=[
            InfraComponent(
                type="database",
                technology="PostgreSQL",
                explanation="Relational database.",
                usage="Stores user records.",
                config="DATABASE_URL env var",
            ),
        ],
        data_flows=[
            DataFlow(
                name="User signup",
                entry_points=["POST /api/users"],
                steps=["Validate input", "Insert into DB", "Enqueue welcome email"],
                outputs=["DB write", "Celery task"],
                mermaid_diagram=(
                    "sequenceDiagram\n"
                    "    Client->>API: POST /api/users\n"
                    "    API->>DB: Insert user\n"
                    "    API->>Celery: send_welcome_email"
                ),
            ),
        ],
    )


# --- Unit tests for helpers ---


class TestSanitizeMermaid:
    def test_strips_whitespace(self):
        assert _sanitize_mermaid("  graph TD\n    A-->B  ") == "graph TD\n    A-->B"

    def test_replaces_smart_quotes(self):
        result = _sanitize_mermaid('A["\u201cHello\u201d"]')
        assert '\u201c' not in result
        assert '"Hello"' in result

    def test_replaces_smart_single_quotes(self):
        result = _sanitize_mermaid("A['\u2018it\u2019s']")
        assert "\u2018" not in result
        assert "'it's'" in result

    def test_replaces_em_dash(self):
        result = _sanitize_mermaid("A \u2014 B")
        assert "\u2014" not in result
        assert "A -- B" in result

    def test_replaces_en_dash(self):
        result = _sanitize_mermaid("A \u2013> B")
        assert "\u2013" not in result
        assert "A -> B" in result


class TestSlugify:
    def test_basic(self):
        assert _slugify("Architecture Overview") == "architecture-overview"

    def test_special_chars(self):
        assert _slugify("API Reference!") == "api-reference"

    def test_multiple_spaces(self):
        assert _slugify("Data  Flow  Diagrams") == "data-flow-diagrams"


class TestMarkdownToHtml:
    def test_basic_paragraph(self):
        result = _markdown_to_html("Hello **world**")
        assert "<strong>world</strong>" in result

    def test_fenced_code_block(self):
        md = "```python\nprint('hi')\n```"
        result = _markdown_to_html(md)
        assert "<code" in result

    def test_table(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        result = _markdown_to_html(md)
        assert "<table>" in result

    def test_mermaid_block_converted(self):
        md = "```mermaid\ngraph TD\n    A-->B\n```"
        result = _markdown_to_html(md)
        assert '<pre class="mermaid">' in result
        assert "language-mermaid" not in result
        assert "A-->B" in result


class TestConvertMermaidBlocks:
    def test_converts_mermaid_code_block(self):
        html = '<pre><code class="language-mermaid">graph TD\n    A-->B</code></pre>'
        result = _convert_mermaid_blocks(html)
        assert '<pre class="mermaid">' in result
        assert "A-->B" in result
        assert "<code" not in result

    def test_leaves_non_mermaid_code_blocks_alone(self):
        html = '<pre><code class="language-python">print("hi")</code></pre>'
        result = _convert_mermaid_blocks(html)
        assert result == html

    def test_handles_html_entities_in_mermaid(self):
        html = '<pre><code class="language-mermaid">A --&gt; B</code></pre>'
        result = _convert_mermaid_blocks(html)
        assert "A --> B" in result


# --- Integration tests ---


@pytest.mark.asyncio
async def test_generate_html_page_creates_index_html(mock_provider, tmp_path):
    store, db = _make_store(tmp_path)
    try:
        analysis = _make_analysis()
        path, errors = await generate_html_page(
            mock_provider, analysis, store, project_name="test-project",
        )

        assert path.exists()
        assert path.name == "index.html"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_html_contains_all_sections(mock_provider, tmp_path):
    store, db = _make_store(tmp_path)
    try:
        analysis = _make_analysis()
        path, errors = await generate_html_page(
            mock_provider, analysis, store, project_name="test-project",
        )
        content = path.read_text()

        assert "Start Here" in content
        assert "Architecture Overview" in content
        assert "API Reference" in content
        assert "Infrastructure" in content
        assert "Architecture Diagram" in content
        assert "Data Flow Diagrams" in content
    finally:
        db.close()


@pytest.mark.asyncio
async def test_html_has_mermaid_script(mock_provider, tmp_path):
    store, db = _make_store(tmp_path)
    try:
        analysis = _make_analysis()
        path, _ = await generate_html_page(
            mock_provider, analysis, store, project_name="test-project",
        )
        content = path.read_text()

        assert "mermaid.min.js" in content
        assert "cdn.jsdelivr.net" in content
    finally:
        db.close()


@pytest.mark.asyncio
async def test_html_has_mermaid_error_recovery(mock_provider, tmp_path):
    store, db = _make_store(tmp_path)
    try:
        analysis = _make_analysis()
        path, _ = await generate_html_page(
            mock_provider, analysis, store, project_name="test-project",
        )
        content = path.read_text()

        # Error recovery: individual rendering with fallback
        assert "mermaid.parse" in content
        assert "mermaid-error" in content
        # Pinned version
        assert "mermaid@11.4.1" in content
    finally:
        db.close()


@pytest.mark.asyncio
async def test_mermaid_blocks_in_output(mock_provider, tmp_path):
    store, db = _make_store(tmp_path)
    try:
        analysis = _make_analysis()
        path, _ = await generate_html_page(
            mock_provider, analysis, store, project_name="test-project",
        )
        content = path.read_text()

        # Data flow diagram section should have mermaid pre tags
        assert '<pre class="mermaid">' in content
    finally:
        db.close()


@pytest.mark.asyncio
async def test_html_has_sidebar_nav(mock_provider, tmp_path):
    store, db = _make_store(tmp_path)
    try:
        analysis = _make_analysis()
        path, _ = await generate_html_page(
            mock_provider, analysis, store, project_name="test-project",
        )
        content = path.read_text()

        assert '<nav class="sidebar"' in content
        assert 'href="#start-here"' in content
        assert 'href="#architecture-overview"' in content
    finally:
        db.close()


@pytest.mark.asyncio
async def test_html_has_theme_toggle(mock_provider, tmp_path):
    store, db = _make_store(tmp_path)
    try:
        analysis = _make_analysis()
        path, _ = await generate_html_page(
            mock_provider, analysis, store, project_name="test-project",
        )
        content = path.read_text()

        assert "toggleTheme" in content
        assert "theme-toggle" in content
    finally:
        db.close()


@pytest.mark.asyncio
async def test_html_has_responsive_meta(mock_provider, tmp_path):
    store, db = _make_store(tmp_path)
    try:
        analysis = _make_analysis()
        path, _ = await generate_html_page(
            mock_provider, analysis, store, project_name="test-project",
        )
        content = path.read_text()

        assert 'name="viewport"' in content
        assert "width=device-width" in content
    finally:
        db.close()


@pytest.mark.asyncio
async def test_html_handles_empty_analysis(mock_provider, tmp_path):
    store, db = _make_store(tmp_path)
    try:
        analysis = AnalysisResult()
        path, errors = await generate_html_page(
            mock_provider, analysis, store, project_name="empty-project",
        )

        assert path.exists()
        content = path.read_text()
        assert "No API endpoints were detected" in content
        assert "No infrastructure components were detected" in content
    finally:
        db.close()


@pytest.mark.asyncio
async def test_html_api_section_chunked_for_many_endpoints(mock_provider, tmp_path):
    store, db = _make_store(tmp_path)
    try:
        # Create analysis with 25 endpoints (> API_CHUNK_SIZE of 20)
        from codebase_teacher.generator.docs import API_CHUNK_SIZE
        endpoints = [
            APIEndpoint(
                method="GET",
                path=f"/api/item-{i}",
                handler=f"get_item_{i}",
                file="routes.py",
                description=f"Get item {i}",
            )
            for i in range(API_CHUNK_SIZE + 5)
        ]
        analysis = AnalysisResult(
            project_summary="A test project.",
            module_summaries={"routes.py": "API routes."},
            api_endpoints=endpoints,
            infrastructure=[
                InfraComponent(
                    type="framework", technology="Flask",
                    explanation="Web framework.", usage="Serves API.", config="N/A",
                ),
            ],
        )

        path, errors = await generate_html_page(
            mock_provider, analysis, store, project_name="chunked-test",
        )

        content = path.read_text()
        assert "API Reference" in content
        # Provider should be called more times than with small endpoint sets
        # (overview + architecture + API chunk 1 + API chunk 2 + infra + diagrams)
        assert len(mock_provider._calls) >= 6
    finally:
        db.close()


@pytest.mark.asyncio
async def test_html_project_name_in_title(mock_provider, tmp_path):
    store, db = _make_store(tmp_path)
    try:
        analysis = _make_analysis()
        path, _ = await generate_html_page(
            mock_provider, analysis, store, project_name="my-cool-project",
        )
        content = path.read_text()

        assert "my-cool-project" in content
        assert "<title>" in content
    finally:
        db.close()
