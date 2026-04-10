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

## Future CLI Providers

3. [ ] Add Codex CLI provider (`codex`)
4. [ ] Add Windsurf CLI provider
5. [ ] Add Gemini CLI provider

## Claude Code Integration

6. [x] Create Claude Code subagent (`.claude/agents/teach.md`) for one-command pipeline invocation

## Real Repo Testing

7. [x] Add httpbin (`postmanlabs/httpbin`) as first test repo (git submodule in `tests/repos/`)
8. [x] Run tool against httpbin and evaluate output quality
9. [ ] Bug: Infrastructure detection returned 0 results for httpbin despite Dockerfile existing.
   The scan step correctly detected Docker (`Infrastructure detected: Docker (containerization)`)
   but the analyze step's LLM infrastructure detection produced 0 `InfraComponent` objects, so
   `infrastructure.md` is empty. Likely cause: scan-detected infra hints aren't passed through
   to the LLM infra detection prompt, or the prompt is biased toward databases/queues and ignores
   Dockerfiles. Investigate `analyzer/infra_detector.py` and the `detect_infrastructure()` call
   in `cli/analyze.py`.
10. [ ] Add fastapi-realworld-example-app as tier 2 test repo
11. [ ] Add spring-petclinic (Java) as tier 3 test repo
12. [ ] Add a small Terraform repo to exercise HCL parsing
13. [ ] Once confidence in the tool is established, externalize or remove the test repo
    submodules from this project. The submodules are a development-time scaffold,
    not a permanent part of the repo. Options: move to a separate test-harness repo,
    or rely on the subagent to clone repos on-the-fly instead.

## Existing

14. [ ] Automated end-to-end LLM-judged test harness:
    - Need to test this stuff against a codebase.
    - Have a mock codebase as a test artifact. Mock codebase should be complex enough to exercise all features of codebase-teacher.
    - Test code should run the tool against that mock codebase and generate output artifacts.
    - An LLM should compare (1) the code to (2) the teaching artifacts and verify that everything looks good.
    - The LLM should build its own knowledge of the code and make sure key things are included.
    - The LLM should check teaching artifacts and sanity-check that the claims are true.
    - All of this should be fully automated.
    - Because it requires LLM usage, this might be something that only gets manually kicked off, but runs beginning-to-end without user input.
    - Ensure this feature is documented.
15. [ ] Double-check all languages I need to use this on, and add support for them.
16. [ ] Add support for C++ (file classification + tree-sitter AST parsing, matching existing language support).
