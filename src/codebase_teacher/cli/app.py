"""Top-level CLI application using Click."""

from __future__ import annotations

import click
from rich.console import Console

from codebase_teacher import __version__

console = Console()


@click.group()
@click.version_option(version=__version__)
@click.option("--model", envvar="CODEBASE_TEACHER_MODEL", default=None, help="LLM model (litellm format)")
@click.option(
    "--provider", envvar="CODEBASE_TEACHER_PROVIDER", default=None,
    type=click.Choice(["litellm", "claude-code"]),
    help="LLM backend: 'litellm' (API key) or 'claude-code' (CLI subscription)",
)
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.pass_context
def cli(ctx: click.Context, model: str | None, provider: str | None, verbose: bool) -> None:
    """Codebase Teacher — AI-powered codebase learning tool."""
    ctx.ensure_object(dict)
    ctx.obj["model"] = model
    ctx.obj["provider"] = provider
    ctx.obj["verbose"] = verbose


# Import and register subcommands
from codebase_teacher.cli.scan import scan  # noqa: E402
from codebase_teacher.cli.analyze import analyze  # noqa: E402
from codebase_teacher.cli.generate import generate  # noqa: E402

cli.add_command(scan)
cli.add_command(analyze)
cli.add_command(generate)
