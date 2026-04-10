# TODO

## Future CLI Providers

- [ ] Add Codex CLI provider (`codex`)
- [ ] Add Windsurf CLI provider
- [ ] Add Gemini CLI provider

## Claude Code Integration

- [ ] Create Claude Code subagent (`.claude/agents/teach.md`) for one-command pipeline invocation

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
