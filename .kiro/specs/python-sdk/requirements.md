# Requirements — Python SDK and guided experience

## Introduction

`ghostreplay.GhostReplay` lets developers instrument their own Python agents. The guided demos
(`/demo/refund`, `/demo/devops`), the Connect page and trace import make the product
understandable and show how to adopt it.

Written after the implementation existed. Requirements 1–7 describe current behaviour.
Requirements 8–10 are planned improvements (see `tasks.md`).

## Requirements

### 1. Explicit instrumentation

**User story:** As an agent developer, I want to decorate my tools and model calls, so that
GhostReplay records exactly those interactions.

- 1.1 WHEN a `@ghost.tool` function is called inside `record` THEN it SHALL execute and be
  recorded as a `tool_call` event with arguments, result or error, and timing.
- 1.2 WHEN it is called inside `replay` THEN the recorded result or error SHALL be returned and
  the function SHALL NOT be called.
- 1.3 WHEN it is called outside a GhostReplay run THEN it SHALL behave like the plain function.
- 1.4 `@ghost.model` SHALL record model calls the same way; `async def` functions SHALL work.
- 1.5 The documentation SHALL state that undecorated calls are not recorded.

### 2. Replay, faults and diff

- 2.1 `replay` SHALL report `diverged` when the agent makes a call the recording does not contain
  or changes arguments, and SHALL NOT fall back to executing the tool.
- 2.2 `record(..., faults=)` and `inject(...)` SHALL support every catalog fault kind;
  `inject(..., agent=...)` SHALL re-execute another agent after the fault (branch).
- 2.3 `new_id()` and `now()` SHALL replay identically.

### 3. Regression tests

- 3.1 `regression_case` SHALL carry the run's task and faults; `check` SHALL report
  `outcome_matches_expectation`.
- 3.2 `write_regression_test(..., import_module=)` SHALL write a pytest module that imports the
  app module (validated as a dotted name) and passes or fails like `check`.

### 4. Packaging

- 4.1 The core package SHALL depend only on pydantic; FastAPI and uvicorn SHALL be an extra.
- 4.2 A wheel SHALL install into a fresh virtual environment and run the external example.

### 5. CLI

- 5.1 `inspect`, `diff`, `replay --app`, `export` and `test --import` SHALL work on trace and
  case files, with JSON output where useful and clear errors (no tracebacks) for bad input.

### 6. Guided experience

- 6.1 The homepage SHALL explain the product, its users and how to try it, and link to both
  guided demos and the Connect page.
- 6.2 Each guided demo SHALL drive real executions (record, strict replay, fixed-agent
  re-execution, diff, regression) and derive every number from them.
- 6.3 Developer mode SHALL remain available, and guided steps SHALL link to the matching view.

### 7. Trace import on the public server

- 7.1 Uploaded traces SHALL be schema-validated, re-redacted, capped (512 KiB, 5,000 events),
  stored only in the uploader's session and never executed.

### 8. PyPI distribution (planned)
### 9. Concurrent tool calls inside one run (planned)
### 10. Framework adapters (planned)
