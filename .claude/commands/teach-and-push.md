# Teach, Evaluate, Push & Link

Run the codebase-teacher pipeline against a target repo, display the full
results, push the generated files to a temporary branch, and provide GitHub
links.

## Usage

```
/teach-and-push {path} {format}
```

**Parameters (both mandatory, provided via `$ARGUMENTS`):**
1. `{path}` — path to the target repository
2. `{format}` — output format: `markdown` or `html`

## Step 1 — Run the Pipeline

Run these commands in order:

1. `teach scan --auto {path}`
2. `teach analyze {path}`
3. `teach generate --format {format} {path}`

If any step fails, report the error and stop.

## Step 2 — Display Generated Files (in full)

Read and display the **complete contents** of every generated file. Do NOT
summarize or truncate — show the full text.

### When format is `markdown`

Read and display all of these:

- `{path}/.teacher-output/docs/overview.md`
- `{path}/.teacher-output/docs/architecture.md`
- `{path}/.teacher-output/docs/api-reference.md`
- `{path}/.teacher-output/docs/infrastructure.md`
- `{path}/.teacher-output/diagrams/architecture.md`
- `{path}/.teacher-output/diagrams/data-flow.md`

### When format is `html`

Read and display:

- `{path}/.teacher-output/index.html`

Also verify these HTML-specific requirements:

- **Sidebar navigation** — `<nav class="sidebar">` exists with links to all sections
- **Theme toggle** — a button or control for light/dark switching is present
- **Mermaid support** — `mermaid.min.js` CDN script tag is present
- **Mermaid rendering** — diagram content uses `<pre class="mermaid">` tags (not markdown fences)
- **Responsive viewport** — `<meta name="viewport" ...>` tag is present
- **Self-contained** — all CSS is inline (no external stylesheet links other than mermaid CDN)
- **All sections present** — the page contains sections for: Start Here, Architecture Overview, API Reference, Infrastructure, Architecture Diagram, Data Flow Diagrams

## Step 3 — Evaluate Quality

Read the actual source code of the target repo to build your own understanding,
then evaluate each generated output on these criteria:

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

Display a structured assessment:

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

## Step 4 — Push to Temporary Branch

1. Determine the basename of `{path}` (e.g., `httpbin` from `tests/repos/httpbin`).
2. Record the current branch name so you can return to it later.
3. Create a staging directory in the codebase-teacher repo root:
   ```bash
   mkdir -p .teacher-staging/{basename}
   cp -r {path}/.teacher-output/* .teacher-staging/{basename}/
   ```
4. Create and switch to a temporary branch:
   ```bash
   git checkout -b teacher-output/{basename}/$(date +%Y%m%d-%H%M%S)
   ```
5. Force-add the staging files (they are gitignored) and commit:
   ```bash
   git add -f .teacher-staging/
   git commit -m "teacher output for {basename}"
   ```
6. Push the branch:
   ```bash
   git push -u origin {branch-name}
   ```
7. Switch back to the original branch:
   ```bash
   git checkout {original-branch}
   ```

## Step 5 — Display GitHub Links

Construct and display clickable links to every generated file on GitHub:

```
https://github.com/mpallone/codebase-teacher/blob/{branch-name}/.teacher-staging/{basename}/{relative-file-path}
```

List every file with its link. For markdown format this is 6 links; for html
format this is 1 link.
