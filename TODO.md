# TODO

## Future CLI Providers

- [ ] Add Codex CLI provider (`codex`)
- [ ] Add Windsurf CLI provider
- [ ] Add Gemini CLI provider

## Claude Code Integration

- [x] Create Claude Code subagent (`.claude/agents/teach.md`) for one-command pipeline invocation

## Real Repo Testing

- [x] Add httpbin (`postmanlabs/httpbin`) as first test repo (git submodule in `tests/repos/`)
- [ ] Run tool against httpbin and evaluate output quality
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
