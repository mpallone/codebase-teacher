# Codebase Teacher

AI-powered codebase teaching tool that generates documentation, lectures, quizzes, and evaluations to help onboard engineers to unfamiliar codebases.

## Quick Start

No API key needed — uses the Claude Code CLI by default.

```bash
pip install -e ".[dev]"

# Scan a codebase (use --auto for non-interactive mode)
teach scan --auto /path/to/your/project

# Run LLM-assisted analysis
teach analyze /path/to/your/project

# Generate documentation
teach generate /path/to/your/project
```

## Provider Configuration

### Claude Code CLI (default)

The default provider uses the `claude` CLI tool. No API key required — it uses your existing Claude Code authentication.

```bash
# Explicit (or just omit — it's the default)
export CODEBASE_TEACHER_PROVIDER=claude-code
```

### litellm (API key mode)

Switch to litellm for direct API access. Supports Anthropic, OpenAI, Google, and any provider litellm supports.

```bash
export CODEBASE_TEACHER_PROVIDER=litellm

# Set the API key for your chosen provider
export ANTHROPIC_API_KEY=sk-ant-...
# or
export OPENAI_API_KEY=sk-...

# Choose a model (defaults to anthropic/claude-sonnet-4-20250514)
export CODEBASE_TEACHER_MODEL=anthropic/claude-sonnet-4-20250514
```

## CLI Options

```bash
teach --provider claude-code analyze /path   # Use Claude Code CLI
teach --provider litellm analyze /path       # Use litellm with API key
teach --model anthropic/claude-sonnet-4-20250514 analyze /path  # Set model (litellm only)
teach scan --auto /path                      # Non-interactive scan (auto-select all folders)
teach --verbose analyze /path                # Verbose output
```

## iOS / Mobile Usage

Codebase Teacher works from the Claude iOS app via Claude Code. All LLM calls route through the `claude` CLI using your existing subscription — no API key needed.

```bash
teach scan --auto /path/to/project && teach analyze /path/to/project && teach generate /path/to/project
```

## Development

```bash
pip install -e ".[dev]"
pytest
```
