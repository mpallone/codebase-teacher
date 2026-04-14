Before doing anything, capture the overall start time by running:

```bash
date +%s%3N
```

Record this value as SKILL_START_MS.

Print the following status banner:

```
## Starting teach-evaluate-push pipeline
Target: {path}, Format: {format}
```

Then print:

```
## [1/3] Launching teach subagent...
```

Launch the `/agents/teach` subagent with arguments: $ARGUMENTS

## Async subagent handling (critical — do not skip)

These rules exist because a previous run of this skill hallucinated a
completed subagent response and fabricated evaluation numbers. Do not
remove these checks without also removing the progress banners they
protect.

**1. Wait for the subagent before continuing.** The `Agent` tool in this
harness returns asynchronously. A successful-launch response (containing
`agentId`, phrases like "working in the background," or "you will be
notified automatically when it completes") means the subagent has NOT
finished — only that it has started. Do NOT capture `SUBAGENT_END_MS`, do
NOT print the `[2/3]` banner, and do NOT produce any assessment until the
`<task-notification>` for that `agentId` arrives with
`<status>completed</status>` and a `result` payload. If no completion
notification arrives, stop and tell the user the subagent is still
running — do NOT fabricate output to fill the slot.

**2. Verify expected output files exist before declaring success.**
Before printing the `[2/3]` completion banner, confirm the subagent
produced the expected artifacts on disk:

- For `--format html`: `{path}/.teacher-output/index.html`
- For `--format markdown`: `{path}/.teacher-output/docs/overview.md`

If the expected file is missing, the subagent did NOT complete
successfully regardless of what its message says. Print a failure banner
(e.g., `## [2/3] Subagent reported completion but expected output file is
missing — stopping.`) and stop.

**3. Display the subagent's output verbatim.** The structured assessment
you display under the Post-Teach Workflow (AGENTS.md step 1) must come
from the `result` field of the task notification. Never summarize,
reconstruct, paraphrase, or invent any part of it. If the `result` is
missing or partial, say so and stop.

---

Once the completion notification has arrived and the expected output file
exists, capture the end-of-subagent time:

```bash
date +%s%3N
```

Record this as SUBAGENT_END_MS. Compute the subagent duration and print:

```
## [2/3] Teach subagent complete ({formatted subagent duration}). Starting post-teach workflow...
```

Then follow the "Post-Teach Workflow" in AGENTS.md.

After the Post-Teach Workflow completes, capture the final timestamp:

```bash
date +%s%3N
```

Record this as WORKFLOW_END_MS. Compute the post-teach duration and print:

```
## [3/3] Post-teach workflow complete ({formatted post-teach duration}).
```

Compute durations in milliseconds, then format
each as a human-readable string using the largest applicable units
(omit leading zero units, e.g. `36m 46s 123ms` not `0d 0h 36m 46s 123ms`):

- d = ms ÷ 86 400 000
- h = (ms mod 86 400 000) ÷ 3 600 000
- m = (ms mod 3 600 000) ÷ 60 000
- s = (ms mod 60 000) ÷ 1 000
- remaining ms = ms mod 1 000

Display the following timing summary at the very end of your output:

```
## Execution Time
- Subagent (teach pipeline + evaluation): {formatted duration}
- Post-teach workflow (stage, commit, push): {formatted duration}
- Total wall time: {formatted duration}
```
