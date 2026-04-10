# TODO

## Generated Output Improvements

- [ ] Add a friendly overview document to generated output (e.g. a README.md or "Start Here" page).
  The current docs (architecture.md, api-reference.md) are thorough but can feel overwhelming.
  The overview should answer upfront:
  - **What does this codebase do?** Plain-language purpose, not implementation details.
  - **Why is it valuable?** Business value, who uses it, what problem it solves.
    Include concrete examples (hypothetical is fine). E.g. for httpbin: "An HTTP client
    library author uses httpbin to verify their library correctly handles gzip responses,
    digest auth, and redirect chains — without standing up a custom test server."
  - **High-level codebase walkthrough.** A short, skimmable tour of the major pieces
    and how they connect. Not every file — just enough that a dev can orient themselves
    in a few minutes. Think "trail map", not "street-by-street atlas."
  This should be the first thing a new developer reads before diving into architecture.md.
- [ ] Explore HTML output as an alternative (or complement) to markdown.
  HTML could be friendlier for reading generated docs:
  - Collapsible sections — hide detail until you need it, less overwhelming
  - Live Mermaid diagram rendering — see actual diagrams, not code blocks
  - Sidebar navigation — jump between docs/sections without scrolling
  - Styled visual hierarchy — guide the eye to what matters first
  Markdown still renders well on GitHub and is easy to edit. Could do both:
  markdown as source of truth, HTML as the polished browsable output.

## Future CLI Providers

- [ ] Add Codex CLI provider (`codex`)
- [ ] Add Windsurf CLI provider
- [ ] Add Gemini CLI provider

## Claude Code Integration

- [x] Create Claude Code subagent (`.claude/agents/teach.md`) for one-command pipeline invocation

## Real Repo Testing

- [x] Add httpbin (`postmanlabs/httpbin`) as first test repo (git submodule in `tests/repos/`)
- [x] Run tool against httpbin and evaluate output quality
- [ ] Bug: Infrastructure detection returned 0 results for httpbin despite Dockerfile existing.
  The scan step correctly detected Docker (`Infrastructure detected: Docker (containerization)`)
  but the analyze step's LLM infrastructure detection produced 0 `InfraComponent` objects, so
  `infrastructure.md` is empty. Likely cause: scan-detected infra hints aren't passed through
  to the LLM infra detection prompt, or the prompt is biased toward databases/queues and ignores
  Dockerfiles. Investigate `analyzer/infra_detector.py` and the `detect_infrastructure()` call
  in `cli/analyze.py`.
- [ ] Add fastapi-realworld-example-app as tier 2 test repo
- [ ] Add spring-petclinic (Java) as tier 3 test repo
- [ ] Add a small Terraform repo to exercise HCL parsing
- [ ] Once confidence in the tool is established, externalize or remove the test repo
  submodules from this project. The submodules are a development-time scaffold,
  not a permanent part of the repo. Options: move to a separate test-harness repo,
  or rely on the subagent to clone repos on-the-fly instead.

## Existing

- Automated end-to-end LLM-judged test harness:
  - Need to test this stuff against a codebase.
  - Have a mock codebase as a test artifact. Mock codebase should be complex enough to exercise all features of codebase-teacher.
  - Test code should run the tool against that mock codebase and generate output artifacts.
  - An LLM should compare (1) the code to (2) the teaching artifacts and verify that everything looks good.
  - The LLM should build its own knowledge of the code and make sure key things are included.
  - The LLM should check teaching artifacts and sanity-check that the claims are true.
  - All of this should be fully automated.
  - Because it requires LLM usage, this might be something that only gets manually kicked off, but runs beginning-to-end without user input.
  - Ensure this feature is documented.
- Double-check all languages I need to use this on, and add support for them.
- Add support for C++ (file classification + tree-sitter AST parsing, matching existing language support).
