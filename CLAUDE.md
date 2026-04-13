# Project Instructions

## Teach Pipeline

Use `/teach-and-push {path} {format}` to run the codebase-teacher pipeline
with automatic display, push, and GitHub linking. This is the preferred way
to run the teach tool.

If the `/agents/teach` subagent is invoked directly instead, always:

1. Display the **full** structured assessment report without summarizing or
   truncating.
2. Display the **full contents** of every generated file in
   `{path}/.teacher-output/`.
3. Offer to push the generated files to a temporary branch and provide GitHub
   links (follow the same push workflow described in
   `.claude/commands/teach-and-push.md` steps 4-5).
