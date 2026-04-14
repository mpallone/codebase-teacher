# Agent Instructions

## Verification Requirement

After implementing changes, **ask the user** whether to launch the repository's
`/teach-evaluate-push` skill (`.claude/commands/teach-evaluate-push.md`) before
committing. This skill runs the full `teach scan → analyze → generate` pipeline
against a test repo and evaluates the output quality. It burns LLM tokens, so
the user decides when the cost is justified. If approved, the skill should
independently:

1. Read the changed files and confirm the fix matches the task description.
2. Run the full test suite (`uv run pytest`) and report results.
3. Write and run a targeted repro script that exercises the fix end-to-end
   (e.g., simulate the failure scenario with stubs and confirm the new
   behavior).
4. Flag any edge cases, regressions, or concerns.

Address all findings from the verification skill before committing.

## Post-Teach Workflow

After the `/teach-evaluate-push` skill returns its assessment, always do the
following:

1. Display the skill's **full** structured assessment without summarizing.
2. For each generated file in `{path}/.teacher-output/`, display only its
   file name and size. The full content will be viewable via the GitHub
   links in step 5.
3. Copy the output into the codebase-teacher repo for committing:
   ```bash
   mkdir -p .teacher-staging/{basename}
   cp -r {path}/.teacher-output/* .teacher-staging/{basename}/
   ```
4. Create a temporary branch, force-add, commit, and push:
   ```bash
   git checkout -b teacher-output/{basename}/$(date +%Y%m%d-%H%M%S)
   git add -f .teacher-staging/
   git commit -m "teacher output for {basename}"
   git push -u origin HEAD
   ```
5. Display GitHub links to each pushed file:
   ```
   https://github.com/mpallone/codebase-teacher/blob/{branch}/.teacher-staging/{basename}/{file}
   ```
6. Switch back to the original branch.

In addition to carrying out the steps above, print a short progress banner to
stdout before each step so the user can see how far along the workflow is.
The banners are user-facing status updates — they do not replace the steps.
Always carry out the steps.

- Before step 1: print `## Displaying assessment...`
- Before step 3: print `## Copying output to .teacher-staging/...`
- Before step 4: print `## Creating branch, committing, and pushing...`
- After step 5: print `## Push complete.`

## Testing

- Always run `uv run pytest` to verify all tests pass before committing.
- When adding new functionality, add tests that cover the happy path,
  failure/fallback paths, and any edge cases identified during development.
