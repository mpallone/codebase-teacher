"""Tests for eval/runner.py — clone and teach subprocess logic."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from eval.runner import RunResult, clone_or_update, load_repos, run_teach


class TestLoadRepos:
    def test_loads_yaml(self) -> None:
        repos = load_repos()
        assert isinstance(repos, dict)
        assert "flask" in repos
        assert "javalin" in repos
        assert "cask" in repos
        assert "terraform-aws-vpc" in repos

    def test_each_repo_has_required_fields(self) -> None:
        repos = load_repos()
        for slug, info in repos.items():
            assert "url" in info, f"{slug} missing 'url'"
            assert "commit" in info, f"{slug} missing 'commit'"
            assert "language" in info, f"{slug} missing 'language'"

    def test_repo_urls_are_git_urls(self) -> None:
        repos = load_repos()
        for slug, info in repos.items():
            assert info["url"].endswith(".git"), f"{slug} url should end with .git"


class TestCloneOrUpdate:
    def test_clones_new_repo(self, tmp_path: Path) -> None:
        repos_dir = tmp_path / "repos"
        with patch("eval.runner.subprocess.run") as mock_run:
            # First call: clone. Second: rev-parse HEAD to check commit.
            mock_run.side_effect = [
                MagicMock(returncode=0),  # clone
                MagicMock(returncode=0, stdout="abc123\n"),  # rev-parse
                MagicMock(returncode=0),  # fetch
                MagicMock(returncode=0),  # checkout
            ]
            # Create the dir so the function doesn't fail on path checks
            (repos_dir / "test-repo").mkdir(parents=True)
            result = clone_or_update("test-repo", "https://github.com/test/repo.git", "abc123", repos_dir)
            assert result == repos_dir / "test-repo"

    def test_skips_if_already_at_commit(self, tmp_path: Path) -> None:
        repos_dir = tmp_path / "repos"
        repo_path = repos_dir / "test-repo"
        repo_path.mkdir(parents=True)

        with patch("eval.runner.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="abc123\n")
            result = clone_or_update("test-repo", "https://example.com/repo.git", "abc123", repos_dir)
            assert result == repo_path
            # Only one call (rev-parse) since commit matches
            assert mock_run.call_count == 1


class TestRunTeach:
    def test_captures_output(self, tmp_path: Path) -> None:
        with patch("eval.runner.subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="analysis done", stderr=""),  # analyze
                MagicMock(returncode=0, stdout="generation done", stderr=""),  # generate
            ]
            result = run_teach(tmp_path)
            assert result.exit_code == 0
            assert "analysis done" in result.stdout
            assert "generation done" in result.stdout
            assert result.wall_time >= 0

    def test_returns_failure_on_analyze_error(self, tmp_path: Path) -> None:
        with patch("eval.runner.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="Error: no files"
            )
            result = run_teach(tmp_path)
            assert result.exit_code == 1
            assert "Error: no files" in result.stderr

    def test_discovers_output_files(self, tmp_path: Path) -> None:
        # Create fake teacher output
        output_dir = tmp_path / ".teacher-output" / "docs"
        output_dir.mkdir(parents=True)
        (output_dir / "architecture.md").write_text("# Architecture")
        (output_dir / "api-reference.md").write_text("# API Reference")

        with patch("eval.runner.subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="ok", stderr=""),
                MagicMock(returncode=0, stdout="ok", stderr=""),
            ]
            result = run_teach(tmp_path)
            assert "docs/architecture.md" in result.output_files
            assert "docs/api-reference.md" in result.output_files
