"""Shared test fixtures including mock LLM provider."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import AsyncIterator
from unittest.mock import AsyncMock

import pytest

from codebase_teacher.llm.provider import LLMResponse, Message, TokenUsage
from codebase_teacher.storage.database import Database


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sample_project"


class MockLLMProvider:
    """Mock LLM provider that returns canned responses for testing."""

    def __init__(self, responses: dict[str, str] | None = None):
        self._responses = responses or {}
        self._default_response = "This is a mock LLM response."
        self._calls: list[list[Message]] = []

    async def complete(
        self,
        messages: list[Message],
        temperature: float = 0.3,
        max_tokens: int | None = None,
        response_format=None,
    ) -> LLMResponse:
        self._calls.append(messages)
        # Check if any keyword in the user message matches a canned response
        user_msg = messages[-1].content if messages else ""
        for keyword, response in self._responses.items():
            if keyword.lower() in user_msg.lower():
                return LLMResponse(
                    content=response,
                    usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                    model="mock-model",
                )
        return LLMResponse(
            content=self._default_response,
            usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            model="mock-model",
        )

    async def stream(
        self,
        messages: list[Message],
        temperature: float = 0.3,
    ) -> AsyncIterator[str]:
        self._calls.append(messages)
        for word in self._default_response.split():
            yield word + " "

    @property
    def context_window(self) -> int:
        return 100_000

    @property
    def max_tokens(self) -> int:
        return 16384

    @property
    def model_name(self) -> str:
        return "mock-model"


@pytest.fixture
def mock_provider():
    """Create a mock LLM provider with useful canned responses."""
    return MockLLMProvider(
        responses={
            "summarize": (
                "Purpose: This module handles user management.\n"
                "Key abstractions: User class, database session.\n"
                "Dependencies: Flask, SQLAlchemy.\n"
                "Data flow role: Input (API handler).\n"
                "Infrastructure: PostgreSQL database."
            ),
            "detect_apis": (
                '[{"method": "GET", "path": "/api/users", "handler": "list_users", '
                '"file": "app.py", "description": "List all users"}]'
            ),
            "detect_infrastructure": (
                '[{"type": "database", "technology": "PostgreSQL", '
                '"explanation": "Relational database", "usage": "User data storage", '
                '"config": "db.prod.example.com:5432"}]'
            ),
            "trace_data_flow": (
                '[{"name": "User Creation Flow", "entry_points": ["POST /api/users"], '
                '"steps": ["Validate input", "Create user in DB", "Send welcome email"], '
                '"outputs": ["DB write", "Email sent"], '
                '"mermaid_diagram": "sequenceDiagram\\n    Client->>API: POST /api/users\\n    API->>DB: Insert user\\n    API->>Celery: send_welcome_email"}]'
            ),
            "architecture": (
                "# System Architecture\n\n"
                "This is a Flask-based REST API with PostgreSQL storage and "
                "Celery for async task processing.\n\n"
                "```mermaid\ngraph TD\n    A[Client] --> B[Flask API]\n    "
                "B --> C[PostgreSQL]\n    B --> D[Celery/Redis]\n```"
            ),
            # Matches the `generate_api_doc` prompt. Return a stub with many
            # `### ` headings so the per-chunk under-production check
            # (`_generate_api_chunk_with_retry`) is satisfied across chunk
            # sizes used in tests.
            "generate api reference documentation": "\n".join(
                f"### GET /mock-{i}\nMock endpoint {i}.\n" for i in range(30)
            ),
        }
    )


@pytest.fixture
def sample_project():
    """Path to the sample project fixture."""
    return FIXTURES_DIR


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database."""
    db = Database(tmp_path / "test.db")
    yield db
    db.close()


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory with some files."""
    project = tmp_path / "test_project"
    project.mkdir()

    # Create a simple Python file
    (project / "main.py").write_text(
        'from flask import Flask\n\napp = Flask(__name__)\n\n'
        '@app.route("/health")\ndef health():\n    return "ok"\n'
    )

    # Create a subdirectory with a file
    src = project / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "utils.py").write_text(
        "def add(a: int, b: int) -> int:\n"
        '    """Add two numbers."""\n'
        "    return a + b\n"
    )

    # Create a test directory
    tests = project / "tests"
    tests.mkdir()
    (tests / "test_utils.py").write_text(
        "from src.utils import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"
    )

    # Create requirements.txt
    (project / "requirements.txt").write_text("flask==3.0.0\nredis==5.0.0\n")

    return project
