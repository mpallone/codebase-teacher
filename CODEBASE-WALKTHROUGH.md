# Codebase Teacher — Complete Mechanical Walkthrough

This document explains every module in the `codebase-teacher` repository. It is intended for someone who wants to understand precisely how each piece works, how it connects to every other piece, and why the design decisions were made.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Repository Layout](#2-repository-layout)
3. [Configuration — `pyproject.toml` and `.env.example`](#3-configuration--pyprojecttoml-and-envexample)
4. [Entry Points — `__init__.py` and `__main__.py`](#4-entry-points----initpy-and-mainpy)
5. [CLI Layer](#5-cli-layer)
   - [cli/app.py](#clipy--the-root-click-group)
   - [cli/scan.py](#cliscanpy--teach-scan)
   - [cli/analyze.py](#clianalyzepy--teach-analyze)
   - [cli/generate.py](#cligeneratepy--teach-generate)
6. [Core Utilities](#6-core-utilities)
   - [core/config.py](#coreconfigpy)
   - [core/exceptions.py](#coreexceptionspy)
7. [Scanner](#7-scanner)
   - [scanner/discovery.py](#scannerdiscoverypy)
   - [scanner/file_classifier.py](#scannerfile_classifierpy)
   - [scanner/dependency.py](#scannerdependencypy)
8. [Analyzer](#8-analyzer)
   - [analyzer/code_parser.py](#analyzercode_parserpy--python-ast)
   - [analyzer/java_parser.py](#analyzerjava_parserpy--java-tree-sitter)
   - [analyzer/terraform_parser.py](#analyzerterraform_parserpy--hcl-tree-sitter)
   - [analyzer/api_detector.py](#analyzerapi_detectorpy)
   - [analyzer/infra_detector.py](#analyzerinfra_detectorpy)
   - [analyzer/flow_tracer.py](#analyzerflow_tracerpy)
9. [LLM Layer](#9-llm-layer)
   - [llm/provider.py](#llmproviderpy--protocol)
   - [llm/litellm_adapter.py](#llmlitellm_adapterpy--concrete-adapter)
   - [llm/prompt_registry.py](#llmprompt_registrypy)
   - [llm/context_manager.py](#llmcontext_managerpy)
   - [llm/structured.py](#llmstructuredpy)
10. [Storage](#10-storage)
    - [storage/models.py](#storagemodels py--pydantic-models)
    - [storage/database.py](#storagedatabasepy--sqlite)
    - [storage/artifact_store.py](#storageartifact_storepy)
11. [Generator](#11-generator)
    - [generator/docs.py](#generatordocspy)
    - [generator/diagrams.py](#generatordiagramspy)
    - [generator/templates/doc_page.md.j2](#generatortemplates)
12. [Tests](#12-tests)
    - [conftest.py](#conftestpy)
    - [Fixtures: sample\_project](#fixtures-sample_project)
    - [test_scanner/](#test_scanner)
    - [test_analyzer/](#test_analyzer)
    - [test_llm/](#test_llm)
    - [test_storage/](#test_storage)
13. [End-to-End Pipeline Trace](#13-end-to-end-pipeline-trace)

---

## 1. Project Overview

`codebase-teacher` is a CLI tool that takes a directory of source code and produces human-readable documentation — architecture overviews, API references, infrastructure maps, and Mermaid diagrams — by combining two complementary techniques:

- **Deterministic AST parsing** (Python's `ast` module, tree-sitter for Java and Terraform/HCL) to extract structural facts: functions, classes, imports, decorators, Terraform resources.
- **LLM-powered summarization and analysis** (via litellm, which abstracts Anthropic, OpenAI, Gemini, etc.) to produce natural-language summaries, detect infrastructure patterns, trace data flows, and write documentation prose.

The three-command pipeline is: `teach scan` → `teach analyze` → `teach generate`. Each command reads from and writes to a per-project SQLite database stored inside the target project directory under `.teacher/teacher.db`.

---

## 2. Repository Layout

```
.
├── pyproject.toml                    # build config, dependencies, entry point
├── .env.example                      # shows env vars users must set
├── README.md
├── src/
│   └── codebase_teacher/
│       ├── __init__.py               # package version
│       ├── __main__.py               # python -m support
│       ├── cli/                      # Click commands (scan, analyze, generate)
│       ├── core/                     # config, context object, exceptions
│       ├── scanner/                  # filesystem walk, classification, dep detection
│       ├── analyzer/                 # AST parsers + LLM-based analyzers
│       ├── llm/                      # provider protocol, litellm adapter, prompts, parsing
│       ├── storage/                  # pydantic models, SQLite DB, artifact store
│       └── generator/                # markdown docs + Mermaid diagrams
└── tests/
    ├── conftest.py                   # shared fixtures (MockLLMProvider, tmp_db, etc.)
    ├── fixtures/sample_project/      # minimal Flask+Celery app used by many tests
    ├── test_analyzer/
    ├── test_llm/
    ├── test_scanner/
    └── test_storage/
```

---

## 3. Configuration — `pyproject.toml` and `.env.example`

### [`pyproject.toml`](https://github.com/mpallone/codebase-teacher/blob/main/pyproject.toml)

**What it does:** Defines the package, its dependencies, the entry-point script, and pytest configuration.

**Key entries:**

| Entry | Detail |
|---|---|
| `build-backend = "hatchling.build"` | Uses Hatchling to build. No `setup.py` needed. |
| `requires-python = ">=3.11"` | The code uses `ast.unparse` (3.9+) and `X \| Y` union syntax (3.10+). 3.11 is chosen as a safe minimum. |
| `dependencies` | Runtime deps. `click` + `rich` for CLI. `litellm` for multi-provider LLM calls. `pydantic` + `pydantic-settings` for typed models and env-var config. `jinja2` for doc templates. `tree-sitter>=0.22,<0.24` plus `tree-sitter-java` and `tree-sitter-hcl` for language-specific parsers. |
| `[project.scripts] teach = "codebase_teacher.cli.app:cli"` | The installed entry point. Running `teach` invokes `cli()` in `cli/app.py`. |
| `[project.optional-dependencies] dev` | `pytest`, `pytest-asyncio`, `pytest-cov`. Not installed in production. |
| `[tool.pytest.ini_options]` | `asyncio_mode = "auto"` means every `async def test_*` is run automatically without `@pytest.mark.asyncio`. Tests live in `tests/`. The `llm` marker tags tests that hit a real API key. |

**Design note:** tree-sitter is pinned to `<0.24` because the API changed at 0.24 (the `Language` constructor signature changed). The Java and HCL language packages expose a `language()` function that returns a language pointer consumed by `Language(...)`.

### [`.env.example`](https://github.com/mpallone/codebase-teacher/blob/main/.env.example)

Shows the three env vars a user may need:
- `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` — passed through to litellm automatically by convention.
- `CODEBASE_TEACHER_MODEL` — litellm model string, e.g. `anthropic/claude-sonnet-4-20250514`.

The `CODEBASE_TEACHER_` prefix is set in `Settings.model_config` and applied by pydantic-settings to all `Settings` fields.

---

## 4. Entry Points — `__init__.py` and `__main__.py`

### [`src/codebase_teacher/__init__.py`](https://github.com/mpallone/codebase-teacher/blob/main/src/codebase_teacher/__init__.py)

Single line: `__version__ = "0.1.0"`. Imported by `cli/app.py` to supply `--version`.

### [`src/codebase_teacher/__main__.py`](https://github.com/mpallone/codebase-teacher/blob/main/__main__.py)

Enables `python -m codebase_teacher`. Imports and calls `cli()` from `cli/app.py`. Identical behavior to the `teach` entry point.

---

## 5. CLI Layer

The CLI uses [Click](https://click.palletsprojects.com/). The root group is defined in `app.py`; each subcommand lives in its own file and is registered with `cli.add_command(...)`.

### [`src/codebase_teacher/cli/app.py`](https://github.com/mpallone/codebase-teacher/blob/main/src/codebase_teacher/cli/app.py) — the root Click group

**What it does:** Defines the `cli` Click group, which acts as the top-level dispatcher. Attaches three options that apply to all subcommands:

- `--version` — prints `__version__` and exits.
- `--model` — LLM model string in litellm format (e.g. `anthropic/claude-sonnet-4-20250514`). Also readable from `CODEBASE_TEACHER_MODEL` env var via `envvar=`.
- `--verbose` / `-v` — verbose flag (stored in context but not yet wired deeply into logging).

Both `model` and `verbose` are stored in `ctx.obj` (a plain dict), and subcommands retrieve them with `ctx.obj.get("model")`.

**Subcommand registration:** After defining `cli`, the file imports `scan`, `analyze`, and `generate` from their respective modules and calls `cli.add_command(...)`. The imports are deferred (below the `@click.group()` definition) to avoid circular imports; `# noqa: E402` silences the linter complaint.

### [`src/codebase_teacher/cli/scan.py`](https://github.com/mpallone/codebase-teacher/blob/main/src/codebase_teacher/cli/scan.py) — `teach scan`

**What it does:** Runs the scan pipeline: interactive folder selection, file classification, dependency analysis.

**Mechanics:**

1. Takes a `PATH` argument (a real directory, resolved to absolute path by Click).
2. Instantiates `Settings()` (reads env vars). If `--model` was passed at the group level, it overrides `settings.model`.
3. Opens (or creates) the SQLite database at `<project_root>/.teacher/teacher.db` via `Database(settings.db_path(root))`.
4. Calls `db.get_or_create_project(str(root), root.name)` — returns an integer project ID. This ID is the foreign key for all subsequent DB operations for this project.
5. **Step 1 — Folder Discovery:** Calls `interactive_folder_selection(root, db, project_id, console)`. This walks the top-level directories, shows a Rich tree, and asks the user "is this folder relevant?" for each one. Answers are persisted to `scan_state`. On a second run, existing answers are shown without re-prompting.
6. **Step 2 — File Classification:** Calls `classify_directory(root, relevant_folders)` which walks every file in the relevant folders and assigns each a category (source, test, config, infra, build, docs, data, unknown) and language. Results are stored in `file_classifications` via `db.set_file_classification(...)`.
7. Prints a summary table of category counts and language counts.
8. **Step 3 — Dependency Analysis:** Calls `detect_dependencies(root)` which looks for `requirements.txt`, `pyproject.toml`, `package.json`, `go.mod`, and extracts package names. Also heuristically detects infra (Redis, Kafka, etc.) from dependency names and the presence of `Dockerfile` or `.tf` files.

**Why it's separate from `analyze`:** Scanning is interactive (requires stdin) and cheap (no LLM calls). Analysis is expensive (many LLM calls). Separating them lets the user verify the scan results first.

### [`src/codebase_teacher/cli/analyze.py`](https://github.com/mpallone/codebase-teacher/blob/main/src/codebase_teacher/cli/analyze.py) — `teach analyze`

**What it does:** Runs the full LLM-assisted analysis pipeline and caches the result to SQLite.

**Sync wrapper / async core:** The `analyze` Click command is synchronous (Click doesn't support `async def`). It immediately calls `asyncio.run(_analyze_async(root, settings))`. All the real work is in `_analyze_async`.

**The 8-step pipeline inside `_analyze_async`:**

1. **Database and project setup.** Same pattern as `scan`: open DB, get project ID, load relevant folders. If no folders were scanned, falls back to `"."`.
2. **Load source files.** Reads from `file_classifications` table, category `"source"`. If nothing was classified, falls back to walking `*.py` files.
3. **Initialize LLM.** Creates `LiteLLMProvider(model=..., max_tokens=...)` and wraps it in `ContextManager(provider, max_concurrent=...)`.
4. **Step 1 — AST parsing (no LLM).** Calls `parse_codebase(root, source_files)`. Returns a `CodebaseGraph` with all extracted functions, classes, imports, and Terraform resources. No LLM involved; this is deterministic.
5. **Step 2 — AST-based API detection (no LLM).** Calls `detect_apis_from_ast(functions, classes)`. Inspects decorator strings for HTTP-routing patterns.
6. **Step 3 — File summarization (LLM).** Reads all source files into a `dict[str, str]`. Calls `ctx_manager.summarize_files(file_contents)`, which fires up to `max_concurrent` parallel LLM calls to summarize each file. Returns `list[FileSummary]`.
7. **Step 4 — Module summarization (LLM).** Groups file summaries by top-level directory (`_group_by_module`). For each module, calls `ctx_manager.summarize_module(...)`, which concatenates the file summaries and asks the LLM for a module-level overview.
8. **Step 5 — Project summary (LLM).** Calls `ctx_manager.summarize_project(module_summaries)`, which concatenates module summaries and asks for a project-level overview. One LLM call.
9. **Step 6 — LLM-based API detection.** Calls `detect_apis(provider, file_contents)`, which sends all source code to the LLM and asks for all API endpoints. Merges results with AST-detected endpoints, deduplicating by handler name.
10. **Step 7 — Infrastructure detection (LLM).** Reads config and infra files from the DB, adds the first 20 source files, adds `dep_report.infra_hints` as extra context, and calls `detect_infrastructure(provider, infra_files, hints)`.
11. **Step 8 — Data flow tracing (LLM).** Calls `trace_data_flows(provider, project_summary, module_summaries, api_endpoints, infrastructure)`. This is the most expensive call. It inherits the provider's configured `max_tokens` (Settings-driven) — no hardcoded override.

**Caching:** After all steps, assembles an `AnalysisResult` pydantic model and calls `db.cache_analysis(project_id, "full_analysis", content_hash, result.model_dump())`. The content hash is SHA-256 of all source file bytes (truncated to 16 hex chars). The `generate` command reads this cache.

**`_compute_hash`:** Sorts source file paths (for determinism), reads each file's bytes, and updates a SHA-256 digest. Only the first 16 hex characters are used as the key — a convenience truncation sufficient for cache invalidation in practice.

**`_group_by_module`:** Splits `file_path` on `"/"` and uses `parts[0]` as the module name. Files at the root level (no directory component) are grouped under `"."`. This means a project like `src/foo/bar.py` would group under `src`, while `main.py` would group under `"."`.

### [`src/codebase_teacher/cli/generate.py`](https://github.com/mpallone/codebase-teacher/blob/main/src/codebase_teacher/cli/generate.py) — `teach generate`

**What it does:** Reads the cached `AnalysisResult` from SQLite and generates documentation and diagrams.

**Options:** `--type [all|docs|diagrams]` (default `all`). Allows regenerating only docs or only diagrams.

**`_load_analysis`:** Queries the `analysis_cache` table for the most recent row where `analyzer_name = 'full_analysis'` for this project. Deserializes `result_json` via `AnalysisResult.model_validate(data)`. Returns `None` if not found.

**Generation flow:**
- If `gen_type in ("all", "docs")`: calls `generate_all_docs(provider, analysis, store)` → returns paths to `architecture.md`, `api-reference.md`, `infrastructure.md` written under `<project>/.teacher-output/docs/`.
- If `gen_type in ("all", "diagrams")`: calls `generate_all_diagrams(provider, analysis, store)` → returns paths to `architecture.md` and `data-flow.md` under `<project>/.teacher-output/diagrams/`.

**`ArtifactStore`:** Created with `output_dir = settings.output_path(root)` (default `<project>/.teacher-output`). The store handles creating subdirectories and recording each written file in the `artifacts` table.

---

## 6. Core Utilities

### [`src/codebase_teacher/core/config.py`](https://github.com/mpallone/codebase-teacher/blob/main/src/codebase_teacher/core/config.py)

**What it does:** Defines `Settings`, the single source of truth for all configurable values.

`Settings` extends `pydantic_settings.BaseSettings`. pydantic-settings automatically reads matching environment variables, applying the `CODEBASE_TEACHER_` prefix. Fields:

| Field | Default | Notes |
|---|---|---|
| `model` | `"anthropic/claude-sonnet-4-20250514"` | litellm model string |
| `temperature` | `0.3` | LLM temperature for most calls |
| `max_tokens` | `16384` | Max output tokens per LLM call. Single source of truth — all call sites inherit this via `LiteLLMProvider`. |
| `output_dir` | `".teacher-output"` | Relative to target project root |
| `db_dir` | `".teacher"` | Relative to target project root |
| `verbose` | `False` | Not yet wired to logging |
| `max_concurrent_llm_calls` | `5` | Semaphore limit in `ContextManager.summarize_files` |

`output_path(project_root)` and `db_path(project_root)` are helper methods that resolve the relative dirs against the project root and create the db directory if absent.

**Design note:** Using pydantic-settings means settings can be overridden per-call with environment variables without any explicit `.env` file reading. The `--model` CLI flag flows into `settings.model` via `ctx.obj["model"]` at the CLI layer, not through pydantic.

### [`src/codebase_teacher/core/exceptions.py`](https://github.com/mpallone/codebase-teacher/blob/main/src/codebase_teacher/core/exceptions.py)

**What it does:** Defines the exception hierarchy. All exceptions inherit from `CodebaseTeacherError(Exception)`.

| Exception | When it's raised |
|---|---|
| `ScanError` | Scanning failures |
| `AnalysisError` | Analysis failures |
| `GenerationError` | Generation failures |
| `LLMError` | `LiteLLMProvider.complete` or `.stream` fails |
| `LLMResponseError` | LLM returns unparseable or schema-invalid JSON |
| `ContextBudgetExceeded` | `ContextManager.build_context` exceeds token budget |
| `StorageError` | DB or file I/O failures |

`LLMError` and `LLMResponseError` both subclass `LLMError`. `ContextBudgetExceeded` also subclasses `LLMError` because it's triggered by context window constraints.

---

## 7. Scanner

### [`src/codebase_teacher/scanner/discovery.py`](https://github.com/mpallone/codebase-teacher/blob/main/src/codebase_teacher/scanner/discovery.py)

**What it does:** Walks the top level of the target project directory, presents a Rich tree view, and asks the user which folders are relevant.

**`ALWAYS_SKIP`:** A hardcoded set of directory names that are never shown to the user: `.git`, `__pycache__`, `node_modules`, `.venv`, `venv`, `dist`, `build`, `.teacher`, `.teacher-output`, IDE dirs, etc.

**`_should_skip(name)`:** Returns `True` if `name` is in `ALWAYS_SKIP` or starts with `"."`. The dot prefix rule catches all hidden directories, including `.github`, `.circleci`, etc.

**`_load_gitignore_patterns(root)`:** Reads `.gitignore` line by line, strips blank lines and comment lines. Returns the raw pattern strings. Notably, this is not a full gitignore spec implementation.

**`_is_gitignored(path, root, patterns)`:** For each pattern, checks if the cleaned pattern (trailing `/` stripped) appears as a substring of the relative path or if the relative path ends with it. This is a heuristic — it handles the most common cases (`vendor/`, `__pycache__`, etc.) but does not handle negation patterns (`!foo`), character classes, or anchored patterns.

**`discover_folders(root)`:** Iterates `sorted(root.iterdir())` (sorted for deterministic ordering). Skips non-directories, directories that fail `_should_skip`, and gitignored entries. Returns a flat list of `Path` objects — only the immediate children of root.

**`build_folder_tree(root, max_depth=3)`:** Builds a Rich `Tree` object showing the directory structure to 3 levels deep. At depth `< max_depth - 1`, shows up to 10 files with a "and N more" truncation. At the deepest level, shows only the file count.

**`interactive_folder_selection(root, db, project_id, console)`:**
1. Calls `discover_folders` to get candidate folders.
2. Calls `build_folder_tree` and prints it.
3. Loads existing decisions from `db.get_folder_statuses(project_id)` — a dict of `{rel_path: status}`.
4. For each folder: if it has a prior decision, shows it without prompting. Otherwise, shows the folder name, counts files with `folder.rglob("*")`, and asks `y/n/s` via `rich.prompt.Prompt.ask`.
5. Persists each decision to `scan_state` via `db.set_folder_status(...)`.
6. Returns the list of `rel_path` strings that got `"relevant"` status.

**Design note:** Only immediate top-level subdirectories are presented. This is intentional: for large repos, showing every nested directory would be overwhelming. The user filters at the top level (e.g. "yes to `src/`, no to `vendor/`"), and subsequent steps recursively process the selected folders.

### [`src/codebase_teacher/scanner/file_classifier.py`](https://github.com/mpallone/codebase-teacher/blob/main/src/codebase_teacher/scanner/file_classifier.py)

**What it does:** Assigns each file a category (`source`, `test`, `config`, `infra`, `build`, `docs`, `data`, `unknown`) and a language name.

**`LANGUAGE_MAP`:** Dict mapping extension (e.g. `".py"`) to language name (e.g. `"python"`). Covers 25+ languages. The language name is stored as-is in the DB.

**`_determine_category(path, rel_path, name, ext)`:** Priority order:
1. Test — checks `rel_lower` for any of `{"test_", "_test.", ".test.", ".spec.", "tests/", "test/", "__tests__/"}`. Note that this matches path components anywhere in the relative path. So `src/tests/utils.py` would be classified as `test`.
2. Infra — checks `name in INFRA_PATTERNS` (exact filename match: `Dockerfile`, `Makefile`, etc.) or `ext in INFRA_EXTENSIONS` (`".tfvars"`), or any `part in INFRA_PATTERNS` along `path.parts`. The third check catches files inside e.g. a `.github/` directory.
3. Build — checks `name in BUILD_PATTERNS` (exact: `pyproject.toml`, `package.json`, etc.).
4. Config — checks `name in CONFIG_PATTERNS` or `ext in CONFIG_EXTENSIONS` (`.yaml`, `.toml`, `.ini`, etc.).
5. Docs — checks `ext in DOC_EXTENSIONS` (`.md`, `.rst`, `.txt`, `.adoc`).
6. Data — checks for `.csv`, `.json`, `.xml`, `.parquet`, `.avro`.
7. Source — if `ext in LANGUAGE_MAP`.
8. Unknown — fallback.

**`classify_file(path, root)`:**
- Computes relative path from root.
- Calls `_determine_category`.
- Reads the file text to call `estimate_tokens(content)` (from `llm/context_manager.py`). Uses `len(text) // 4`.
- Returns a `FileInfo` pydantic model.

**`classify_directory(root, relevant_folders)`:**
- For each relevant folder, calls `folder.rglob("*")` to get all files recursively.
- Skips compiled/binary extensions: `.pyc`, `.pyo`, `.so`, `.dll`, `.exe`, `.bin`, `.jar`, `.class`.
- Skips files larger than 1 MB.
- Calls `classify_file` on each remaining file.
- Returns all `FileInfo` instances as a flat list.

### [`src/codebase_teacher/scanner/dependency.py`](https://github.com/mpallone/codebase-teacher/blob/main/src/codebase_teacher/scanner/dependency.py)

**What it does:** Reads known dependency manifest files and extracts package names. Also produces `infra_hints` — strings describing detected infrastructure.

**`_PARSERS` dict:** Maps filename to parser function. Current parsers:

| File | Parser | Technique |
|---|---|---|
| `requirements.txt` | `_parse_requirements_txt` | Line-by-line regex `([a-zA-Z0-9_-]+)` to extract package name before version specifiers |
| `pyproject.toml` | `_parse_pyproject_toml` | Regex-based: finds the `dependencies = [` line, then extracts `"package-name` patterns from subsequent lines until `]` |
| `package.json` | `_parse_package_json` | `json.loads`, iterates `dependencies` and `devDependencies` keys |
| `go.mod` | `_parse_go_mod` | Finds `require (` block, splits on whitespace to extract module paths |

**`_detect_infra_hints(root)`:**
- For each parser file (if it exists), reads the full text lowercased and checks for each key in `_INFRA_KEYWORDS`. `_INFRA_KEYWORDS` maps substring (e.g. `"kafka"`) to a description string (e.g. `"Kafka (message queue)"`).
- Checks for `Dockerfile` or `docker-compose.yml` → Docker hint.
- Checks for any `*.tf` file → Terraform hint.
- Checks for `**/k8s/**` or `**/*.k8s.yaml` → Kubernetes hint.

**`print_dependency_report`:** Formats the report using Rich, showing dependency file names, total package count, and infra hints.

---

## 8. Analyzer

### [`src/codebase_teacher/analyzer/code_parser.py`](https://github.com/mpallone/codebase-teacher/blob/main/src/codebase_teacher/analyzer/code_parser.py) — Python AST

**What it does:** Parses Python, Java, and Terraform/HCL files and merges results into a single `CodebaseGraph`. The Python parsing uses the standard library `ast` module; Java and Terraform delegate to their respective parsers.

**`parse_python_file(file_path, root)`:**
1. Reads file as UTF-8 text (errors ignored).
2. Calls `ast.parse(source, filename=...)` — raises `SyntaxError` on invalid Python, caught and returned as empty graph.
3. Walks the entire AST with `ast.walk(tree)`.
4. For `ast.FunctionDef` / `ast.AsyncFunctionDef`: only processes if `_is_top_level_or_module_level` (checks if the node is a direct child of `tree.body`). This filters out methods — they are captured separately when processing `ClassDef`.
5. For `ast.ClassDef`: calls `_extract_class`.
6. For `ast.Import`: each `alias` in `node.names` becomes an `ImportInfo(module=alias.name, names=[alias.asname or alias.name])`.
7. For `ast.ImportFrom`: creates one `ImportInfo(module=node.module, names=[...], is_relative=node.level > 0)`. `node.level > 0` indicates a relative import (`from .models import User`).

**`_extract_function(node, file_path)`:**
- Iterates `node.args.args` to build argument strings. If an argument has an annotation, calls `ast.unparse(arg.annotation)` to reconstruct it as a string (e.g. `"str"`, `"list[int]"`).
- Builds return type string from `node.returns` via `ast.unparse`.
- Assembles `signature` like `"def foo(x: int, y: str) -> bool"`.
- Extracts decorators via `[ast.unparse(d) for d in node.decorator_list]` — `ast.unparse` reconstructs the full decorator expression as a string, e.g. `"@app.route('/api/users', methods=['GET'])"`.
- Extracts docstring via `ast.get_docstring(node)`.
- Sets `is_async=True` for `ast.AsyncFunctionDef`.

**`_extract_class(node, file_path)`:**
- Calls `ast.unparse` on each `node.bases` entry.
- Iterates `node.body` for `FunctionDef` / `AsyncFunctionDef` children (methods). Calls `_extract_function` on each.
- Does not handle nested classes.

**`parse_codebase(root, source_files)`:**
- Iterates `source_files` (relative path strings).
- Dispatches by extension: `.py` → `parse_python_file`, `.java` → `parse_java_file`, `.tf`/`.hcl` → `parse_terraform_file`.
- Skips all other extensions silently.
- Accumulates all results into a single `CodebaseGraph`.

### [`src/codebase_teacher/analyzer/java_parser.py`](https://github.com/mpallone/codebase-teacher/blob/main/src/codebase_teacher/analyzer/java_parser.py) — Java tree-sitter

**What it does:** Parses Java files using `tree-sitter-java`. Extracts classes, interfaces, enums, records, annotation types, their methods, their imports, and the package declaration.

**Initialization (module-level):**
```python
import tree_sitter_java as _tsjava
from tree_sitter import Language, Parser as _TSParser
_JAVA_LANGUAGE = Language(_tsjava.language())
_JAVA_AVAILABLE = True
```
This runs once at import time. If `tree-sitter-java` is not installed, `_JAVA_AVAILABLE = False` and all parse calls return empty graphs. The broad `except Exception` handles `ImportError`, `OSError`, and potential ABI errors.

**`parse_java_file(file_path, root)`:**
1. Reads file as bytes (tree-sitter works on bytes, not strings).
2. Creates `_TSParser(_JAVA_LANGUAGE)` (a new parser per call — stateless).
3. Calls `parser.parse(source)` — returns a `tree_sitter.Tree` with `root_node`.
4. Iterates `root_node.named_children` (top-level AST nodes).
5. Dispatches by `child.type`:
   - `"import_declaration"` → `_extract_import`
   - `"package_declaration"` → `_extract_package` (stored as `ImportInfo` with `names=["<package>"]` to distinguish it)
   - `"class_declaration"`, `"interface_declaration"`, `"enum_declaration"`, `"annotation_type_declaration"`, `"record_declaration"` → `_extract_class`
6. Returns `CodebaseGraph(classes=classes, imports=imports)`. No top-level functions (Java has none).

**`_extract_import(node, source)`:**
- Extracts the node text with `_node_text(node, source)` (slices `source[start_byte:end_byte]`, decodes UTF-8).
- Strips `"import"`, `"static"`, and `";"` prefixes/suffixes.
- If the remaining text ends with `".*"`: `module = text[:-2]`, `names = ["*"]`.
- Otherwise: splits on last `"."` to get `(module, name)`.

**`_extract_class(node, file_path, source, node_type)`:**
- Finds the name: `node.child_by_field_name("name")` — a named field in the Java grammar. Falls back to `_first_child_of_type(node, "identifier")`.
- Sets sentinel `bases` entries: `"<interface>"` for interfaces, `"<enum>"` for enums, `"<annotation>"` for annotation types, `"<record>"` for records.
- Superclass: `node.child_by_field_name("superclass")` returns a node like `extends Foo`; iterates its `named_children` to get type identifier names.
- Implemented interfaces: `node.child_by_field_name("interfaces")` returns a `super_interfaces` node; `_collect_type_list` digs into its `type_list` child for individual `type_identifier` nodes.
- Extended interfaces (for interfaces): searches for a child of type `"extends_interfaces"` (this is a node type, not a field name in the tree-sitter-java grammar).
- Body: `node.child_by_field_name("body")` → iterates `named_children`, filters for `"method_declaration"` and `"constructor_declaration"`.

**`_extract_method(node, file_path, source)`:**
- Name: `child_by_field_name("name")`.
- Return type: `child_by_field_name("type")` — absent for constructors.
- Parameters: `child_by_field_name("parameters")` — the full text including parentheses.
- Modifiers: `_first_child_of_type(node, "modifiers")` — its children are either modifier keywords (`public`, `static`, etc.) or annotations (`"annotation"` / `"marker_annotation"` node types). Annotations go into `decorators`; keywords go into `modifiers_parts`.
- Signature assembled as e.g. `"public static String findAll()"`.
- Always sets `is_async=False` — Java has no async keyword.

**`_collect_type_list(node, source, out)`:** Finds a `"type_list"` child and iterates its `named_children` to collect type names. Fallback: collects any child that isn't `"implements"` or `"extends"`.

**`_node_text(node, source)`:** `source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")`.

### [`src/codebase_teacher/analyzer/terraform_parser.py`](https://github.com/mpallone/codebase-teacher/blob/main/src/codebase_teacher/analyzer/terraform_parser.py) — HCL tree-sitter

**What it does:** Parses Terraform (`.tf`) and HCL (`.hcl`) files using `tree-sitter-hcl`. Extracts block-level constructs as `TerraformResource` instances.

**Initialization (module-level):** Same pattern as Java: `Language(_tshcl.language())` in a try/except, sets `_HCL_AVAILABLE`.

**`_TERRAFORM_BLOCK_TYPES`:** A `frozenset` of HCL block type keywords: `resource`, `data`, `module`, `variable`, `output`, `provider`, `terraform`, `locals`. Only blocks whose first token matches one of these are captured.

**`parse_terraform_file(file_path, root)`:**
1. Reads as bytes, parses, gets `tree.root_node`.
2. Calls `_collect_blocks(root_node, source, rel_path, resources)`.
3. Returns `CodebaseGraph(terraform_resources=resources)`.

**`_collect_blocks(node, source, file_path, resources)`:** Walks all children. If a child's `type == "block"`, calls `_parse_block`. Otherwise, recurses. This handles the fact that HCL grammars may wrap blocks in intermediate container nodes.

**`_parse_block(node, source, file_path)`:**
1. Calls `_block_type_and_labels(node, source)` to get `(block_type, [label1, label2, ...])`.
2. If `block_type not in _TERRAFORM_BLOCK_TYPES`, returns `None`.
3. Maps to `TerraformResource`:
   - `resource "aws_s3_bucket" "my_bucket" {}` → `kind="resource"`, `type="aws_s3_bucket"`, `name="my_bucket"`.
   - `data "aws_ami" "ubuntu" {}` → `kind="data"`, `type="aws_ami"`, `name="ubuntu"`.
   - `module "vpc" {}` → `kind="module"`, `type=""`, `name="vpc"`.
   - `variable "region" {}` → `kind="variable"`, `type=""`, `name="region"`.
   - `terraform {}` / `locals {}` → `kind="terraform"`/`"locals"`, `type=""`, `name=""`.

**`_block_type_and_labels(node, source)`:** The most complex function in this file. It needs to handle two grammar layouts because different versions of tree-sitter-hcl use different AST structures:

- **Layout A (field-based):** The block node has a `"type"` field pointing to an identifier node. Then iterates `named_children` to collect labels after the type node. Labels are string literals (quoted template) or bare identifiers.
- **Layout B (positional fallback):** Takes the first named child as the block type identifier, then collects subsequent string children as labels until a non-string child is encountered.

**`_extract_label_text(node, source)`:** Handles the three string node types used in HCL grammars:
- `"quoted_template"`: iterates children looking for `"template_literal"` nodes (the content between the quotes).
- `"string_lit"`: strips leading/trailing `"` or `'` from the raw text.
- `"template_literal"`: returns the text directly.
- Returns `None` for anything else (so the caller knows to stop collecting labels).

**Design note:** The dual-layout handling exists because `tree-sitter-hcl` has changed its grammar structure across versions. The field-based approach (Layout A) is tried first; if the `"type"` field isn't present, the positional fallback (Layout B) handles older grammar versions. This makes the parser robust to library version changes.

### [`src/codebase_teacher/analyzer/api_detector.py`](https://github.com/mpallone/codebase-teacher/blob/main/src/codebase_teacher/analyzer/api_detector.py)

**What it does:** Detects API endpoints two ways: (1) from AST data without LLM, (2) from source code via LLM.

**`detect_apis_from_ast(functions, classes)`:**
- Iterates all functions. For each decorator string, lowercases it and checks if any of `{"route", "get", "post", "put", "delete", "patch", "api_view", "action"}` appears as a substring.
- If matched: extracts path via `_extract_path_from_decorator` (regex `["'](/[^"']*)["\']` to find a slash-leading string argument) and method via `_extract_method_from_decorator` (checks for HTTP method names as substrings, defaults to `"GET"`).
- Creates `APIEndpoint(method=..., path=..., handler=func.name, file=func.file_path, description=func.docstring or "")`.
- Also iterates all class methods and generates `handler = f"{cls.name}.{method_info.name}"`.

**`detect_apis(provider, file_contents)`:**
- Formats all file contents as code fences: `"### File: {path}\n```\n{content}\n```"`.
- Uses the `"detect_apis"` prompt from `PROMPTS`.
- Sends to LLM, which returns a JSON array.
- Calls `parse_model_list(response.content, APIEndpoint)` to parse.
- On any exception during parsing, returns `[]` (silent failure — the merge step in `analyze.py` handles the case of zero LLM endpoints).

**Integration with `analyze.py`:** Both detection methods run, then are merged: AST endpoints first, then LLM endpoints are appended only if their `handler` name doesn't already appear in the AST results. This means AST takes precedence for endpoints it finds (more reliable source locations), and LLM fills in endpoints the AST missed (e.g. FastAPI dependencies, gRPC services, CLI commands).

### [`src/codebase_teacher/analyzer/infra_detector.py`](https://github.com/mpallone/codebase-teacher/blob/main/src/codebase_teacher/analyzer/infra_detector.py)

**What it does:** Sends source and config file contents to the LLM, asking it to identify infrastructure components (databases, queues, storage, compute platforms).

**`detect_infrastructure(provider, file_contents, infra_hints)`:**
- Builds a prompt body with `_build_code_chunks`, prepending any `infra_hints` as bullet points before the code fences.
- Uses the `"detect_infrastructure"` prompt.
- Parses the response as `list[InfraComponent]` via `parse_model_list`.

**`_build_code_chunks`:** Prepends the hints section if hints exist, then appends each file as a labeled code fence.

**Why pass `infra_hints` explicitly?** The hints come from the deterministic dependency scanner (`_INFRA_KEYWORDS`), which is faster and cheaper than the LLM. By including them in the LLM prompt, the LLM can focus on details (configuration, usage patterns) rather than re-detecting what the scanner already found.

### [`src/codebase_teacher/analyzer/flow_tracer.py`](https://github.com/mpallone/codebase-teacher/blob/main/src/codebase_teacher/analyzer/flow_tracer.py)

**What it does:** The most LLM-intensive analysis step. Takes the project summary, module summaries, API endpoints, and infrastructure components, and asks the LLM to identify major data flows through the system.

**`trace_data_flows(provider, project_summary, module_summaries, api_endpoints, infrastructure)`:**
- Builds a context document with `_build_summaries_text`: project overview, module summaries section, API endpoints section, infrastructure section.
- Uses the `"trace_data_flow"` prompt.
- Passes no `max_tokens` override; inherits the provider's configured cap (`Settings.max_tokens`, default 16384).
- Parses as `list[DataFlow]` via `parse_model_list`.

**`DataFlow` fields:** `name` (descriptive name), `entry_points` (list of entry point strings), `steps` (ordered list of processing steps), `outputs` (list of output destinations), `mermaid_diagram` (a Mermaid sequence or flowchart diagram as a string).

**`_build_summaries_text`:** Builds four sections: project overview, module summaries (each as an H3 heading), API endpoints (each as a bullet), infrastructure (each as a bullet).

---

## 9. LLM Layer

The LLM layer has a strict separation: `provider.py` defines the protocol; only `litellm_adapter.py` imports litellm. All other modules depend only on the protocol.

### [`src/codebase_teacher/llm/provider.py`](https://github.com/mpallone/codebase-teacher/blob/main/src/codebase_teacher/llm/provider.py) — Protocol

**What it does:** Defines three Pydantic models (`Message`, `TokenUsage`, `LLMResponse`) and one Protocol class (`LLMProvider`).

**`LLMProvider` Protocol:** Uses Python's structural typing (`typing.Protocol`). Any class that implements `complete`, `stream`, `context_window`, and `model_name` — without inheriting from `LLMProvider` — satisfies the protocol. This means `MockLLMProvider` in tests satisfies it without inheritance, just by implementing the same methods.

**Methods:**
- `complete(messages, temperature, max_tokens, response_format) -> LLMResponse`: Non-streaming completion.
- `stream(messages, temperature) -> AsyncIterator[str]`: Streaming completion, yields content chunks.
- `context_window: int`: Property returning max tokens for this model.
- `model_name: str`: Property returning the model identifier.

**Why a Protocol and not an ABC?** Structural typing avoids coupling test mocks to the production class hierarchy. Any dict-like object with the right methods works.

### [`src/codebase_teacher/llm/litellm_adapter.py`](https://github.com/mpallone/codebase-teacher/blob/main/src/codebase_teacher/llm/litellm_adapter.py) — Concrete adapter

**What it does:** The only file that imports `litellm`. All actual LLM API calls go through this class.

**`LiteLLMProvider.__init__`:** Stores `_model` (litellm model string) and `_max_tokens`. Lazily initializes `_context_window` to avoid a litellm API call at construction time.

**`complete(messages, temperature, max_tokens, response_format)`:**
- Converts `list[Message]` to `list[dict]` (the format litellm expects).
- If `response_format` is provided (a Pydantic class), sets `kwargs["response_format"] = {"type": "json_object"}`. Note: this requests JSON mode from the provider, but the actual schema validation happens in `structured.py` — litellm's `response_format` here just tells the provider to return valid JSON.
- Calls `await litellm.acompletion(**kwargs)`.
- Extracts `choice.message.content` and usage fields from the litellm response object.
- On any exception, wraps in `LLMError`.

**`stream(messages, temperature)`:**
- Calls `litellm.acompletion(..., stream=True)`.
- Iterates `async for chunk in response`, extracts `chunk.choices[0].delta.content`, yields non-empty chunks.

**`context_window` property:**
- On first access, calls `litellm.get_max_tokens(self._model)`, which looks up known context windows.
- Falls back to `200_000` (and emits a warning log) if the model isn't in litellm's registry. The warning is what makes this not a silent cap — users see they're in fallback-land and should upgrade litellm if their model has a larger window.

**`max_tokens` property:** Exposes the configured output cap (`_max_tokens`) as a read-only property. `ContextManager.available_tokens` reads this to reserve response headroom dynamically.

**`litellm.suppress_debug_info = True`:** Module-level line that disables litellm's verbose startup logging, which would otherwise clutter the CLI output.

**Design note:** litellm's value is that it normalizes the API across providers (Anthropic, OpenAI, Google, Azure, etc.). The model string format `provider/model` (e.g. `anthropic/claude-sonnet-4-20250514`) tells litellm which provider to use and which credentials to read from environment variables.

### [`src/codebase_teacher/llm/prompt_registry.py`](https://github.com/mpallone/codebase-teacher/blob/main/src/codebase_teacher/llm/prompt_registry.py)

**What it does:** A single module holding all LLM prompt templates. No prompt text appears outside this file.

**`PromptTemplate`:** A frozen dataclass with `system: str`, `user: str`, `version: str`. `format_system(**kwargs)` and `format_user(**kwargs)` call Python's `str.format()` on the respective templates. The `user` templates use `{variable_name}` placeholders.

**`PROMPTS` dict:** Maps string keys to `PromptTemplate` instances. Current keys:

| Key | Purpose |
|---|---|
| `"summarize_file"` | Summarize a single source file (5 structured points) |
| `"detect_apis"` | Find all API endpoints in a set of files |
| `"detect_infrastructure"` | Identify infrastructure components |
| `"trace_data_flow"` | Trace data flows with Mermaid diagrams |
| `"generate_architecture_doc"` | Generate architecture overview doc |
| `"generate_api_doc"` | Generate API reference |
| `"generate_infra_doc"` | Generate infrastructure documentation |

**Why centralized?** All prompts in one file means they can be versioned together (`version` field), reviewed in isolation, and potentially tested for regressions without running the full pipeline. The `version` field is present but not currently used for any routing logic.

### [`src/codebase_teacher/llm/context_manager.py`](https://github.com/mpallone/codebase-teacher/blob/main/src/codebase_teacher/llm/context_manager.py)

**What it does:** Manages the three-tier summarization hierarchy (file → module → project) and provides token budget calculations.

**`estimate_tokens(text)`:** `len(text) // 4`. This is a rough approximation (English/code averages ~4 chars per token). Used for budget estimation, not billing.

**`ContextManager.__init__(provider, max_concurrent=5)`:**
- Stores `provider` and `max_concurrent`.
- Internal caches: `_file_summaries: dict[str, FileSummary]`, `_module_summaries: dict[str, ModuleSummary]`, `_project_summary: ProjectSummary | None`.

**`available_tokens`:** `provider.context_window - 4000 - provider.max_tokens`. Reserves 4000 tokens for system prompts and reserves the provider's actual configured output cap for the response. Reading `provider.max_tokens` dynamically means raising `Settings.max_tokens` automatically shrinks the input budget to match — no silent over-allocation.

**`summarize_file(file_path, code)`:**
- Checks the `_file_summaries` cache first.
- If not cached: formats the `"summarize_file"` prompt with `file_path` and `code`, calls `provider.complete`, wraps the response in `FileSummary`.
- Caches and returns the result.

**`summarize_files(files: dict[str, str])`:**
- Creates `asyncio.Semaphore(max_concurrent)` to limit parallelism.
- For each `(path, code)` pair, creates a coroutine `_summarize(path, code)` that acquires the semaphore and calls `summarize_file`.
- Gathers all coroutines with `asyncio.gather`.
- Returns a `list[FileSummary]` in the same order as the input dict iteration.

**`summarize_module(module_path, file_summaries)`:**
- Checks `_module_summaries` cache.
- Combines file summaries as `"### {path}\n{summary}"` blocks.
- Uses an inline prompt (not from `PROMPTS`): asks for "purpose, key abstractions, dependencies, and data flow role".
- One LLM call per module.

**`summarize_project(module_summaries)`:**
- Checks `_project_summary` cache.
- Combines module summaries as `"### {path}\n{summary}"` blocks.
- Uses an inline prompt: asks for "what the system does, major components, how they connect, key infrastructure dependencies".
- One LLM call total.

**`build_context(project_summary, focus_module, focus_files)`:**
- Builds a budget-aware context string.
- Always includes the project summary.
- If `focus_module` is given, finds that module summary and adds it (if it fits).
- If `focus_files` is given, adds raw file content one at a time until the budget is exhausted.
- If the budget goes negative even for the project summary alone, raises `ContextBudgetExceeded`.
- This method is defined but not called in the current CLI flow — it's infrastructure for a future "ask a question about the codebase" feature.

### [`src/codebase_teacher/llm/structured.py`](https://github.com/mpallone/codebase-teacher/blob/main/src/codebase_teacher/llm/structured.py)

**What it does:** Parses LLM responses into Pydantic models. LLMs frequently embed JSON inside prose or markdown code fences, so robust extraction is needed.

**`extract_json(text)`:**
1. First, tries to find JSON inside a ` ```json ... ``` ` or ` ``` ... ``` ` fence using regex `r"```(?:json)?\s*\n(.*?)\n```"` with `re.DOTALL`.
2. If no fence: scans for the first `[` or `{`. Tracks bracket depth character by character to find the matching `]` or `}`. Returns that substring.
3. Falls back to returning the stripped text as-is.

**`parse_json_response(text)`:** Calls `extract_json`, then `json.loads`. Raises `LLMResponseError` on `json.JSONDecodeError`.

**`parse_model(text, model_class)`:** Calls `parse_json_response`, checks the result is a `dict`, calls `model_class.model_validate(data)`. Raises `LLMResponseError` on `ValidationError`.

**`parse_model_list(text, model_class)`:** Same but checks for a `list` and validates each item.

**`complete_and_parse(provider, messages, model_class, retries=2, temperature=0.3)`:**
- Retry loop: on `LLMResponseError`, decrements temperature by `0.1 * attempt` (minimum 0.1) and tries again.
- On all retries exhausted, raises the last error.
- Note: this function is defined but the primary callers in the analyzer modules (`detect_apis`, `detect_infrastructure`, `trace_data_flows`) call `provider.complete()` directly and then call `parse_model_list()` in a `try/except Exception: return []` block. So the retry logic is available but not consistently used.

---

## 10. Storage

### [`src/codebase_teacher/storage/models.py`](https://github.com/mpallone/codebase-teacher/blob/main/src/codebase_teacher/storage/models.py) — Pydantic models

**What it does:** Defines all data models used across the pipeline. Every model uses Pydantic v2.

**Scanner models:**

| Model | Fields | Notes |
|---|---|---|
| `FolderDecision` | `path`, `status` | status ∈ {relevant, irrelevant, unknown} |
| `FileInfo` | `path`, `category`, `language?`, `token_estimate` | Returned by `classify_file` |
| `DependencyInfo` | `name`, `source` | One package |
| `DependencyReport` | `dependencies`, `config_files`, `infra_hints` | Full scan result |

**Analyzer models:**

| Model | Fields | Notes |
|---|---|---|
| `FunctionInfo` | `name`, `file_path`, `line_number`, `signature`, `decorators`, `docstring?`, `is_async` | Python function or Java method |
| `ClassInfo` | `name`, `file_path`, `line_number`, `bases`, `methods`, `docstring?` | Python class or Java class/interface/enum |
| `ImportInfo` | `module`, `names`, `is_relative` | Python or Java import. Java package declarations use `names=["<package>"]` |
| `TerraformResource` | `kind`, `type`, `name`, `file_path`, `line_number` | One HCL block |
| `CodebaseGraph` | `functions`, `classes`, `imports`, `terraform_resources` | Aggregated AST result |
| `APIEndpoint` | `method`, `path`, `handler`, `file`, `description` | One API endpoint |
| `InfraComponent` | `type`, `technology`, `explanation`, `usage`, `config` | One infra component |
| `DataFlow` | `name`, `entry_points`, `steps`, `outputs`, `mermaid_diagram` | One data flow |
| `AnalysisResult` | `codebase_graph`, `api_endpoints`, `infrastructure`, `data_flows`, `file_summaries`, `module_summaries`, `project_summary` | Everything cached to DB |

**`AnalysisResult`** is the central accumulator: `analyze.py` builds it step by step and persists it as `model.model_dump()` (a plain dict) via `json.dumps`. `generate.py` loads it back with `AnalysisResult.model_validate(data)`.

### [`src/codebase_teacher/storage/database.py`](https://github.com/mpallone/codebase-teacher/blob/main/src/codebase_teacher/storage/database.py) — SQLite

**What it does:** Wraps SQLite with a lazy-connection pattern and provides typed operations for all five tables.

**Schema (`SCHEMA_SQL`):**

| Table | Purpose | Key columns |
|---|---|---|
| `schema_version` | Single-row version marker | `version INTEGER PRIMARY KEY` |
| `projects` | One row per target project root | `path TEXT UNIQUE`, `name TEXT` |
| `scan_state` | Folder relevance decisions | `project_id FK`, `folder_path`, `status CHECK(...)`, `UNIQUE(project_id, folder_path)` |
| `file_classifications` | File category + language + token estimate | `project_id FK`, `file_path`, `category`, `language`, `token_estimate`, `UNIQUE(project_id, file_path)` |
| `analysis_cache` | Serialized analysis results | `project_id FK`, `analyzer_name`, `file_path?`, `content_hash`, `result_json TEXT`, `UNIQUE(project_id, analyzer_name, file_path)` |
| `artifacts` | Written output files | `project_id FK`, `artifact_type`, `file_path` |

**`Database.__init__(db_path)`:** Stores path, sets `_conn = None`. The `conn` property implements lazy connection: first access creates the connection, sets `row_factory = sqlite3.Row` (enables dict-style row access), enables WAL journal mode (better write concurrency), enables foreign keys, and runs `_initialize()`.

**`_initialize()`:** Runs `SCHEMA_SQL` via `executescript` (idempotent due to `CREATE TABLE IF NOT EXISTS`). Checks `schema_version`; if empty, inserts `SCHEMA_VERSION = 1`. This provides a hook for future migrations.

**`INSERT OR REPLACE`:** Used in `set_folder_status`, `set_file_classification`, and `cache_analysis`. The `UNIQUE` constraints make this an upsert — re-running `scan` or `analyze` on the same project updates existing rows.

**`get_cached_analysis(..., content_hash)`:** Requires the hash to match. If source files have changed since the last run, the hash won't match and `None` is returned, forcing a re-analysis. The `analyze.py` command does not check this automatically — it always re-runs and overwrites the cache.

**`conn` property pattern:** Using a lazy property avoids holding an open SQLite connection during the entire process lifetime. The `close()` method explicitly closes and clears the connection.

### [`src/codebase_teacher/storage/artifact_store.py`](https://github.com/mpallone/codebase-teacher/blob/main/src/codebase_teacher/storage/artifact_store.py)

**What it does:** Writes generated files to the output directory and records them in the `artifacts` table.

**`ArtifactStore.__init__(output_dir, db, project_id)`:** Stores all three. Does not create directories yet.

**`write(artifact_type, filename, content)`:**
1. `subdir = output_dir / artifact_type` — e.g. `<project>/.teacher-output/docs`.
2. `subdir.mkdir(parents=True, exist_ok=True)`.
3. `filepath = subdir / filename`.
4. `filepath.write_text(content, encoding="utf-8")`.
5. Calls `db.record_artifact(project_id, artifact_type, str(filepath.relative_to(output_dir)))`.
6. Returns the absolute `Path` to the written file.

**`read(artifact_type, filename)`:** Reads and returns existing artifact content, or `None` if missing.

**`list_artifacts(artifact_type=None)`:** Delegates to `db.get_artifacts`.

---

## 11. Generator

### [`src/codebase_teacher/generator/docs.py`](https://github.com/mpallone/codebase-teacher/blob/main/src/codebase_teacher/generator/docs.py)

**What it does:** Generates three markdown documentation files: architecture overview, API reference, and infrastructure guide. Each is produced by one LLM call plus Jinja2 template rendering.

**Jinja2 environment:** Created by `_get_jinja_env()`. Uses `FileSystemLoader` pointing to `generator/templates/`. Autoescape is disabled (no HTML escaping needed for markdown). `trim_blocks=True` and `lstrip_blocks=True` prevent extra blank lines from Jinja control tags.

**`generate_architecture_doc(provider, analysis, store)`:**
1. Formats the prompt with:
   - `project_summary`: raw project summary string.
   - `module_summaries`: formatted as `"### {path}\n{summary}"` blocks.
   - `data_flows`: formatted as bullet lists (name, entry, steps, output).
   - `infrastructure`: formatted as bold technology name + bullet points.
   - `apis`: formatted as `"- METHOD /path -> handler (file): description"` lines.
2. Calls `provider.complete(messages)` — inherits the provider's configured output cap.
3. Renders `doc_page.md.j2` with `title="Architecture Overview"` and `body=response.content`.
4. Writes to `docs/architecture.md` via `store.write`.

**`generate_api_doc(provider, analysis, store)`:** Same pattern. If `analysis.api_endpoints` is empty, writes a short "no APIs found" message without an LLM call.

**`generate_infra_doc(provider, analysis, store)`:** Same pattern. If `analysis.infrastructure` is empty, writes a short placeholder.

**`generate_all_docs(provider, analysis, store)`:** Calls the three generators sequentially and returns their paths as a list. Sequential (not parallel) to avoid rate-limiting issues.

**Formatting helpers (`_format_module_summaries`, `_format_data_flows`, `_format_apis`, `_format_infrastructure`):** Convert the Pydantic model lists/dicts into multi-line strings for inclusion in prompts. Each handles the case where the input is either a Pydantic model (has `model_dump()`) or a plain dict (from the Pydantic `.model_dump()` output stored in the DB).

### [`src/codebase_teacher/generator/diagrams.py`](https://github.com/mpallone/codebase-teacher/blob/main/src/codebase_teacher/generator/diagrams.py)

**What it does:** Generates two Mermaid diagram files: an architecture diagram and a data flow diagram.

**`generate_architecture_diagram(provider, analysis, store)`:**
- Sends project summary, module list, infrastructure, and APIs to the LLM.
- System prompt instructs the LLM to output only Mermaid code (no prose), use `graph TD` or C4 style, max 15 nodes.
- Calls `_clean_mermaid(response.content)` to strip code fences if the LLM included them anyway.
- Wraps result in a markdown file: `` # Architecture Diagram\n\n```mermaid\n{code}\n``` ``.
- Writes to `diagrams/architecture.md`.

**`generate_data_flow_diagram(provider, analysis, store)`:**
- If `analysis.data_flows` has entries with `mermaid_diagram` fields (populated by `flow_tracer.py`), uses those directly. This avoids a redundant LLM call — the flow tracer already generated the diagrams.
- If no pre-generated diagrams exist, makes a fresh LLM call.
- Writes to `diagrams/data-flow.md`.

**`_clean_mermaid(text)`:** Regex `r"```(?:mermaid)?\s*\n(.*?)\n```"` with `re.DOTALL`. Strips the fences and returns just the Mermaid code. If no fence is found, returns the text stripped of whitespace.

### [`src/codebase_teacher/generator/templates/`](https://github.com/mpallone/codebase-teacher/blob/main/src/codebase_teacher/generator/templates/doc_page.md.j2)

**`doc_page.md.j2`:** A 7-line Jinja2 template:
```
# {{ title }}

*Generated by codebase-teacher*

---

{{ body }}
```

Every generated documentation page uses this wrapper. It adds the title as an H1 heading, a "Generated by" attribution line, a horizontal rule separator, and the LLM-generated body.

---

## 12. Tests

### [`tests/conftest.py`](https://github.com/mpallone/codebase-teacher/blob/main/tests/conftest.py)

**What it does:** Defines shared fixtures available to all test modules via pytest's fixture discovery.

**`MockLLMProvider`:** Satisfies the `LLMProvider` protocol without inheriting from it. Constructor takes an optional `responses: dict[str, str]` mapping keyword → response string. In `complete()`, it checks if any keyword appears (case-insensitive) in the last message's content and returns the corresponding canned response. Otherwise returns a default string. `_calls` accumulates all message lists — tests can inspect this to verify the LLM was called correctly. `context_window` returns `100_000`; `max_tokens` returns `16384` (matching the Settings default).

**Fixtures:**

| Fixture | Scope | What it provides |
|---|---|---|
| `mock_provider` | function | `MockLLMProvider` with canned responses for summarize, detect_apis, detect_infrastructure, trace_data_flow, architecture |
| `sample_project` | function | `Path` to `tests/fixtures/sample_project/` |
| `tmp_db` | function | `Database` in a `tmp_path`, auto-closed after test |
| `tmp_project` | function | Minimal Flask project in `tmp_path`: `main.py`, `src/utils.py`, `tests/test_utils.py`, `requirements.txt` |

**`tmp_project` structure:**
- `main.py`: Flask app with `@app.route("/health")` → `health()`.
- `src/__init__.py`, `src/utils.py`: `add(a, b)` with docstring.
- `tests/test_utils.py`: `test_add()`.
- `requirements.txt`: `flask==3.0.0\nredis==5.0.0`.

### [Fixtures: `tests/fixtures/sample_project/`](https://github.com/mpallone/codebase-teacher/blob/main/tests/fixtures/sample_project/)

A minimal Flask+Celery+SQLAlchemy application used by the analyzer and scanner tests.

**`app.py`:** Three Flask routes: `GET /api/users`, `POST /api/users`, `GET /api/users/<int:user_id>`. Uses `User.query`, `db.session`, and `send_welcome_email.delay(user.id)`.

**`models.py`:** `User` SQLAlchemy model with `id`, `name`, `email` columns and a `to_dict()` method.

**`tasks.py`:** Celery app with broker `redis://localhost:6379/0`. Two tasks: `send_welcome_email(user_id)` and `generate_report(report_type)`.

**`requirements.txt`:** `flask`, `flask-sqlalchemy`, `celery`, `redis`, `psycopg2-binary`. The `dependency.py` tests assert that `flask`, `celery`, and `redis` are detected from this file.

**`config.yaml`:** Database and Redis host/port config — used by the classifier to test `.yaml` → `config` category.

### [`tests/test_scanner/`](https://github.com/mpallone/codebase-teacher/blob/main/tests/test_scanner/)

**`test_discovery.py`:**
- `test_discover_folders`: Asserts `src` and `tests` appear in discovered folders, `.git` does not.
- `test_discover_folders_skips_pycache`: Creates `__pycache__`, asserts it's skipped.
- `test_discover_folders_empty_dir`: Empty dir returns `[]`.
- `test_build_folder_tree`: Just verifies the tree is non-null (smoke test).

**`test_file_classifier.py`:**
- Tests each category classification: Python source, test file, requirements.txt (build), full directory.
- `test_classify_with_relevant_folders`: Passes `["src"]` as relevant folders and asserts all returned paths contain `"src"`.

**`test_dependency.py`:**
- `test_detect_requirements_txt`: Checks `flask` and `redis` are in dep names.
- `test_detect_infra_hints`: Checks `"redis"` appears in hints (lowercase).
- `test_detect_no_dependencies`: Empty dir → empty result.
- `test_detect_sample_project`: Checks `flask`, `celery`, `redis` in the sample project's deps.

### [`tests/test_analyzer/`](https://github.com/mpallone/codebase-teacher/blob/main/tests/test_analyzer/)

**`test_code_parser.py`:**
- `test_parse_python_file`: Parses `sample_project/app.py`, asserts `list_users`, `create_user`, `get_user` are in functions. Checks `flask` import. Verifies `create_user`'s docstring and that its decorators contain `"route"`.
- `test_parse_python_file_with_class`: Parses `models.py`, asserts `User` class and `to_dict` method.
- `test_parse_codebase`: Parses all three sample project files, checks for functions from multiple files and the `User` class.
- `test_parse_async_function`: Writes a temp `async def fetch_data(url: str) -> dict:` file, asserts `is_async=True`.
- `test_parse_invalid_python`: Passes garbage Python, asserts empty graph returned (no exception).

**`test_api_detector.py`:**
- `test_detect_flask_routes`: Parses `app.py`, calls `detect_apis_from_ast`, asserts ≥2 endpoints, `/api/users` in paths, both GET and POST methods present.
- `test_detect_no_apis`: File with no decorators → empty list.

**`test_java_parser.py`:** Uses `pytest.importorskip("tree_sitter_java")` at the top — the entire file is skipped if the package isn't installed.

Key tests:
- `test_parse_simple_class`: Parses `UserService` with three methods.
- `test_parse_imports`: Checks `java.util` module, `List` or `ArrayList` in names.
- `test_parse_package_declaration`: Checks package appears as `ImportInfo` with `names=["<package>"]`.
- `test_parse_interface`: Checks `"<interface>"` in bases.
- `test_parse_annotated_class`: Parses `@Service` class with `@Override` method.
- `test_parse_enum`: Checks `"<enum>"` in bases.
- `test_parse_multiple_classes`: Parses two top-level classes in one file.
- `test_method_line_numbers`: Checks `line_number > 0`.
- `test_file_path_in_results`: Checks all classes have `file_path == "UserService.java"`.
- `test_graceful_on_invalid_java`: tree-sitter is error-tolerant; this verifies no exception is raised.
- `test_graceful_when_file_missing`: Missing file → empty graph.
- `test_terraform_resources_empty_for_java`: Java parser never populates terraform_resources.

**`test_terraform_parser.py`:** Also uses `pytest.importorskip("tree_sitter_hcl")`.

Tests cover: resources, data sources, variables, outputs, modules, providers, mixed file with all block types. Checks line numbers > 0, file paths populated, no functions/classes/imports for Terraform files. `test_hcl_extension` verifies `.hcl` files parse without error.

### [`tests/test_llm/`](https://github.com/mpallone/codebase-teacher/blob/main/tests/test_llm/)

**`test_context_manager.py`:**
- `test_estimate_tokens`: Empty → 0, 400 `"a"`s → 100.
- `test_context_manager_available_tokens`: `100_000 - 4000 - 16384 = 79_616`.
- `test_available_tokens_tracks_provider_max_tokens`: regression test pinning the contract that `reserved_response == provider.max_tokens`, so raising the output cap shrinks the input budget automatically.
- `test_fits_in_context`: Short text fits, 1M chars doesn't.
- `test_summarize_file` and `test_summarize_file_caching`: Async tests verifying file summary is returned and cached (same object on second call).
- `test_summarize_files_concurrent`: 3 files, `max_concurrent=2`, all 3 summaries returned.
- `test_build_context` and `test_build_context_with_focus`: Context string contains expected text.

**`test_structured.py`:**
- `test_extract_json_from_code_fence`: Fenced JSON extracted correctly.
- `test_extract_json_bare`, `test_extract_json_with_surrounding_text`, `test_extract_json_array`: Various formats.
- `test_parse_json_response_valid` and `_invalid`: Valid dict and invalid text.
- `test_parse_model`, `test_parse_model_list`: Parse into `SampleModel`.
- `test_parse_model_invalid_data`: Wrong field names → `LLMResponseError`.
- `test_parse_model_from_code_fence`: Fenced JSON parsed into model.

### [`tests/test_storage/`](https://github.com/mpallone/codebase-teacher/blob/main/tests/test_storage/)

**`test_database.py`:**
- `test_create_project`: ID is positive; second call with same path returns same ID.
- `test_folder_status`: `relevant`, `irrelevant`, `unknown` all stored and retrieved.
- `test_get_relevant_folders`: Filters to only relevant ones.
- `test_file_classification`: Source file stored; query by category returns it.
- `test_analysis_cache`: Stores and retrieves JSON result; wrong hash returns `None`.
- `test_artifacts`: Three artifacts inserted; filtered by type returns correct subset.

---

## 13. End-to-End Pipeline Trace

Here is what happens mechanically when a user runs all three commands on a Python project:

### `teach scan /path/to/project`

1. `cli()` stores `model=None`, `verbose=False` in `ctx.obj`.
2. `scan()` creates `Settings()` (reads `CODEBASE_TEACHER_*` env vars). Opens `<project>/.teacher/teacher.db`.
3. `get_or_create_project(str(root), root.name)` → returns e.g. `project_id = 1`.
4. `interactive_folder_selection(root, db, 1, console)`:
   - Loads existing folder decisions from DB (empty on first run).
   - Walks `root.iterdir()`, skips `.git`, `__pycache__`, etc.
   - Prints a Rich tree.
   - For each folder, prompts `y/n/s`. Persists to `scan_state`.
   - Returns e.g. `["src", "tests"]`.
5. `classify_directory(root, ["src", "tests"])`:
   - Walks every file under `src/` and `tests/`.
   - For each file: determines category and language, estimates tokens.
   - Returns list of `FileInfo`.
6. For each `FileInfo`, calls `db.set_file_classification(...)`. Stored in `file_classifications`.
7. `detect_dependencies(root)`:
   - Finds `requirements.txt`, parses package names.
   - Checks dep names against `_INFRA_KEYWORDS`, adds hints.
   - Checks for Docker/Terraform/K8s files.
8. Prints summary. Done. No LLM calls.

### `teach analyze /path/to/project`

1. Opens the same DB. Gets `project_id = 1`. Loads `relevant_folders = ["src", "tests"]`.
2. Loads `source_files` from `file_classifications` where `category = "source"`.
3. Creates `LiteLLMProvider("anthropic/claude-sonnet-4-20250514", max_tokens=16384)` and `ContextManager(provider, max_concurrent=5)`.
4. `parse_codebase(root, source_files)`:
   - For each `.py` file: `ast.parse` → extract functions, classes, imports.
   - Returns one `CodebaseGraph` with everything merged.
5. `detect_apis_from_ast(functions, classes)`:
   - Finds functions with `@app.route`, `@router.get`, etc.
   - Returns e.g. `[APIEndpoint(method="GET", path="/api/users", handler="list_users", ...)]`.
6. `_read_source_files(root, source_files)` → `dict[str, str]`.
7. `ctx_manager.summarize_files(file_contents)`:
   - For each file, fires `summarize_file(path, code)` with semaphore(5).
   - Each call: formats `"summarize_file"` prompt, calls `litellm.acompletion`.
   - Returns `list[FileSummary]`.
8. `_group_by_module(file_summaries)` → e.g. `{"src": [...], "tests": [...]}`.
9. For each module: `ctx_manager.summarize_module(path, file_summaries)` → one LLM call per module.
10. `ctx_manager.summarize_project(module_summaries)` → one LLM call.
11. `detect_apis(provider, file_contents)`:
    - Concatenates all files as code fences.
    - One LLM call with `"detect_apis"` prompt.
    - Parses JSON array into `list[APIEndpoint]`.
    - Merged with AST endpoints (dedup by handler name).
12. Reads config and infra files from DB; calls `detect_infrastructure(provider, infra_files, hints)` → one LLM call.
13. `trace_data_flows(provider, ...)` → one LLM call. Inherits the provider's configured `max_tokens`.
14. Assembles `AnalysisResult`. Computes SHA-256 hash of source files.
15. `db.cache_analysis(1, "full_analysis", hash, result.model_dump())` → stores `result_json` TEXT in `analysis_cache`.

### `teach generate /path/to/project`

1. Opens DB. Gets `project_id = 1`.
2. Queries `analysis_cache` for most recent `full_analysis` row. Deserializes via `AnalysisResult.model_validate(data)`.
3. Creates `LiteLLMProvider` and `ArtifactStore(output_dir=<project>/.teacher-output, db, project_id=1)`.
4. `generate_all_docs(provider, analysis, store)`:
   - `generate_architecture_doc`: formats prompt with project/module/flow/infra/api data. One LLM call. Renders `doc_page.md.j2`. Writes to `.teacher-output/docs/architecture.md`.
   - `generate_api_doc`: same pattern. Writes to `.teacher-output/docs/api-reference.md`.
   - `generate_infra_doc`: same pattern. Writes to `.teacher-output/docs/infrastructure.md`.
5. `generate_all_diagrams(provider, analysis, store)`:
   - `generate_architecture_diagram`: LLM returns only Mermaid code. Writes to `.teacher-output/diagrams/architecture.md`.
   - `generate_data_flow_diagram`: Uses pre-generated diagrams from `analysis.data_flows` if available; otherwise one LLM call. Writes to `.teacher-output/diagrams/data-flow.md`.
6. Each write is recorded in the `artifacts` table.
7. Total output: 5 markdown files in `.teacher-output/`.

---

*End of walkthrough.*
