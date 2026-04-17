# TODO

## Generated Output Improvements

1. [x] Add a friendly overview document to generated output (e.g. a README.md or "Start Here" page).
   Implemented as `.teacher-output/docs/overview.md` (generated first by
   `generate_all_docs`). Uses a dedicated prompt that asks the LLM to produce
   a plain-language "What is this?", "Why does it exist?" (with one concrete
   usage example), a short high-level walkthrough, and pointers to the other
   generated docs. See `generator/docs.py::generate_overview_doc`.
2. [ ] **Interactive HTML output** (replaces old TODOs #2 and #3, merged after research).
   **Background:** Researched what Claude Code, Codex CLI, Gemini CLI, Windsurf,
   and Aider can produce. Key findings:
   - All CLI tools write files to disk. None have built-in HTML rendering.
   - **Standalone `.html` files are the universal, portable output format.**
     No need for provider-specific formats or fallback detection.
   - Claude Code and Gemini 2.5 Pro produce the highest-quality frontend code.
     Codex CLI is weaker on frontend (~68% vs ~95% benchmark).
   - Web-UI features (Claude Artifacts, Gemini Canvas, ChatGPT Canvas) are
     irrelevant here — codebase-teacher runs via CLI and writes to disk.
   - The current generation architecture (AnalysisResult → generator layer)
     cleanly separates data from presentation, so adding HTML output does not
     require touching the analysis pipeline.

   The work is split into three phases. Keep markdown as the default output;
   HTML is an opt-in `--format html` flag (or similar). **All HTML output must
   be mobile-friendly** — responsive layout, readable on small screens, touch
   targets sized appropriately. This applies to every phase.

   ### Phase 1: Static HTML shell with rendered diagrams
   - [x] 2a. Create an HTML page template (Jinja2) that replaces `doc_page.md.j2`.
         Single-file or small file set. Inline CSS for styling (no build step).
         Include: styled typography, a sidebar nav linking all generated docs,
         collapsible `<details>` sections for long content, a light/dark toggle.
         Use responsive CSS (media queries, fluid widths) so the layout works
         on mobile — sidebar collapses to a hamburger menu or top nav on small
         screens.
         Implemented as `generator/templates/doc_page.html.j2` — single-page HTML
         with inline CSS custom properties (light/dark), fixed sidebar with
         scroll-spy active highlighting, hamburger menu on mobile (<768px),
         collapsible `<details>` sections, and theme toggle with localStorage
         persistence. See `generator/html.py::generate_html_page`.
   - [x] 2b. Render Mermaid diagrams live by including `mermaid.js` from CDN in a
         `<script>` tag. Convert existing ``` mermaid ``` code blocks into
         `<pre class="mermaid">` blocks that mermaid.js picks up automatically.
         Implemented with mermaid.js v11.4.1 CDN. Diagrams render individually
         with error recovery — broken diagrams show source code as fallback.
         `_sanitize_mermaid()` cleans LLM output (smart quotes, em/en dashes).
         Theme toggle re-renders diagrams with matching mermaid theme.
   - [x] 2c. Add a `--format` flag to the CLI (`markdown` default, `html` option).
         When `html` is selected, use the HTML template instead of the markdown
         template. Output goes to the same `.teacher-output/` directory.
         Implemented in `cli/generate.py`. HTML mode produces a single
         `index.html` in `.teacher-output/`. API doc generation uses chunking
         (groups of 20 endpoints) to avoid timeouts on large codebases.
         CLI timeout is now configurable via `cli_timeout` setting (default 600s).
   - [x] 2d. Ensure the HTML output is fully self-contained (opens in any browser
         with no server, no build step). The only external dependency allowed is
         the mermaid.js CDN script tag.
         Confirmed: all CSS is inline, all content embedded, only external
         resource is the pinned mermaid.js CDN script.

   ### Phase 2: Rich standalone visualizations — Not planned
   Previously scoped as D3.js force-directed architecture explorer, animated
   request-flow walkthrough, `--rich-visualizations` flag, and cross-browser
   testing. Removed because:
   - Phase 1 already ships an LLM-generated Mermaid architecture diagram and
     per-flow sequence diagrams (`generator/html.py:157-205`).
   - `AnalysisResult` has no precomputed module→module edge list and
     `DataFlow.steps` is `list[str]` (`storage/models.py:124-143`), so a D3
     graph would be sparser than the existing Mermaid one and an "animated
     walkthrough" would be a click-through of names.
   - Adding D3 either pulls in a large CDN dep or breaks the "no build step"
     guarantee from Phase 1 item 2d.
   - Real mermaid pain points are bugs #18 and #31, which D3 does not address.
   Revisit only if the analyzer grows a real dependency graph.

## Pipeline Parallelism & Failure Surfacing

30. [ ] **Parallelize LLM calls, make concurrency configurable, and surface
    silent section-generation failures.**

    **Motivation.** Running `teach generate --format html` on httpbin
    (6 source files, 55 endpoints) took 16m 6s because each section is
    generated via a sequential `claude` CLI subprocess call. One section
    (API Reference) hit the 600s `cli_timeout`, was caught per-section,
    and silently dropped from the output — the sidebar in `index.html`
    just omitted the link. Users reading the generated artifact had no
    way to know a section was missing.

    **Work items (all under one change):**

    - [ ] Parallelize section generation in HTML output.
          `src/codebase_teacher/generator/html.py::generate_html_page`
          (lines 296-339) runs `doc_specs` (4 entries) and diagram
          sections (2 entries) in sequential `for … await` loops. Replace
          with `asyncio.gather(...)` bounded by a shared
          `asyncio.Semaphore`. Preserve the existing per-section
          `try/except LLMError` behavior so a single failure doesn't
          abort the gather.
    - [ ] Parallelize doc generation in markdown output.
          `src/codebase_teacher/generator/docs.py::generate_all_docs`
          (lines 240-244) has the same sequential loop pattern. Same fix
          — `asyncio.gather` with the shared semaphore.
    - [ ] Parallelize module summarization in analyze.
          `src/codebase_teacher/cli/analyze.py` (lines 152-155) serializes
          `ctx_manager.summarize_module(...)` calls. Reuse the semaphore
          already held by `ContextManager`
          (`src/codebase_teacher/llm/context_manager.py:105`) and gather
          the module summaries.
    - [ ] Parallelize API-reference chunk calls.
          In `generator/html.py::_generate_api_section_chunked` (called
          at line 319) and the equivalent path in `generator/docs.py`,
          run chunk generation calls concurrently rather than
          sequentially. Use the same shared semaphore.
    - [ ] Make concurrency configurable. Bump
          `max_concurrent_llm_calls` default from 5 to 10 in
          `src/codebase_teacher/core/config.py:37`. Thread the value
          through to the generator layer (currently only `ContextManager`
          uses it — `llm/context_manager.py:53-59, 105`). Exposed via env
          var `CODEBASE_TEACHER_MAX_CONCURRENT_LLM_CALLS` (existing
          mechanism).
    - [ ] Reduce API chunk size from 20 to 5. Change
          `API_CHUNK_SIZE = 20` at
          `src/codebase_teacher/generator/docs.py:104` to `5`. Smaller
          chunks keep each `claude` CLI call well under the 600s timeout,
          and combined with parallel chunk execution the wall-clock
          impact is net-positive.
    - [ ] Surface silent section failures in the artifact itself.
          The CLI already prints `[red]Failed:[/]` lines
          (`cli/generate.py:90-91, 100-113`), but the HTML/markdown
          output gives the user no indication anything is missing. Fix
          in two layers:
          1. **Banner.** In the HTML template
             (`generator/templates/doc_page.html.j2`, rendered by
             `generator/html.py::generate_html_page` at line 347), render
             a visible top-of-page banner when `errors` is non-empty,
             listing each failed section name and the error class. For
             markdown, write a `.teacher-output/docs/TEACHER-ERRORS.md`
             file and add a "Generation errors" note to the top of
             `overview.md`.
          2. **Placeholder sections.** For each failed section, append a
             `Section` to `sections` (before line 341) with a body like
             "This section failed to generate: {error}. Rerun
             `teach generate` or increase
             `CODEBASE_TEACHER_CLI_TIMEOUT`." so the sidebar link appears
             and the gap is visible in the navigation. Do the same for
             missing markdown docs.

    **Acceptance criteria:**
    - Running `uv run teach generate --format html tests/repos/httpbin`
      completes meaningfully faster than the current 16m baseline
      (target: under 6m on the same hardware).
    - When a section deliberately fails (e.g., by setting
      `CODEBASE_TEACHER_CLI_TIMEOUT=1` to force timeouts), the resulting
      `index.html` shows (a) a top-of-page error banner and (b) a
      placeholder section with a sidebar link for every failed section.
    - `max_concurrent_llm_calls` defaults to 10 and its value is
      respected by both analyze and generate phases (verifiable by
      setting it to 1 and observing serialized behavior).
    - `API_CHUNK_SIZE` is 5; httpbin's 55 endpoints produce 11 chunks,
      generated concurrently.
    - All existing tests in `uv run pytest` pass. New tests cover: the
      shared-semaphore wiring, the failed-section banner rendering, the
      placeholder-section insertion, and the chunk-size constant.

## Future CLI Providers

4. [ ] Add Codex CLI provider (`codex`)
5. [ ] Add Windsurf CLI provider
6. [ ] Add Gemini CLI provider

## Claude Code Integration

7. [x] Create Claude Code subagent (`.claude/agents/teach.md`) for one-command pipeline invocation

## Progress Status During teach-evaluate-push

19. [x] Add progress status output to the `/teach-evaluate-push` skill and `/agents/teach`
    subagent so the user can see how far along the pipeline is while it runs.
    Currently the workflow is long-running and produces no visible output until the
    very end (final timing summary and assessment). The user has no indication of
    which phase is active or how much remains.

    **Where to add status banners:**

    Each status line should be printed to the user as a clear, visible banner
    (e.g., `## [1/6] Scanning repository...`) before the corresponding step begins,
    and a short completion note when it finishes (including elapsed time for that step).

    - **teach-evaluate-push skill** (`teach-evaluate-push.md`):
      - [x] On entry: print `## Starting teach-evaluate-push pipeline` with the
            target path and format.
      - [x] Before launching subagent: print `## [1/3] Launching teach subagent...`
      - [x] After subagent returns: print `## [2/3] Teach subagent complete ({duration}s). Starting post-teach workflow...`
      - [x] After post-teach workflow completes: print `## [3/3] Post-teach workflow complete ({duration}s).`

    - **teach subagent** (`agents/teach.md`):
      - [x] Before scan: print `## [Step 1/4] Scanning repository ({path})...`
      - [x] After scan: print `## [Step 1/4] Scan complete ({scan_duration}s).`
      - [x] Before analyze: print `## [Step 2/4] Analyzing codebase...`
      - [x] After analyze: print `## [Step 2/4] Analysis complete ({analyze_duration}s).`
      - [x] Before generate: print `## [Step 3/4] Generating {format} output...`
      - [x] After generate: print `## [Step 3/4] Generation complete ({generate_duration}s).`
      - [x] Before evaluation: print `## [Step 4/4] Evaluating generated output...`
      - [x] After evaluation: print `## [Step 4/4] Evaluation complete.`

    - **Post-Teach Workflow** (AGENTS.md):
      - [x] Before displaying assessment: print `## Displaying assessment...`
      - [x] Before staging: print `## Copying output to .teacher-staging/...`
      - [x] Before git operations: print `## Creating branch, committing, and pushing...`
      - [x] After push: print `## Push complete. Generating links...`

## Real Repo Testing

8. [x] Add httpbin (`postmanlabs/httpbin`) as first test repo (git submodule in `tests/repos/`)
9. [x] Run tool against httpbin and evaluate output quality
10. [x] Bug: Infrastructure detection returned 0 results for httpbin despite Dockerfile existing.
    The scan step correctly detected Docker (`Infrastructure detected: Docker (containerization)`)
    but the analyze step's LLM infrastructure detection produced 0 `InfraComponent` objects, so
    `infrastructure.md` was empty. Fixed by (a) strengthening the `detect_infrastructure` prompt
    to cover containers, orchestration, and IaC and to treat scanner hints as authoritative,
    (b) adding a minimal `_fallback_from_hints()` in `analyzer/infra_detector.py` that preserves
    scanner hints when the LLM returns nothing, and (c) adding a filesystem fallback in
    `cli/analyze.py` that scans root-level files through the existing file classifier so
    Dockerfiles always reach the LLM even if `teach scan` wasn't run.
11. [x] Add fastapi-realworld-example-app as tier 2 test repo
12. [x] Add spring-petclinic (Java) as tier 3 test repo
13. [ ] Add a small Terraform repo to exercise HCL parsing
14. [ ] Once confidence in the tool is established, externalize or remove the test repo
    submodules from this project. The submodules are a development-time scaffold,
    not a permanent part of the repo. Options: move to a separate test-harness repo,
    or rely on the subagent to clone repos on-the-fly instead.

## Existing

15. [ ] Automated end-to-end LLM-judged test harness:
    - Need to test this stuff against a codebase.
    - Have a mock codebase as a test artifact. Mock codebase should be complex enough to exercise all features of codebase-teacher.
    - Test code should run the tool against that mock codebase and generate output artifacts.
    - An LLM should compare (1) the code to (2) the teaching artifacts and verify that everything looks good.
    - The LLM should build its own knowledge of the code and make sure key things are included.
    - The LLM should check teaching artifacts and sanity-check that the claims are true.
    - All of this should be fully automated.
    - Because it requires LLM usage, this might be something that only gets manually kicked off, but runs beginning-to-end without user input.
    - Ensure this feature is documented.
16. [ ] Double-check all languages I need to use this on, and add support for them.
17. [ ] Add support for C++ (file classification + tree-sitter AST parsing, matching existing language support).
18. [ ] Fix mermaid diagram rendering on mobile. Diagrams break or render incorrectly
    on device rotation. Reproduce using browser dev tools on laptop to simulate mobile
    device rotation, grab the console logs, feed them to Claude, and iterate until fixed.
31. [ ] Bug: zooming in/out on a mermaid diagram crashes the page. Will probably need to
    debug in a PC browser. May be the same root cause as item #18 (mermaid diagrams
    breaking on mobile device rotation) — both involve mermaid misbehaving when the
    viewport scale changes.

## Deeper Analysis

These items extend the existing `teach analyze` pipeline to capture more about a codebase.
Each follows the established pattern: new analyzer → new fields on `AnalysisResult` → new
doc section in `teach generate` output.

20. [ ] **Test coverage analysis.** Detect test files (the file classifier already tags
    `category=test`), count test functions, cross-reference against source modules using
    import analysis and naming conventions, and have the LLM assess whether coverage
    appears adequate. Output: a new `docs/test-coverage.md` section listing which modules
    have tests, what types of tests exist (unit, integration, e2e), and what major code
    paths appear untested.

    **Feasibility: Good.** File classifier + AST parser already provide the raw data.
    This is primarily prompt engineering plus a cross-reference heuristic. Note: the output
    is qualitative ("module X has no tests"), not quantitative line coverage — it is not a
    replacement for `coverage.py`, but is useful for onboarding.

21. [ ] **Production configuration analysis.** Detect config files (already classified),
    identify environment-specific configs (dev/staging/prod), document what configuration
    knobs exist, which are required, and what their defaults are. Output: a new
    `docs/configuration.md` section.

    **Feasibility: Good with caveats.** Many repos keep prod config outside the repo
    (Vault, SSM, environment variables). The tool should document what it *can* see and
    explicitly flag what appears to be missing or externally managed. "How do I configure
    this to run locally?" is always the first question a new engineer asks, so this has
    high onboarding value even with incomplete information.

22. [ ] **Operational readiness analysis** (alerts + dashboards + failure modes, combined).
    Single doc section covering:
    - **Alerts:** Detect alerting rules (Prometheus `.rules`, Terraform alert resources,
      Datadog monitors-as-code). Document what each alert watches, what it means when it
      fires, and how to respond.
    - **Dashboards:** Detect dashboard definitions (Grafana JSON, Datadog
      dashboards-as-code). Document what metrics are visualized.
    - **Failure modes:** For each infrastructure dependency identified by the existing
      infra detector, analyze what happens if it fails. Are there retries, circuit
      breakers, fallbacks, graceful degradation? Are existing alerts adequate for each
      failure scenario?
    Output: a new `docs/operational-readiness.md` section.

    **Feasibility: Moderate.** Alert and dashboard detection only works when config-as-code
    is present — many orgs keep these in UIs, so the tool will often find nothing. The
    failure mode analysis is higher value: it is LLM-driven reasoning over existing
    infrastructure + data flow data. Even speculative output is useful ("no retry logic
    detected for database calls"). When alert/dashboard configs are absent, the doc should
    say so and recommend what observability *should* exist.

23. [ ] **Dependency sanity checks.** After scanning dependencies, have the LLM review the
    dependency list + project summary and flag anything that appears missing or
    misconfigured. Check whether prod config, alert config, and dashboard config exist in
    the repo. Output: a "sanity check" summary at the top of the generated docs.

    **Feasibility: Moderate.** What's "critical" is stack-dependent, but the LLM is good
    at this reasoning (e.g., "Flask app with no WSGI server in requirements"). This is
    distinct from providing install instructions for missing libraries (which duplicates
    package managers and is out of scope).

## Teaching Artifacts

These are new document types generated from the existing `AnalysisResult`. They fit the
existing `generate` architecture — just differently-structured output. All teaching content
targets a Senior Software Engineer who is experienced but unfamiliar with the specific
codebase, per the product spec's style guidance.

24. [ ] **Lecture generation (pipeline-ordered).** Generate a structured walkthrough that
    teaches the codebase following data flow order: entry points (API routes, consumers) →
    transformations (business logic, side effects) → outputs (DB writes, responses,
    published events). The existing `DataFlow` analysis provides the ordering.

    This is the **highest-value teaching feature** from the product spec. A lecture is a
    differently-organized view of the existing analysis: instead of "here's the
    architecture" (reference doc), it's "let me walk you through this step by step"
    (tutorial). New CLI surface: either `teach lecture <path>` or a `--type lecture` flag
    on `teach generate`. Output: `lectures/` directory in `.teacher-output/`.

    **Feasibility: Good.** New prompt + generator function following the established
    pattern. The hard part is getting the LLM to order content by data flow rather than
    by directory structure. The data flow traces already exist to inform this ordering.

25. [ ] **Flashcard / offline quiz generation.** Generate markdown flashcards with Q/A
    format. Questions like "What does module X do?", "What happens when endpoint Y is
    called?", "What infrastructure does Z depend on?" Answers include justifications
    referencing the actual code (per the product spec's requirement for offline learning
    artifacts with clear justifications).

    Format: markdown file using `<details>` tags for answer reveal. Usable without an
    internet connection. Output: `.teacher-output/flashcards.md`.

    **Feasibility: Good.** Straightforward LLM generation from existing analysis data.
    Low implementation cost, moderate learning value.

26. [ ] **On-call practice scenarios.** Generate realistic on-call scenarios based on the
    actual infrastructure, APIs, and failure modes of the target codebase. Example: "You
    get paged at 2am. Service X is returning 500s. Dashboard shows Y. Walk through your
    debugging steps." Include expected investigation steps and resolution.

    Produces markdown, not interactive. Ideally builds on operational readiness analysis
    (#22) for more realistic scenarios. Output: `.teacher-output/scenarios.md`.

    **Feasibility: Good.** Natural LLM task. Quality depends on prompt engineering.
    Scenarios will be synthetic (no actual production incident history), but still valuable
    for building on-call intuition about a specific codebase. Set expectations that these
    are practice exercises, not runbooks.

27. [ ] **Exercise generation (without scoring).** Generate exercises for the learner to
    complete: implement a small feature, improve test coverage for a specific module, make
    the codebase run locally. Include rubrics describing what a good solution looks like.

    **Automated scoring is deferred** — it is a fundamentally different problem requiring
    either code execution (build environment) or LLM evaluation of solutions (unreliable,
    expensive). For now, generate exercise descriptions with rubrics only.

    **Feasibility: Moderate.** Lower value-to-effort ratio than lectures and flashcards.
    Exercises risk being generic without deep codebase understanding. Prioritize after
    #24-26.

## Learner Evaluation

28. [ ] **CLI quiz / knowledge evaluation.** New command: `teach evaluate <path>`. Runs an
    interactive CLI quiz: asks N questions about the codebase, the learner types answers,
    and the LLM scores each answer against the `AnalysisResult` ground truth. Output: a
    scorecard markdown file summarizing performance across dimensions.

    Evaluation dimensions should emerge naturally from whatever analysis capabilities
    exist (API knowledge, infrastructure knowledge, data flow understanding, configuration
    knowledge, operational readiness) rather than being predefined.

    **Feasibility: Architecturally clear, UX-novel.** This is the tool's first REPL-style
    interaction — a significant new CLI pattern. **Defer until teaching artifacts (#24-27)
    are validated**, since evaluation presupposes teaching content exists.

## Interactive Teaching

29. [ ] **Interactive teaching via generated Claude Code commands.** Reduced scope approach:
    generate a `.claude/commands/learn-<repo>.md` custom command that a learner can invoke
    to start a guided conversation with the analysis results pre-loaded as context. This
    leverages Claude Code's existing interactive capabilities rather than building a custom
    REPL from scratch.

    The product spec flags this as an open question ("not sure exactly what this would
    look like"). Start with a simple "quiz me" / "teach me about <topic>" command that has
    the `AnalysisResult` summary, data flows, and infrastructure baked into its system
    context. The learner gets an interactive conversational tutor backed by real analysis
    of their codebase.

    **Feasibility: Moderate.** The tool already generates markdown artifacts. Generating a
    Claude Code command file that includes key analysis context is a natural extension. The
    interactive experience is delegated to Claude Code itself. Open question: how to keep
    the command file within context limits for large codebases (may need to summarize
    aggressively or reference generated docs rather than inlining everything).
