# Codebase Teacher

AI-powered codebase teaching tool that generates documentation, lectures, quizzes, and evaluations to help onboard engineers to unfamiliar codebases.

## Quick Start

```bash
pip install -e ".[dev]"

# Scan a codebase
teach scan /path/to/your/project

# Run LLM-assisted analysis
teach analyze /path/to/your/project

# Generate documentation
teach generate /path/to/your/project
```

## Configuration

Set your LLM provider API key:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
# or
export OPENAI_API_KEY=sk-...
```

Choose a model (defaults to `anthropic/claude-sonnet-4-20250514`):

```bash
export CODEBASE_TEACHER_MODEL=anthropic/claude-sonnet-4-20250514
```

## Development

```bash
pip install -e ".[dev]"
pytest
```
