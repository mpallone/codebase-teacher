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

After the `/teach-evaluate-push` skill returns its assessment, always do
the following. The push step branches on `{format}`: markdown runs
create an archival branch; html runs publish to the `html-test-host`
branch that GitHub Pages serves.

1. Display the skill's **full** structured assessment without summarizing.
2. For each generated file in `{path}/.teacher-output/`, display only its
   file name and size. The full content will be viewable via the GitHub
   link(s) shown after pushing.

### If `{format}` is `markdown` — archive to a teacher-output branch

3m. Copy the output into the codebase-teacher repo for committing:
   ```bash
   mkdir -p .teacher-staging/{basename}
   cp -r {path}/.teacher-output/* .teacher-staging/{basename}/
   ```
4m. Create a temporary branch, force-add, commit, and push:
   ```bash
   git checkout -b teacher-output/{basename}/$(date +%Y%m%d-%H%M%S)
   git add -f .teacher-staging/
   git commit -m "teacher output for {basename}"
   git push -u origin HEAD
   ```
5m. Display GitHub links to each pushed file:
   ```
   https://github.com/mpallone/codebase-teacher/blob/{branch}/.teacher-staging/{basename}/{file}
   ```
6m. Switch back to the original branch.

### If `{format}` is `html` — publish to the `html-test-host` branch

The `html-test-host` branch is served by GitHub Pages. Only the tip
tree is served; only `index.html` at the branch root is hosted. Each
run overwrites the previous report.

Do **not** create a teacher-output/* archival branch for html runs.

Use a git worktree so the push happens without disturbing the
current branch. The worktree path `.teacher-staging/html-test-host`
is gitignored, so it won't leak into your working branch. Run these
commands from the repo root (not from inside the worktree) so commit
signing can resolve the source repo:

3h. Fetch and check out the target branch into a temporary worktree:
   ```bash
   git fetch origin html-test-host
   rm -rf .teacher-staging/html-test-host
   git worktree add .teacher-staging/html-test-host html-test-host
   ```
4h. Copy the generated page in, staying in the repo root and
    targeting the worktree via `git -C`:
   ```bash
   cp {path}/.teacher-output/index.html .teacher-staging/html-test-host/index.html
   git -C .teacher-staging/html-test-host add index.html
   git -C .teacher-staging/html-test-host commit -m "Publish HTML report for {basename} ($(date -u +%Y-%m-%dT%H:%M:%SZ))"
   git -C .teacher-staging/html-test-host push origin html-test-host
   ```
5h. Display the hosted URL and the GitHub blob link:
   ```
   Hosted: https://mpallone.github.io/codebase-teacher/
   Source: https://github.com/mpallone/codebase-teacher/blob/html-test-host/index.html
   ```
   If the user has not yet enabled GitHub Pages on the repo, note that
   the hosted URL will 404 until Pages is configured to serve from
   branch `html-test-host` at path `/ (root)`.
6h. Remove the temporary worktree:
   ```bash
   git worktree remove .teacher-staging/html-test-host
   ```

### Banners

In addition to carrying out the steps above, print a short progress banner to
stdout before each step so the user can see how far along the workflow is.
The banners are user-facing status updates — they do not replace the steps.
Always carry out the steps.

Shared:

- Before step 1: print `## Displaying assessment...`
- After step 5m or 5h: print `## Push complete.`

Markdown path:

- Before step 3m: print `## Copying output to .teacher-staging/...`
- Before step 4m: print `## Creating archival branch, committing, and pushing...`

HTML path:

- Before step 3h: print `## Checking out html-test-host worktree...`
- Before step 4h: print `## Publishing HTML to html-test-host...`

## Testing

- Always run `uv run pytest` to verify all tests pass before committing.
- When adding new functionality, add tests that cover the happy path,
  failure/fallback paths, and any edge cases identified during development.
