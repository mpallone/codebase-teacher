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

If either argument is missing, or `{format}` is not one of `markdown` or
`html`, print a usage error and stop. Use this exact format:

```
## Usage error: expected 2 args (path, format=markdown|html), got "$ARGUMENTS". Stopping.
```

## Notation

- `{formatted X}` — the millisecond value `X` rendered per the
  *Duration formatting* rules near the bottom of this file.
- `{placeholder}` — fill in with the actual value at runtime.

## Rules (do not skip)

These rules exist because a previous run of this workflow hallucinated
completions and fabricated evaluation numbers. Do not remove them.

**Rule 1 — Verify before declaring complete.** Applies to Preflight and
steps [1/5]–[3/5] and [5/5]. Each step below specifies the artifact it
must produce. If the command returns a non-zero exit code, or the
expected file is missing or empty, print a failure banner for that
step (e.g.,
`## [3/5] Generate failed — index.html not produced. Stopping.`) and
stop. Do not continue to later steps. Do not fabricate results.

**Rule 2 — Never invent the structured assessment.** Applies to step
[4/5] only. The assessment must come from your own direct reads of the
generated files and the source code. If you cannot produce a field
because the data is missing, write the field's value as `unknown` and
explain why — do not summarize, reconstruct, paraphrase, or guess.

## Re-runs

Stale `{path}/.teacher/` and `{path}/.teacher-output/` from a prior run
are fine to leave in place — `teach scan|analyze|generate` overwrites
them safely.

## Timing and banners

Every numbered step records start and end timestamps with `date +%s%3N`
and prints a progress banner before and after. The banners are
user-facing status updates — they do not replace the bash commands.
Always run the bash commands.

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

---

## Preflight — ensure target repo is populated

This step is bookkeeping and is intentionally omitted from the
"Execution Time" summary at the bottom of the skill; any time spent
here is still captured by the total wall-time row. (Rule 1 still
applies — failure here stops the pipeline.)

Print: `## Preflight: checking target repo ({path})...`

Test whether `{path}` exists and is non-empty:

```bash
[ -d {path} ] && [ -n "$(ls -A {path} 2>/dev/null)" ]
```

The target must be either populated already, or registered as a git
submodule under `.gitmodules`. **Do not fall back to an arbitrary
`git clone`** — the skill must not pull unknown URLs on the user's
behalf.

**If `{path}` is populated:** print
`## Preflight: target repo already populated.` and continue to [1/5].

**If `{path}` is missing or empty:** fixtures under `tests/repos/` are
managed as git submodules in this repo (see `.gitmodules`). Recover by
initializing the submodule:

```bash
git submodule update --init --recursive -- {path}
```

Re-check that `{path}` is now non-empty.

- If populated, print `## Preflight: target repo populated.` and
  continue.
- If still missing or empty (e.g., `{path}` is not a registered
  submodule), print
  `## Preflight failed — could not populate {path}. Stopping.` and
  stop.

## [1/5] Scan

Print: `## [1/5] Scanning repository ({path})...`

Record `SCAN_START_MS` (`date +%s%3N`), then run:

```bash
teach scan --auto {path}
```

Record `SCAN_END_MS` (`date +%s%3N`).

**Verify:** `{path}/.teacher/teacher.db` exists and is non-empty. If not,
print `## [1/5] Scan failed — teacher.db not produced. Stopping.` and
stop.

Print: `## [1/5] Scan complete ({formatted scan_duration}).`

## [2/5] Analyze

Print: `## [2/5] Analyzing codebase...`

Record `ANALYZE_START_MS` (`date +%s%3N`), then run:

```bash
teach analyze {path}
```

**Prefer the foreground.** Do not pipe to `tail` and do not set
`run_in_background=true`. The Bash tool will auto-background any run
exceeding ~10 min; treat that as *normal*, not as a failure, and fall
through to the polling protocol below.

**Polling protocol (when the Bash tool returns a task id):**

1. Poll with a **single Bash `until`-loop** — *not* the Monitor tool.
   Monitor is MCP-backed and can disappear mid-wait, and when it does
   the background child is reaped. Bash is in-process and survives
   MCP drops:
   ```bash
   until [ -s {path}/.teacher/teacher.db ] \
         || [ -f {task_output_dir}/{task_id}.exit ]; do
     sleep 10
   done
   ```
2. **Check artifact first, exit file second.** If the artifact exists
   and is non-empty, treat it as success. Only if the artifact is
   missing AND the `.exit` file has appeared do you declare early
   termination.
3. **On detected early termination, retry exactly once.** Print
   `## [2/5] Analyze: detected early termination, retrying once.`,
   re-run the same command, and poll again. A second failure stops
   the pipeline per Rule 1 (print the failure banner; do not retry
   further).
4. Record `ANALYZE_END_MS` only after the successful run's artifact
   lands (not at the first attempt's kill time).

Detaching the child via `setsid`/`nohup` is **not** reliable under the
Bash tool and is not used.

Record `ANALYZE_END_MS` (`date +%s%3N`).

**Verify:** the command returned a zero exit code. The database update
is internal (no separate file to check). If the command failed, print
`## [2/5] Analyze failed — <reason>. Stopping.` and stop.

Print: `## [2/5] Analysis complete ({formatted analyze_duration}).`

## [3/5] Generate

Print: `## [3/5] Generating {format} output...`

Record `GENERATE_START_MS` (`date +%s%3N`), then run:

```bash
teach generate --format {format} {path}
```

**Prefer the foreground.** Do not pipe to `tail` and do not set
`run_in_background=true`. The Bash tool will auto-background any run
exceeding ~10 min (generate on a mid-sized repo routinely takes 1–2
hours); treat that as *normal*, not as a failure, and fall through
to the polling protocol below. Note that `teach generate` has **no
checkpointing** — `generator/html.py` assembles all sections in memory
and writes the output file exactly once at the end, so a mid-run kill
yields no usable artifact and forces a full re-run.

**Polling protocol (when the Bash tool returns a task id):**

1. Poll with a **single Bash `until`-loop** — *not* the Monitor tool.
   Monitor is MCP-backed and can disappear mid-wait, and when it does
   the background child is reaped. Bash is in-process and survives
   MCP drops:
   ```bash
   # {artifact} is the format-specific file from the Verify section below
   until [ -s {artifact} ] \
         || [ -f {task_output_dir}/{task_id}.exit ]; do
     sleep 10
   done
   ```
2. **Check artifact first, exit file second.** If the artifact exists
   and is non-empty, treat it as success. Only if the artifact is
   missing AND the `.exit` file has appeared do you declare early
   termination. Use `-s` (non-empty), not `-e` — a zero-byte file
   must not be treated as success.
3. **On detected early termination, retry exactly once.** Print
   `## [3/5] Generate: detected early termination, retrying once.`,
   re-run `teach generate --format {format} {path}`, and poll again.
   A second failure stops the pipeline per Rule 1 (print the failure
   banner; do not retry further).
4. Record `GENERATE_END_MS` only after the successful run's artifact
   lands (not at the first attempt's kill time).

Detaching the child via `setsid`/`nohup` is **not** reliable under the
Bash tool and is not used.

Record `GENERATE_END_MS` (`date +%s%3N`).

**Verify** the format-specific artifact exists:

- `--format html` → `{path}/.teacher-output/index.html`
- `--format markdown` → `{path}/.teacher-output/docs/overview.md`

If the expected file is missing, print
`## [3/5] Generate failed — <expected file> not produced. Stopping.`
and stop.

Print: `## [3/5] Generation complete ({formatted generate_duration}).`

## [4/5] Evaluate

Print: `## [4/5] Evaluating generated output...`

Record `EVAL_START_MS` (`date +%s%3N`).

### 4a. Inputs (per format)

**When `{format}` is `markdown`,** read:

- `{path}/.teacher-output/docs/overview.md`
- `{path}/.teacher-output/docs/architecture.md`
- `{path}/.teacher-output/docs/api-reference.md`
- `{path}/.teacher-output/docs/infrastructure.md`
- `{path}/.teacher-output/diagrams/architecture.md`
- `{path}/.teacher-output/diagrams/data-flow.md`

**When `{format}` is `html`,** read the single generated file:

- `{path}/.teacher-output/index.html`

Then read the actual source code under `{path}` to build your own
understanding of the repo.

### 4b. Structural checks (per format)

**Markdown:**

- Each of the six files above starts with an `# H1` heading.
- Diagram files live under `diagrams/` and are referenced from
  `architecture.md`.
- Mermaid diagrams use ` ```mermaid ` fenced code blocks.
- No broken relative links between docs.

**HTML:**

- **Sidebar navigation** — `<nav class="sidebar">` exists with links
  to all sections.
- **Theme toggle** — a button or control for light/dark switching is
  present.
- **Mermaid support** — `mermaid.min.js` CDN script tag is present.
- **Mermaid rendering** — diagram content uses `<pre class="mermaid">`
  tags (not markdown fences).
- **Responsive viewport** — `<meta name="viewport" ...>` tag is
  present.
- **Self-contained** — all CSS is inline (no external stylesheet
  links other than mermaid CDN).
- **All sections present** — the page contains sections for: Start
  Here, Architecture Overview, API Reference, Infrastructure,
  Architecture Diagram, Data Flow Diagrams.

### 4c. Content quality checks (shared)

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
- Would a new developer find the architecture doc helpful for
  onboarding?
- Are the Mermaid diagrams clear and informative?
- Is the level of detail appropriate (not too shallow, not too
  verbose)?

### 4d. Emit assessment

Record `EVAL_END_MS` (`date +%s%3N`).

Print: `## [4/5] Evaluation complete ({formatted eval_duration}).`

Then print the structured assessment using **this exact template**,
replacing each `{placeholder}` with the actual value (or with
`unknown — <reason>` per Rule 2 if data is missing). When `{format}`
is `markdown`, **omit the `### HTML Structure` section entirely**
(do not print the header with "n/a"). When `{format}` is `html`,
include it.

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

The assessment block printed here also satisfies AGENTS.md
§Post-Teach Workflow step 1 ("Display the skill's full structured
assessment without summarizing") — do **not** re-print it in the
post-teach workflow.

## [5/5] Post-teach workflow

Print: `## [5/5] Running post-teach workflow...`

Record `WORKFLOW_START_MS` (`date +%s%3N`).

Follow the **Post-Teach Workflow** in `AGENTS.md` verbatim — it is the
single source of truth for staging, branch creation, commit, push, and
the GitHub link display. Internal banners for that workflow are
specified there.

The workflow branches on `{format}`:

- `markdown` → displays the local paths under
  `{path}/.teacher-output/` and stops. No staging, commit, branch, or
  push.
- `html` → publishes the single `index.html` to the `html-test-host`
  branch (which GitHub Pages serves).

Pick the correct branch of the workflow based on `{format}` and execute
it fully before recording `WORKFLOW_END_MS`.

Record `WORKFLOW_END_MS` (`date +%s%3N`).

Print: `## [5/5] Post-teach workflow complete ({formatted workflow_duration}).`

## Duration formatting

Compute durations in milliseconds, then format each as a human-readable
string using the largest applicable units (omit leading zero units, e.g.
`36m 46s 123ms`, not `0d 0h 36m 46s 123ms`):

- d  = ms ÷ 86400000
- h  = (ms mod 86400000) ÷ 3600000
- m  = (ms mod 3600000)  ÷ 60000
- s  = (ms mod 60000)    ÷ 1000
- remaining ms = ms mod 1000

## Execution time summary

At the very end, compute:

- `scan_duration     = SCAN_END_MS     - SCAN_START_MS`
- `analyze_duration  = ANALYZE_END_MS  - ANALYZE_START_MS`
- `generate_duration = GENERATE_END_MS - GENERATE_START_MS`
- `eval_duration     = EVAL_END_MS     - EVAL_START_MS`
- `workflow_duration = WORKFLOW_END_MS - WORKFLOW_START_MS`
- `total_duration    = WORKFLOW_END_MS - SKILL_START_MS`

Print:

```
## Pipeline complete.
```

Then display:

```
## Execution Time
- Scan: {formatted scan_duration}
- Analyze: {formatted analyze_duration}
- Generate: {formatted generate_duration}
- Evaluation: {formatted eval_duration}
- Post-teach workflow (stage, commit, push): {formatted workflow_duration}
- Total wall time: {formatted total_duration}
```
