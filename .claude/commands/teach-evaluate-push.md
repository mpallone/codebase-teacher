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

After the subagent completes, capture the end-of-subagent time:

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
