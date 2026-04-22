"""Tests for the single-page HTML generator."""

from __future__ import annotations

import pytest

from codebase_teacher.generator.html import (
    _convert_mermaid_blocks,
    _generate_api_section_chunked,
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


class _ScriptedProvider:
    """Test helper: returns one scripted response per call."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self._calls: list[list] = []

    async def complete(self, messages, temperature=None, max_tokens=None, response_format=None):
        from codebase_teacher.llm.provider import LLMResponse, TokenUsage

        self._calls.append(messages)
        content = self._responses.pop(0) if self._responses else ""
        return LLMResponse(
            content=content,
            usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            model="scripted",
        )

    @property
    def context_window(self) -> int:
        return 100_000

    @property
    def max_tokens(self) -> int:
        return 16384

    @property
    def temperature(self) -> float:
        return 0.3

    @property
    def model_name(self) -> str:
        return "scripted"


def _chunk_response(start: int, count: int) -> str:
    return "\n".join(f"### GET /api/item-{start + i}\nDetail.\n" for i in range(count))


@pytest.mark.asyncio
async def test_html_api_section_preserves_all_endpoints_across_chunks(tmp_path):
    """Every endpoint in every chunk must appear in the assembled HTML section."""
    from codebase_teacher.generator.docs import API_CHUNK_SIZE

    total = API_CHUNK_SIZE * 3
    endpoints = [
        APIEndpoint(
            method="GET",
            path=f"/api/item-{i}",
            handler=f"get_item_{i}",
            file="routes.py",
            description=f"Get item {i}",
        )
        for i in range(total)
    ]
    analysis = AnalysisResult(project_summary="t", api_endpoints=endpoints)

    scripted = [_chunk_response(i, API_CHUNK_SIZE) for i in range(0, total, API_CHUNK_SIZE)]
    provider = _ScriptedProvider(scripted)

    section = await _generate_api_section_chunked(provider, analysis, "No data flows.")

    assert section.slug == "api-reference"
    for i in range(total):
        assert f"/api/item-{i}" in section.html_content


@pytest.mark.asyncio
async def test_html_api_section_retries_underproduced_chunk(tmp_path):
    """Empty first response on a chunk should trigger one retry in the HTML path."""
    from codebase_teacher.generator.docs import API_CHUNK_SIZE

    total = API_CHUNK_SIZE * 2
    endpoints = [
        APIEndpoint(
            method="GET",
            path=f"/api/item-{i}",
            handler=f"get_item_{i}",
            file="routes.py",
            description=f"Get item {i}",
        )
        for i in range(total)
    ]
    analysis = AnalysisResult(project_summary="t", api_endpoints=endpoints)

    scripted = [
        _chunk_response(0, API_CHUNK_SIZE),
        "",  # chunk 2 under-produced
        _chunk_response(API_CHUNK_SIZE, API_CHUNK_SIZE),  # retry
    ]
    provider = _ScriptedProvider(scripted)

    section = await _generate_api_section_chunked(provider, analysis, "No data flows.")

    assert len(provider._calls) == 3
    for i in range(total):
        assert f"/api/item-{i}" in section.html_content


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
        assert '<h1 class="page-title">my-cool-project</h1>' in content
    finally:
        db.close()


@pytest.mark.asyncio
async def test_html_section_recovers_after_transient_llm_error(
    mock_provider, tmp_path, monkeypatch
):
    """A transient LLMError on one section should retry and succeed, not drop the section."""
    from unittest.mock import AsyncMock

    from codebase_teacher.core.exceptions import LLMError

    # Patch asyncio.sleep so the backoff doesn't slow the test.
    monkeypatch.setattr(
        "codebase_teacher.llm.provider.asyncio.sleep", AsyncMock()
    )

    # Wrap the mock provider so the first call to the Infrastructure prompt
    # raises LLMError, then subsequent calls succeed via the normal canned path.
    original_complete = mock_provider.complete
    failed_once = {"done": False}

    async def flaky_complete(messages, **kwargs):
        user_msg = messages[-1].content if messages else ""
        # Trigger a transient error on the Infrastructure prompt exactly once.
        if user_msg.startswith("Generate infrastructure documentation.") and not failed_once["done"]:
            failed_once["done"] = True
            raise LLMError("claude CLI exited with code 1: transient")
        return await original_complete(messages, **kwargs)

    mock_provider.complete = flaky_complete

    store, db = _make_store(tmp_path)
    try:
        analysis = _make_analysis()
        path, errors = await generate_html_page(
            mock_provider, analysis, store, project_name="retry-test",
        )

        content = path.read_text()
        # The Infrastructure section should survive the transient failure.
        assert 'id="infrastructure"' in content
        # No unrecoverable errors should be reported.
        assert errors == []
        # Confirm we did hit the failure path.
        assert failed_once["done"] is True
    finally:
        db.close()


@pytest.mark.asyncio
async def test_html_section_gives_up_after_exhausting_retries(
    mock_provider, tmp_path, monkeypatch
):
    """If every retry fails, the section is recorded in errors and others still render."""
    from unittest.mock import AsyncMock

    from codebase_teacher.core.exceptions import LLMError

    monkeypatch.setattr(
        "codebase_teacher.llm.provider.asyncio.sleep", AsyncMock()
    )

    original_complete = mock_provider.complete

    async def always_failing_infra(messages, **kwargs):
        user_msg = messages[-1].content if messages else ""
        if user_msg.startswith("Generate infrastructure documentation."):
            raise LLMError("claude CLI exited with code 1: persistent")
        return await original_complete(messages, **kwargs)

    mock_provider.complete = always_failing_infra

    store, db = _make_store(tmp_path)
    try:
        analysis = _make_analysis()
        path, errors = await generate_html_page(
            mock_provider, analysis, store, project_name="retry-fail-test",
        )

        # Infrastructure section failure is reported, but index.html still produced.
        assert path.exists()
        assert any(title == "Infrastructure" for title, _ in errors)
        content = path.read_text()
        # Other sections still rendered.
        assert 'id="start-here"' in content
        assert 'id="api-reference"' in content
    finally:
        db.close()
