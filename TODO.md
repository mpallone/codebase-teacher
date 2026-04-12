# TODO

## Generated Output Improvements

1. [x] Add a friendly overview document to generated output (e.g. a README.md or "Start Here" page).
   Implemented as `.teacher-output/docs/overview.md` (generated first by
   `generate_all_docs`). Uses a dedicated prompt that asks the LLM to produce
   a plain-language "What is this?", "Why does it exist?" (with one concrete
   usage example), a short high-level walkthrough, and pointers to the other
   generated docs. See `generator/docs.py::generate_overview_doc`.
2. [ ] Explore HTML output as an alternative (or complement) to markdown.
   HTML could be friendlier for reading generated docs:
   - Collapsible sections — hide detail until you need it, less overwhelming
   - Live Mermaid diagram rendering — see actual diagrams, not code blocks
   - Sidebar navigation — jump between docs/sections without scrolling
   - Styled visual hierarchy — guide the eye to what matters first
   Markdown still renders well on GitHub and is easy to edit. Could do both:
   markdown as source of truth, HTML as the polished browsable output.
3. [ ] Explore rich/dynamic LLM-generated visualizations beyond static markdown.
   Modern coding agents (Claude, and likely Gemini/Codex/others) can generate
   dynamic, interactive explanatory content — not just markdown with Mermaid blocks.
   Examples of what could be possible:
   - Interactive HTML artifacts (collapsible call trees, clickable architecture
     diagrams, hoverable tooltips on code entities, zoomable dependency graphs)
   - Animated walkthroughs of request flows or state transitions
   - Embedded runnable snippets or sandboxed demos
   - Custom SVG/Canvas visualizations generated on-the-fly for concepts that
     don't map cleanly to Mermaid (e.g. memory layouts, concurrency timelines,
     data pipeline flows)
   Open questions to investigate:
   - Which providers support rich output natively (Claude artifacts, Gemini
     equivalents, Codex, etc.) and how portable is the format across them?
   - Can we have the generator LLM emit self-contained HTML/JS artifacts as
     part of the teaching output, or do these need a host environment to render?
   - Is there a common denominator (e.g. standalone HTML files) that works
     everywhere, vs. provider-specific formats that we detect and fall back from?
   - How does this interact with TODO #2 (HTML as browsable output)? These
     might be the same project or complementary.
   This is speculative — the point is to capture the idea before it's lost and
   revisit once we know more about what each CLI provider supports.

## Future CLI Providers

4. [ ] Add Codex CLI provider (`codex`)
5. [ ] Add Windsurf CLI provider
6. [ ] Add Gemini CLI provider

## Claude Code Integration

7. [x] Create Claude Code subagent (`.claude/agents/teach.md`) for one-command pipeline invocation

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
