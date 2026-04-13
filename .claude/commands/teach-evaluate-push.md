Before doing anything, capture the overall start time by running:

```bash
date +%s
```

Record this value as SKILL_START_EPOCH.

Launch the `/agents/teach` subagent with arguments: $ARGUMENTS

After the subagent completes, capture the end-of-subagent time:

```bash
date +%s
```

Record this as SUBAGENT_END_EPOCH. Then follow the "Post-Teach Workflow" in AGENTS.md.

After the Post-Teach Workflow completes, capture the final timestamp:

```bash
date +%s
```

Record this as WORKFLOW_END_EPOCH. Compute and display the following timing
summary at the very end of your output:

```
## Execution Time
- Subagent (teach pipeline + evaluation): {SUBAGENT_END_EPOCH - SKILL_START_EPOCH} seconds
- Post-teach workflow (stage, commit, push): {WORKFLOW_END_EPOCH - SUBAGENT_END_EPOCH} seconds
- Total wall time: {WORKFLOW_END_EPOCH - SKILL_START_EPOCH} seconds
```
