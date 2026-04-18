# Codebase Teacher

**Hosted report:** https://mpallone.github.io/codebase-teacher/

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
│   ├── overview.md          # "Start Here" — plain-language intro + walkthrough
│   ├── architecture.md      # System overview with Mermaid diagrams
│   ├── api-reference.md     # HTTP endpoints, gRPC, CLI commands
│   └── infrastructure.md    # Databases, queues, cloud services
└── diagrams/
    ├── architecture.md      # Mermaid architecture diagram
    └── data-flow.md         # Mermaid data flow / sequence diagrams
```

Start with `docs/overview.md` — it's a short, friendly tour of what the
codebase does, why it exists, and how the major pieces connect. Then dive into
`architecture.md` for the deeper design details.

## Tailoring output with `LEARNER-INFO.md`

Drop an optional `LEARNER-INFO.md` file at the root of the project being analyzed
to tell the tool what you care about. Its contents are passed as high-priority
context to every analysis and doc-generation prompt, so the output emphasizes
your priorities and treats tangential components as supporting context.

Example: running across a set of repos that includes dependencies you don't care
much about:

```markdown
# LEARNER-INFO

I'm the author of the `orders` service; treat `orders` and `checkout` as
root repos. Other repos (users, inventory, payments) are dependencies —
only explain them as needed to describe flows that originate in `orders`.
I care most about data flow and failure modes, less about framework plumbing.
```

The file is limited to 20,000 characters (oversized files cause `teach scan`
and `teach analyze` to exit with an explicit error rather than silently drop
context). Editing `LEARNER-INFO.md` invalidates the analyze cache so the next
`teach analyze` run picks up the new priorities.

## Commands

### `teach scan <path>`

Discovers the project structure, classifies files by type (source, config, test, infra, etc.), and detects dependencies.

- **Interactive mode** (default): Prompts you to mark each top-level folder as relevant or not.
- **`--auto` flag**: Auto-selects all folders. Required for headless/mobile use.
- **`--folders-file <path>` flag**: Read the relevant-folder list from a file instead of being prompted. One directory per line, absolute or relative to `<path>`. Blank lines and lines starting with `#` are ignored. Mutually exclusive with `--auto`.

  Example file contents:

  ```
  # Folders to scan, relative to the project root
  src
  services/api
  /abs/path/to/shared-lib
  ```

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
teach scan --folders-file dirs.txt /path      # Read folder list from a file

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
| `CODEBASE_TEACHER_TEMPERATURE` | `0.3` | LLM sampling temperature (0.0–2.0). Forwarded to the model by the `litellm` provider only — the `claude-code` provider accepts it for consistency but cannot pass it to the `claude` CLI (the CLI has no temperature flag). |
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

## Example

Running against the included sample project (a small Flask API with Celery tasks):

```bash
$ teach scan --auto tests/fixtures/sample_project

Scanning codebase: tests/fixtures/sample_project

Step 1: Folder Discovery
Auto-selected 1 folder(s).

Step 2: Classifying files...

Files classified: 8 total
  build: 1
  config: 1
  source: 3
  unknown: 3

Languages detected:
  python: 3 files

Step 3: Analyzing dependencies...

Dependency files found: requirements.txt
Dependencies: 5 packages

Infrastructure detected:
  - Redis (cache/store)
  - Celery (task queue)
  - SQL Database (via SQLAlchemy)
  - PostgreSQL
  - Flask (HTTP framework)

Scan complete! Run teach analyze {path} next.
```

```bash
$ teach analyze tests/fixtures/sample_project

Analyzing codebase: tests/fixtures/sample_project
Provider: claude-code
Source files to analyze: 3
  Found 5 functions, 1 classes, 5 imports
  AST parsing complete
  AST API detection complete
  File summaries complete
  Module summaries complete
  Project summary complete
  API detection complete
  Infrastructure detection complete
  Data flow tracing complete

Analysis complete!
  APIs: 5
  Infrastructure: 0
  Data flows: 5

Run teach generate tests/fixtures/sample_project to produce documentation.
```

```bash
$ teach generate tests/fixtures/sample_project

Generating content for: tests/fixtures/sample_project
Provider: claude-code
Output: tests/fixtures/sample_project/.teacher-output

Generating documentation...
  Created: .teacher-output/docs/overview.md
  Created: .teacher-output/docs/architecture.md
  Created: .teacher-output/docs/api-reference.md
  Created: .teacher-output/docs/infrastructure.md

Generating diagrams...
  Created: .teacher-output/diagrams/architecture.md
  Created: .teacher-output/diagrams/data-flow.md

Generated 6 files!
```

## Hosted HTML reports

This repo hosts the most recent HTML report on the `html-test-host`
branch via GitHub Pages.

- Running `/teach-evaluate-push {path} html` generates
  `{path}/.teacher-output/index.html` and publishes it to
  `html-test-host/index.html`, overwriting the previous run.
- Only the tip of `html-test-host` is served; there is no per-run or
  per-target history. The `markdown` format writes results to
  `{path}/.teacher-output/` locally and does not push anywhere.
- `html-test-host` also contains a `.nojekyll` marker so Pages serves
  files literally (no Jekyll processing).

## Development

```bash
pip install -e ".[dev]"
pytest
```
