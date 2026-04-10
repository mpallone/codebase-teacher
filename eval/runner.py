"""Clone repos and run teach analyze + generate."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class RunResult:
    """Result of running teach against a repo."""

    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    wall_time: float = 0.0
    output_files: list[str] = field(default_factory=list)


def load_repos() -> dict:
    """Load repo definitions from repos.yaml."""
    repos_file = Path(__file__).parent / "repos.yaml"
    with open(repos_file) as f:
        return yaml.safe_load(f)


def clone_or_update(slug: str, url: str, commit: str, repos_dir: Path) -> Path:
    """Shallow-clone a repo and reset to the pinned commit.

    If the repo already exists and is at the right commit, this is a no-op.
    """
    repo_path = repos_dir / slug
    repos_dir.mkdir(parents=True, exist_ok=True)

    if repo_path.exists():
        # Check if already at the right commit
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip() == commit:
            return repo_path
        # Fetch and reset to the pinned commit
        subprocess.run(
            ["git", "fetch", "origin", commit, "--depth=1"],
            cwd=repo_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "checkout", commit],
            cwd=repo_path,
            capture_output=True,
        )
    else:
        # Clone with minimal history
        subprocess.run(
            ["git", "clone", "--depth=1", url, str(repo_path)],
            capture_output=True,
            check=True,
        )
        # Fetch the specific commit if HEAD isn't it
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        if result.stdout.strip() != commit:
            subprocess.run(
                ["git", "fetch", "origin", commit, "--depth=1"],
                cwd=repo_path,
                capture_output=True,
            )
            subprocess.run(
                ["git", "checkout", commit],
                cwd=repo_path,
                capture_output=True,
            )

    return repo_path


def run_teach(repo_path: Path, provider: str = "litellm") -> RunResult:
    """Run teach analyze + generate against a repo.

    Skips `teach scan` (interactive). analyze falls back to root
    directory when no scan data exists (analyze.py:50-56).

    Args:
        repo_path: Path to the cloned repo.
        provider: LLM backend — 'litellm' (API key) or 'claude-code' (CLI subscription).
    """
    result = RunResult()
    start = time.monotonic()

    # Run analyze
    cmd = ["teach", "--provider", provider, "analyze", str(repo_path)]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=600,  # 10 minute timeout
    )
    result.stdout = proc.stdout
    result.stderr = proc.stderr
    result.exit_code = proc.returncode

    if proc.returncode != 0:
        result.wall_time = time.monotonic() - start
        return result

    # Run generate
    proc = subprocess.run(
        ["teach", "generate", str(repo_path)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    result.stdout += "\n--- generate ---\n" + proc.stdout
    result.stderr += proc.stderr
    if proc.returncode != 0:
        result.exit_code = proc.returncode

    result.wall_time = time.monotonic() - start

    # Discover output files
    output_dir = repo_path / ".teacher-output"
    if output_dir.exists():
        result.output_files = [
            str(p.relative_to(output_dir))
            for p in output_dir.rglob("*")
            if p.is_file()
        ]

    return result
