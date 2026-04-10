"""Tests for eval/packet.py — review packet generation.

Uses the real sample_project fixture (no LLM calls needed).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from eval.packet import (
    _all_source_files,
    _build_tree,
    _load_rubric,
    _read_generated_docs,
    _read_readme,
    build_packet,
)


FIXTURES = Path(__file__).parent.parent / "fixtures" / "sample_project"


class TestLoadRubric:
    def test_loads_rubric_text(self) -> None:
        rubric = _load_rubric()
        assert "factual_accuracy" in rubric
        assert "completeness" in rubric
        assert "pass" in rubric
        assert "fail" in rubric


class TestReadReadme:
    def test_returns_empty_for_no_readme(self, tmp_path: Path) -> None:
        assert _read_readme(tmp_path) == ""

    def test_reads_readme_md(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# Hello World")
        assert "Hello World" in _read_readme(tmp_path)


class TestBuildTree:
    def test_builds_tree_for_sample_project(self) -> None:
        tree = _build_tree(FIXTURES)
        assert "app.py" in tree
        assert "models.py" in tree

    def test_skips_hidden_dirs(self, tmp_path: Path) -> None:
        (tmp_path / ".hidden").mkdir()
        (tmp_path / ".hidden" / "secret.py").write_text("")
        (tmp_path / "visible.py").write_text("")
        tree = _build_tree(tmp_path)
        assert "visible.py" in tree
        assert ".hidden" not in tree


class TestAllSourceFiles:
    def test_includes_python_files(self) -> None:
        result = _all_source_files(FIXTURES, "python")
        assert "app.py" in result
        assert "models.py" in result

    def test_includes_all_files_no_truncation(self) -> None:
        result = _all_source_files(FIXTURES, "python")
        # Should say "All N source files included", not "budget exceeded"
        assert "source files included" in result
        assert "budget exceeded" not in result
        assert "truncated" not in result
        assert "not shown" not in result

    def test_respects_language_filter(self, tmp_path: Path) -> None:
        (tmp_path / "Main.java").write_text("public class Main {}")
        (tmp_path / "script.py").write_text("print('hi')")
        result = _all_source_files(tmp_path, "java")
        assert "Main.java" in result
        assert "script.py" not in result

    def test_returns_message_when_no_files(self, tmp_path: Path) -> None:
        result = _all_source_files(tmp_path, "python")
        assert "No source files found" in result


class TestReadGeneratedDocs:
    def test_returns_message_when_no_output(self, tmp_path: Path) -> None:
        result = _read_generated_docs(tmp_path / "nonexistent")
        assert "No teach output found" in result

    def test_reads_doc_files(self, tmp_path: Path) -> None:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "architecture.md").write_text("# Architecture\nThis is the arch doc.")
        result = _read_generated_docs(tmp_path)
        assert "architecture.md" in result
        assert "This is the arch doc" in result

    def test_reads_diagram_files(self, tmp_path: Path) -> None:
        diagrams_dir = tmp_path / "diagrams"
        diagrams_dir.mkdir()
        (diagrams_dir / "data-flow.md").write_text("```mermaid\ngraph TD\n```")
        result = _read_generated_docs(tmp_path)
        assert "data-flow.md" in result
        assert "mermaid" in result


class TestBuildPacket:
    def test_builds_packet_for_sample_project(self, tmp_path: Path) -> None:
        # Create fake teacher output
        output_dir = tmp_path / "teacher-output"
        docs = output_dir / "docs"
        docs.mkdir(parents=True)
        (docs / "architecture.md").write_text("# Architecture\nFlask app with Celery.")

        dest = tmp_path / "packet.md"
        result = build_packet(
            slug="sample",
            repo_path=FIXTURES,
            output_dir=output_dir,
            dest=dest,
            language="python",
        )

        assert result == dest
        assert dest.exists()
        content = dest.read_text()

        # Check packet contains expected sections
        assert "Eval Packet: sample" in content
        assert "Judging Rubric" in content
        assert "Directory Structure" in content
        assert "Source Code (complete)" in content
        assert "Generated Documentation" in content
        assert "app.py" in content
        assert "Flask app with Celery" in content
