Run the codebase-teacher pipeline end-to-end against a target repository,
evaluate the generated documentation, and ship the output to GitHub.

## Arguments

`$ARGUMENTS` contains two mandatory positional values:

1. `{path}` — path to the target repository.
2. `{format}` — output format: `markdown` or `html`.

Example invocations:

```
/teach-evaluate-push tests/repos/httpbin markdown
/teach-evaluate-push tests/repos/httpbin html
```

If either argument is missing or `{format}` is not one of `markdown` or
`html`, print a usage error and stop.

## Timing and banners

Every step below records start and end timestamps with `date +%s%3N` and
prints a progress banner before and after. The banners are user-facing
status updates — they do not replace the bash commands. Always run the bash
commands.

Before doing anything, capture the overall start time:

```bash
date +%s%3N
```

Record this value as `SKILL_START_MS`.

Print the starting banner:

```
## Starting teach-evaluate-push pipeline
Target: {path}, Format: {format}
```

## Anti-hallucination rules (do not skip)

These rules exist because a previous run of this workflow hallucinated
completions and fabricated evaluation numbers. Do not remove them.

1. **Verify expected output files exist before declaring any step
   complete.** Each step below specifies the artifact it must produce. If
   the command returns a non-zero exit code, or the expected file is
   missing or empty, print a failure banner for that step (e.g.,
   `## [3/5] Generate failed — index.html not produced. Stopping.`) and
   stop. Do not continue to later steps. Do not fabricate results.

2. **Never summarize, reconstruct, paraphrase, or invent the structured
   assessment.** The assessment in step [4/5] must come from your own
   direct reads of the generated files and the source code. If you cannot
   produce a field because the data is missing, write the field's value as
   `unknown` and explain why — do not guess.

---

## [0/5] Ensure target repo is populated

Print: `## [0/5] Checking target repo ({path})...`

Test whether `{path}` exists and is non-empty:

```bash
[ -d {path} ] && [ -n "$(ls -A {path} 2>/dev/null)" ]
```

**If `{path}` is missing or empty:**

Fixtures under `tests/repos/` are managed as git submodules in this
repo (see `.gitmodules`). Recover by initializing the submodule rather
than guessing an upstream URL.

Print: `## [0/5] Target is empty — attempting submodule init...`

Then run:

```bash
git submodule update --init --recursive -- {path}
```

Re-check that `{path}` is now non-empty. If it is still missing or
empty (for example, `{path}` is not a registered submodule), print
`## [0/5] Failed to populate {path}. Stopping.` and stop. Do **not**
fall back to an arbitrary `git clone` — the skill must not pull
unknown URLs on the user's behalf.

Print: `## [0/5] Target repo populated.`

**If `{path}` was already populated:**

Print: `## [0/5] Target repo already populated.`

This step is bookkeeping and is intentionally omitted from the
"Execution Time" summary at the bottom of the skill; any time spent
here is still captured by the total wall-time row.

## [1/5] Scan

Print: `## [1/5] Scanning repository ({path})...`

Record `SCAN_START_MS` (`date +%s%3N`), then run:

```bash
teach scan --auto {path}
```

Record `SCAN_END_MS` (`date +%s%3N`).

**Verify:** `{path}/.teacher/teacher.db` exists and is non-empty. If not,
print `## [1/5] Scan failed — teacher.db not produced. Stopping.` and stop.

Print: `## [1/5] Scan complete ({formatted scan_duration}).`

## [2/5] Analyze

Print: `## [2/5] Analyzing codebase...`

Record `ANALYZE_START_MS` (`date +%s%3N`), then run:

```bash
teach analyze {path}
```

Record `ANALYZE_END_MS` (`date +%s%3N`).

**Verify:** the command returned a zero exit code. The database update is
internal (no separate file to check). If the command failed, print
`## [2/5] Analyze failed — <reason>. Stopping.` and stop.

Print: `## [2/5] Analysis complete ({formatted analyze_duration}).`

## [3/5] Generate

Print: `## [3/5] Generating {format} output...`

Record `GENERATE_START_MS` (`date +%s%3N`), then run:

```bash
teach generate --format {format} {path}
```

Record `GENERATE_END_MS` (`date +%s%3N`).

**Verify** the format-specific artifact exists:

- `--format html` → `{path}/.teacher-output/index.html`
- `--format markdown` → `{path}/.teacher-output/docs/overview.md`

If the expected file is missing, print
`## [3/5] Generate failed — <expected file> not produced. Stopping.` and
stop.

Print: `## [3/5] Generation complete ({formatted generate_duration}).`

## [4/5] Evaluate

Print: `## [4/5] Evaluating generated output...`

Record `EVAL_START_MS` (`date +%s%3N`).

### When format is `markdown`

Read the generated outputs:

- `{path}/.teacher-output/docs/overview.md`
- `{path}/.teacher-output/docs/architecture.md`
- `{path}/.teacher-output/docs/api-reference.md`
- `{path}/.teacher-output/docs/infrastructure.md`
- `{path}/.teacher-output/diagrams/architecture.md`
- `{path}/.teacher-output/diagrams/data-flow.md`

### When format is `html`

Read the single generated file:

- `{path}/.teacher-output/index.html`

In addition to the content quality checks below, verify these HTML-specific
requirements:

- **Sidebar navigation** — `<nav class="sidebar">` exists with links to all sections
- **Theme toggle** — a button or control for light/dark switching is present
- **Mermaid support** — `mermaid.min.js` CDN script tag is present
- **Mermaid rendering** — diagram content uses `<pre class="mermaid">` tags (not markdown fences)
- **Responsive viewport** — `<meta name="viewport" ...>` tag is present
- **Self-contained** — all CSS is inline (no external stylesheet links other than mermaid CDN)
- **All sections present** — the page contains sections for: Start Here, Architecture Overview, API Reference, Infrastructure, Architecture Diagram, Data Flow Diagrams

Then read the actual source code to build your own understanding of the repo.

Evaluate each output on these criteria:

#### Completeness
- Are all API endpoints covered?
- Are all modules/directories represented?
- Are infrastructure components (Docker, databases, caches) detected?
- Are major data flows captured?

#### Accuracy
- Are the claims in the generated docs actually true?
- Do API endpoint methods and paths match the source code?
- Are infrastructure technologies correctly identified?
- Do module summaries accurately describe what the code does?

#### Usefulness
- Would a new developer find the architecture doc helpful for onboarding?
- Are the Mermaid diagrams clear and informative?
- Is the level of detail appropriate (not too shallow, not too verbose)?

Record `EVAL_END_MS` (`date +%s%3N`).

Print: `## [4/5] Evaluation complete ({formatted eval_duration}).`

Then report the findings as a structured assessment, verbatim in this shape:

```
## Pipeline Results
- Scan: [pass/fail] — {details}
- Analyze: [pass/fail] — {details}
- Generate (format: {format}): [pass/fail] — {details}

## Evaluation

### API Detection
- Expected endpoints: {count}
- Found endpoints: {count}
- Missing: {list}
- False positives: {list}
- Score: {1-5}

### Infrastructure Detection
- Expected: {list}
- Found: {list}
- Missing: {list}
- Score: {1-5}

### Architecture Documentation
- Completeness: {1-5}
- Accuracy: {1-5}
- Usefulness: {1-5}
- Notes: {specific observations}

### Diagrams
- Renders correctly: {yes/no}
- Informative: {1-5}
- Notes: {specific observations}

### HTML Structure (html format only)
- Sidebar nav: {present/missing}
- Theme toggle: {present/missing}
- Mermaid CDN script: {present/missing}
- Mermaid <pre> tags: {present/missing}
- Viewport meta: {present/missing}
- Self-contained CSS: {yes/no}
- All sections present: {yes/no — list any missing}

### Overall Assessment
- Overall score: {1-5}
- Top issues: {list}
- What worked well: {list}
```

## [5/5] Post-teach workflow

Print: `## [5/5] Running post-teach workflow...`

Record `WORKFLOW_START_MS` (`date +%s%3N`).

Follow the "Post-Teach Workflow" in `AGENTS.md` (copy the output into
`.teacher-staging/`, create a branch, commit, push, and display GitHub
links).

Record `WORKFLOW_END_MS` (`date +%s%3N`).

Print: `## [5/5] Post-teach workflow complete ({formatted workflow_duration}).`

## Duration formatting

Compute durations in milliseconds, then format each as a human-readable
string using the largest applicable units (omit leading zero units, e.g.
`36m 46s 123ms` not `0d 0h 36m 46s 123ms`):

- d = ms ÷ 86 400 000
- h = (ms mod 86 400 000) ÷ 3 600 000
- m = (ms mod 3 600 000) ÷ 60 000
- s = (ms mod 60 000) ÷ 1 000
- remaining ms = ms mod 1 000

## Execution time summary

At the very end, compute:

- `scan_duration = SCAN_END_MS - SCAN_START_MS`
- `analyze_duration = ANALYZE_END_MS - ANALYZE_START_MS`
- `generate_duration = GENERATE_END_MS - GENERATE_START_MS`
- `eval_duration = EVAL_END_MS - EVAL_START_MS`
- `workflow_duration = WORKFLOW_END_MS - WORKFLOW_START_MS`
- `total_duration = WORKFLOW_END_MS - SKILL_START_MS`

Display:

```
## Execution Time
- Scan: {formatted scan_duration}
- Analyze: {formatted analyze_duration}
- Generate: {formatted generate_duration}
- Evaluation: {formatted eval_duration}
- Post-teach workflow (stage, commit, push): {formatted workflow_duration}
- Total wall time: {formatted total_duration}
```
