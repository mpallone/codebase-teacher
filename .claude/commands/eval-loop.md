You are running the codebase-teacher evaluation loop. Your job is to:

1. Run the eval harness to generate documentation for test repos
2. Judge the quality of the generated documentation
3. Fix any issues found in codebase-teacher's source code
4. Re-run and repeat until satisfied

## Step 1: Run the eval harness

Run the prep command to clone test repos, run `teach analyze` + `teach generate` against each, and build review packets:

```bash
cd /home/user/codebase-teacher && python -m eval prep --repos all
```

This will create review packets under `eval/.cache/runs/latest/<slug>/packet.md`.

If a repo fails during analysis, note the error and continue with the others. You can debug failures after judging the successful repos.

## Step 2: Judge each repo

For each repo that completed successfully, read its review packet:

```
eval/.cache/runs/latest/<slug>/packet.md
```

Each packet contains:
- The judging rubric (scoring dimensions and verdict format)
- The repo's README and complete source code (ground truth — every source file, no sampling)
- The generated documentation and diagrams (what you are judging)

**For each repo**, carefully compare the generated docs against the source code and produce a verdict following the rubric format. Focus on:
- Are the architecture claims factually correct?
- Are APIs/routes correctly identified?
- Are infrastructure components (databases, caches, external services) correctly detected?
- Are the Mermaid diagrams valid and useful?
- Is anything important missing?
- Are there any hallucinations (claims not supported by the code)?

Write your verdict summary for each repo in chat.

## Step 3: Fix issues

If any repo has a verdict of "needs_work" or "fail", or has any high-severity findings:

1. Identify the **root cause patterns** in `src/codebase_teacher/` — don't just fix symptoms in the output; fix the code that generated it.
2. Read the relevant source files in `src/codebase_teacher/` (analyzers, generators, prompts, parsers).
3. Apply targeted fixes. Common areas to look at:
   - `src/codebase_teacher/llm/prompt_registry.py` — prompt templates for summarization, API detection, etc.
   - `src/codebase_teacher/analyzer/code_parser.py` — AST parsing logic
   - `src/codebase_teacher/analyzer/api_detector.py` — API endpoint detection
   - `src/codebase_teacher/analyzer/infra_detector.py` — infrastructure detection
   - `src/codebase_teacher/analyzer/flow_tracer.py` — data flow tracing
   - `src/codebase_teacher/generator/docs.py` — documentation generation
   - `src/codebase_teacher/generator/diagrams.py` — diagram generation
   - Language-specific parsers: `java_parser.py`, `scala_parser.py`, `c_parser.py`, `terraform_parser.py`
4. Run `pytest` to make sure nothing is broken.
5. Commit your fixes with a descriptive message.

## Step 4: Re-run

After committing fixes, delete the teach cache for each repo so they get re-analyzed with the new code:

```bash
for slug in flask javalin cask terraform-aws-vpc; do
    rm -rf eval/.cache/repos/$slug/.teacher eval/.cache/repos/$slug/.teacher-output
done
```

Then re-run:

```bash
python -m eval prep --repos all
```

Go back to Step 2 and judge again.

## Step 5: Repeat

Continue the loop (Steps 2-4) until:
- All repos have a verdict of "pass", OR
- You've completed 3 iterations, OR
- Remaining issues are not fixable without major architectural changes (document these for the user)

## Step 6: Final summary

When done, write a final summary including:
- Per-repo verdict (pass/needs_work/fail) and scores
- What was fixed across iterations
- What still needs attention (if anything)
- Recommendations for future improvements
