# Agent Instructions

## Verification Requirement

After implementing changes, **ask the user** whether to launch the repository's
evaluation subagent (`.claude/agents/teach.md`) before committing. This
subagent runs the full `teach scan → analyze → generate` pipeline against a
test repo and evaluates the output quality. It burns LLM tokens, so the user
decides when the cost is justified. If approved, the subagent should
independently:

1. Read the changed files and confirm the fix matches the task description.
2. Run the full test suite (`uv run pytest`) and report results.
3. Write and run a targeted repro script that exercises the fix end-to-end
   (e.g., simulate the failure scenario with stubs and confirm the new
   behavior).
4. Flag any edge cases, regressions, or concerns.

Address all findings from the verification subagent before committing.

## Testing

- Always run `uv run pytest` to verify all tests pass before committing.
- When adding new functionality, add tests that cover the happy path,
  failure/fallback paths, and any edge cases identified during development.
