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

   ### Phase 2: Rich standalone visualizations
   - [ ] 2h. Generate dedicated interactive visualization files (e.g.
         `architecture-explorer.html`) using D3.js force-directed graphs or
         similar. These are separate files linked from the main docs.
         Feed the AnalysisResult data (modules, dependencies, APIs) as inline
         JSON so D3.js can render it client-side.
   - [ ] 2i. Add an animated request-flow walkthrough: a step-by-step visualization
         that highlights each component in sequence as a request passes through
         the system. Use the existing DataFlow analysis as input.
   - [ ] 2j. Gate Phase 2 behind a `--rich-visualizations` flag (off by default).
         These files are larger and slower to generate. Only attempt with
         providers known to produce good frontend code (document which ones).
   - [ ] 2k. Test Phase 2 output across Chrome, Firefox, and Safari (desktop
         and mobile) to ensure no browser-specific or responsive layout issues
         with the generated JS and CSS.

## Future CLI Providers

4. [ ] Add Codex CLI provider (`codex`)
5. [ ] Add Windsurf CLI provider
6. [ ] Add Gemini CLI provider

## Claude Code Integration

7. [x] Create Claude Code subagent (`.claude/agents/teach.md`) for one-command pipeline invocation

## Progress Status During teach-evaluate-push

19. [ ] Add progress status output to the `/teach-evaluate-push` skill and `/agents/teach`
    subagent so the user can see how far along the pipeline is while it runs.
    Currently the workflow is long-running and produces no visible output until the
    very end (final timing summary and assessment). The user has no indication of
    which phase is active or how much remains.

    **Where to add status banners:**

    Each status line should be printed to the user as a clear, visible banner
    (e.g., `## [1/6] Scanning repository...`) before the corresponding step begins,
    and a short completion note when it finishes (including elapsed time for that step).

    - **teach-evaluate-push skill** (`teach-evaluate-push.md`):
      - [ ] On entry: print `## Starting teach-evaluate-push pipeline` with the
            target path and format.
      - [ ] Before launching subagent: print `## [1/3] Launching teach subagent...`
      - [ ] After subagent returns: print `## [2/3] Teach subagent complete ({duration}s). Starting post-teach workflow...`
      - [ ] After post-teach workflow completes: print `## [3/3] Post-teach workflow complete ({duration}s).`

    - **teach subagent** (`agents/teach.md`):
      - [ ] Before scan: print `## [Step 1/4] Scanning repository ({path})...`
      - [ ] After scan: print `## [Step 1/4] Scan complete ({scan_duration}s).`
      - [ ] Before analyze: print `## [Step 2/4] Analyzing codebase...`
      - [ ] After analyze: print `## [Step 2/4] Analysis complete ({analyze_duration}s).`
      - [ ] Before generate: print `## [Step 3/4] Generating {format} output...`
      - [ ] After generate: print `## [Step 3/4] Generation complete ({generate_duration}s).`
      - [ ] Before evaluation: print `## [Step 4/4] Evaluating generated output...`
      - [ ] After evaluation: print `## [Step 4/4] Evaluation complete.`

    - **Post-Teach Workflow** (AGENTS.md):
      - [ ] Before displaying assessment: print `## Displaying assessment...`
      - [ ] Before staging: print `## Copying output to .teacher-staging/...`
      - [ ] Before git operations: print `## Creating branch, committing, and pushing...`
      - [ ] After push: print `## Push complete. Generating links...`

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
11. [ ] Add fastapi-realworld-example-app as tier 2 test repo
12. [ ] Add spring-petclinic (Java) as tier 3 test repo
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
