# Codebase Teacher

AI-powered codebase analysis tool that generates architecture documentation, API references, infrastructure guides, and Mermaid diagrams to help onboard engineers to unfamiliar codebases.

## Prerequisites

- **Python 3.11+**
- **Claude Code CLI** (`claude`) — installed and authenticated. This is the default LLM provider; no API key needed.
  - Alternatively, use the `litellm` provider with an API key (see [Provider Configuration](#provider-configuration)).

## Quick Start

```bash
pip install -e .

# 1. Scan — discover folders, classify files, detect dependencies
teach scan --auto /path/to/your/project

# 2. Analyze — LLM-assisted code understanding (AST parsing + summarization)
teach analyze /path/to/your/project

# 3. Generate — produce documentation and diagrams
teach generate /path/to/your/project
```

Output is written to `.teacher-output/` inside the target project:

```
.teacher-output/
├── docs/
│   ├── architecture.md      # System overview with Mermaid diagrams
│   ├── api-reference.md     # HTTP endpoints, gRPC, CLI commands
│   └── infrastructure.md    # Databases, queues, cloud services
└── diagrams/
    ├── architecture.md      # Mermaid architecture diagram
    └── data-flow.md         # Mermaid data flow / sequence diagrams
```

## Commands

### `teach scan <path>`

Discovers the project structure, classifies files by type (source, config, test, infra, etc.), and detects dependencies.

- **Interactive mode** (default): Prompts you to mark each top-level folder as relevant or not.
- **`--auto` flag**: Auto-selects all folders. Required for headless/mobile use.

### `teach analyze <path>`

Runs an 8-step pipeline combining deterministic AST parsing with LLM-assisted analysis:

1. AST parsing (functions, classes, imports)
2. AST-based API detection (decorators like `@app.route`)
3. File summarization (LLM)
4. Module summarization (LLM)
5. Project summary (LLM)
6. LLM-based API detection (catches what AST missed)
7. Infrastructure detection (LLM)
8. Data flow tracing (LLM)

Results are cached in `.teacher/teacher.db` — re-running skips LLM calls if source files haven't changed.

### `teach generate <path>`

Generates documentation and diagrams from cached analysis results.

- `--type all` (default) — generate both docs and diagrams
- `--type docs` — generate only documentation
- `--type diagrams` — generate only diagrams

## Provider Configuration

### Claude Code CLI (default)

Uses the `claude` CLI tool. No API key required — it uses your existing Claude Code authentication.

```bash
# Explicit (or just omit — it's the default)
export CODEBASE_TEACHER_PROVIDER=claude-code
```

### litellm (API key mode)

Uses litellm for direct API access. Supports Anthropic, OpenAI, Google, and any provider litellm supports.

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
# Provider and model
teach --provider claude-code analyze /path    # Use Claude Code CLI (default)
teach --provider litellm analyze /path        # Use litellm with API key
teach --model anthropic/claude-sonnet-4-20250514 analyze /path  # Set model (litellm only)

# Scan modes
teach scan /path                              # Interactive folder selection
teach scan --auto /path                       # Auto-select all folders

# Generate options
teach generate /path                          # Generate docs + diagrams
teach generate --type docs /path              # Docs only
teach generate --type diagrams /path          # Diagrams only

# General
teach --verbose analyze /path                 # Verbose output
teach --version                               # Show version
```

## Environment Variables

All settings use the `CODEBASE_TEACHER_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `CODEBASE_TEACHER_PROVIDER` | `claude-code` | LLM backend: `claude-code` or `litellm` |
| `CODEBASE_TEACHER_MODEL` | `anthropic/claude-sonnet-4-20250514` | Model (litellm provider only) |
| `CODEBASE_TEACHER_TEMPERATURE` | `0.3` | LLM temperature (0.0–2.0) |
| `CODEBASE_TEACHER_MAX_TOKENS` | `16384` | Max output tokens per LLM call |
| `CODEBASE_TEACHER_MAX_CONCURRENT_LLM_CALLS` | `5` | Concurrent LLM call limit |
| `CODEBASE_TEACHER_OUTPUT_DIR` | `.teacher-output` | Output directory (relative to target project) |
| `CODEBASE_TEACHER_DB_DIR` | `.teacher` | Cache database directory (relative to target project) |
| `CODEBASE_TEACHER_VERBOSE` | `false` | Enable verbose logging |

## iOS / Mobile Usage

Codebase Teacher works from the Claude iOS app via Claude Code. All LLM calls route through the `claude` CLI using your existing subscription — no API key needed. Use `--auto` to skip interactive prompts:

```bash
teach scan --auto /path/to/project && teach analyze /path/to/project && teach generate /path/to/project
```

## Development

```bash
pip install -e ".[dev]"
pytest
```
