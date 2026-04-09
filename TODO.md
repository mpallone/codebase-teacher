# TODO

- README documentation describing how to use the tool.
- README documentation describing how to set up the tool for the first time.
- Automated end-to-end LLM-judged test harness:
  - Need to test this stuff against a codebase.
  - Have a mock codebase as a test artifact. Mock codebase should be complex enough to exercise all features of codebase-teacher.
  - Test code should run the tool against that mock codebase and generate output artifacts.
  - An LLM should compare (1) the code to (2) the teaching artifacts and verify that everything looks good.
  - The LLM should build its own knowledge of the code and make sure key things are included.
  - The LLM should check teaching artifacts and sanity-check that the claims are true.
  - All of this should be fully automated.
  - Because it requires LLM usage, this might be something that only gets manually kicked off, but runs beginning-to-end without user input.
  - Ensure this feature is documented.
- Double-check all languages I need to use this on, and add support for them.
- Add support for C (file classification + tree-sitter AST parsing, matching existing language support).
- Add support for C++ (file classification + tree-sitter AST parsing, matching existing language support).
- Verify the `missing` list in `print_dependency_report` is always empty (walkthrough says it's reserved for future use but never populated). If confirmed, remove it and any related dead code.
- Verify `ProjectContext` is actually unused (walkthrough claims it's defined but never instantiated — CLI commands use `Settings()` directly). If confirmed, delete the class and any related dead code.
