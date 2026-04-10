"""CLI for the eval harness: `python -m eval <command>`."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from eval.runner import clone_or_update, load_repos, run_teach


CACHE_DIR = Path(__file__).parent / ".cache"


@click.group()
def cli() -> None:
    """Evaluate codebase-teacher against real-world repositories."""


@cli.command()
@click.argument("slug", required=False)
def clone(slug: str | None) -> None:
    """Clone (or update) a test repo by slug, or all repos if no slug given."""
    repos = load_repos()
    targets = _resolve_targets(repos, slug)
    for name, info in targets.items():
        click.echo(f"Cloning {name}...")
        path = clone_or_update(name, info["url"], info["commit"], CACHE_DIR / "repos")
        click.echo(f"  -> {path}")


@cli.command()
@click.argument("slug", required=False)
def analyze(slug: str | None) -> None:
    """Run teach analyze + generate against a cloned repo (or all repos)."""
    repos = load_repos()
    targets = _resolve_targets(repos, slug)
    for name, info in targets.items():
        repo_path = CACHE_DIR / "repos" / name
        if not repo_path.exists():
            click.echo(f"Repo {name} not cloned yet. Run `python -m eval clone {name}` first.")
            sys.exit(1)
        click.echo(f"Analyzing {name}...")
        result = run_teach(repo_path)
        click.echo(f"  exit_code={result.exit_code}  wall_time={result.wall_time:.1f}s")
        if result.exit_code != 0:
            click.echo(f"  stderr: {result.stderr[-500:]}")


@cli.command()
@click.argument("slug", required=False)
def packet(slug: str | None) -> None:
    """Build review packets from existing teach output (or for all repos)."""
    from eval.packet import build_packet

    repos = load_repos()
    targets = _resolve_targets(repos, slug)
    for name, info in targets.items():
        repo_path = CACHE_DIR / "repos" / name
        output_dir = repo_path / ".teacher-output"
        if not output_dir.exists():
            click.echo(f"No teach output for {name}. Run `python -m eval analyze {name}` first.")
            sys.exit(1)
        click.echo(f"Building packet for {name}...")
        run_dir = _get_latest_run_dir() / name
        run_dir.mkdir(parents=True, exist_ok=True)
        packet_path = build_packet(
            slug=name,
            repo_path=repo_path,
            output_dir=output_dir,
            dest=run_dir / "packet.md",
            language=info.get("language", "unknown"),
        )
        click.echo(f"  -> {packet_path}")


@cli.command()
@click.option("--repos", default="all", help="Comma-separated repo slugs or 'all'")
def prep(repos: str) -> None:
    """Clone, analyze, and build packets for repos (the main command)."""
    from eval.packet import build_packet

    all_repos = load_repos()
    if repos == "all":
        targets = all_repos
    else:
        slugs = [s.strip() for s in repos.split(",")]
        targets = {s: all_repos[s] for s in slugs if s in all_repos}
        missing = [s for s in slugs if s not in all_repos]
        if missing:
            click.echo(f"Unknown repos: {', '.join(missing)}")
            click.echo(f"Available: {', '.join(all_repos.keys())}")
            sys.exit(1)

    run_dir = _create_run_dir()
    click.echo(f"Run directory: {run_dir}\n")

    for name, info in targets.items():
        click.echo(f"=== {name} ({info.get('language', '?')}) ===")

        # Clone
        click.echo("  Cloning...")
        repo_path = clone_or_update(name, info["url"], info["commit"], CACHE_DIR / "repos")

        # Analyze
        click.echo("  Running teach analyze + generate...")
        result = run_teach(repo_path)
        click.echo(f"  exit_code={result.exit_code}  wall_time={result.wall_time:.1f}s")
        if result.exit_code != 0:
            click.echo(f"  FAILED: {result.stderr[-500:]}")
            # Copy whatever output exists anyway
            slug_dir = run_dir / name
            slug_dir.mkdir(parents=True, exist_ok=True)
            (slug_dir / "error.txt").write_text(
                f"exit_code={result.exit_code}\n\nSTDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
            )
            continue

        # Build packet
        click.echo("  Building review packet...")
        output_dir = repo_path / ".teacher-output"
        slug_dir = run_dir / name
        slug_dir.mkdir(parents=True, exist_ok=True)

        # Copy teacher-output into run dir for archival
        _copy_tree(output_dir, slug_dir / "teacher-output")

        build_packet(
            slug=name,
            repo_path=repo_path,
            output_dir=output_dir,
            dest=slug_dir / "packet.md",
            language=info.get("language", "unknown"),
        )
        click.echo(f"  Packet: {slug_dir / 'packet.md'}")
        click.echo()

    click.echo(f"Done. Review packets at: {run_dir}")
    click.echo("Run /eval-loop in Claude Code to judge and fix.")


def _resolve_targets(repos: dict, slug: str | None) -> dict:
    if slug is None:
        return repos
    if slug not in repos:
        click.echo(f"Unknown repo: {slug}")
        click.echo(f"Available: {', '.join(repos.keys())}")
        sys.exit(1)
    return {slug: repos[slug]}


def _create_run_dir() -> Path:
    """Create a timestamped run directory and update the `latest` symlink."""
    import datetime

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = CACHE_DIR / "runs" / ts
    run_dir.mkdir(parents=True, exist_ok=True)

    latest = CACHE_DIR / "runs" / "latest"
    if latest.is_symlink() or latest.exists():
        latest.unlink()
    latest.symlink_to(run_dir.resolve())

    return run_dir


def _get_latest_run_dir() -> Path:
    """Get or create the latest run directory."""
    latest = CACHE_DIR / "runs" / "latest"
    if latest.is_symlink() and latest.exists():
        return latest.resolve()
    return _create_run_dir()


def _copy_tree(src: Path, dst: Path) -> None:
    """Copy a directory tree, overwriting destination."""
    import shutil

    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
