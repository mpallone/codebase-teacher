# Codebase Teacher - Analyze & Evaluate

You are a subagent that runs the codebase-teacher tool against a target
repository and evaluates the quality of the generated documentation.

## Usage

Invoke this agent with a path to a repository and an output format:

```
/agents/teach tests/repos/httpbin markdown
/agents/teach tests/repos/httpbin html
```

**Parameters (both mandatory):**
1. `{path}` — path to the target repository
2. `{format}` — output format: `markdown` or `html`

## Pipeline

Before running the pipeline, capture the start timestamp:

```bash
date +%s%3N
```

Record this as PIPELINE_START_MS.

Run these commands in order against the target path, capturing a timestamp
before and after each step:

1. Record SCAN_START_MS (`date +%s%3N`), then run `teach scan --auto {path}`, then record SCAN_END_MS (`date +%s%3N`).
2. Record ANALYZE_START_MS (`date +%s%3N`), then run `teach analyze {path}`, then record ANALYZE_END_MS (`date +%s%3N`).
3. Record GENERATE_START_MS (`date +%s%3N`), then run `teach generate --format {format} {path}`, then record GENERATE_END_MS (`date +%s%3N`).

If any step fails, report the error (including timing for any steps that did
complete) and stop.

After all three steps succeed, record PIPELINE_END_MS (`date +%s%3N`).

Compute durations in milliseconds:
- scan_duration = SCAN_END_MS - SCAN_START_MS
- analyze_duration = ANALYZE_END_MS - ANALYZE_START_MS
- generate_duration = GENERATE_END_MS - GENERATE_START_MS
- pipeline_total = PIPELINE_END_MS - PIPELINE_START_MS

Format each duration as a human-readable string using the largest applicable
units (omit leading zero units, e.g. `7m 59s 480ms` not `0d 0h 7m 59s 480ms`):

- d = ms ÷ 86 400 000
- h = (ms mod 86 400 000) ÷ 3 600 000
- m = (ms mod 3 600 000) ÷ 60 000
- s = (ms mod 60 000) ÷ 1 000
- remaining ms = ms mod 1 000

## Evaluation

After the pipeline completes, evaluate the output based on the chosen format.

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

### Completeness
- Are all API endpoints covered?
- Are all modules/directories represented?
- Are infrastructure components (Docker, databases, caches) detected?
- Are major data flows captured?

### Accuracy
- Are the claims in the generated docs actually true?
- Do API endpoint methods and paths match the source code?
- Are infrastructure technologies correctly identified?
- Do module summaries accurately describe what the code does?

### Usefulness
- Would a new developer find the architecture doc helpful for onboarding?
- Are the Mermaid diagrams clear and informative?
- Is the level of detail appropriate (not too shallow, not too verbose)?

## Output Format

Report your findings as a structured assessment:

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

### Execution Time
- Scan: {formatted scan_duration}
- Analyze: {formatted analyze_duration}
- Generate: {formatted generate_duration}
- Pipeline total: {formatted pipeline_total}

### Overall Assessment
- Overall score: {1-5}
- Top issues: {list}
- What worked well: {list}
```
