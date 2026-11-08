# Implementation plan — Python SDK and guided experience

> **Provenance.** Tasks marked `[x]` were implemented outside Kiro, before this spec was
> written; each one was checked against the current code and tests. Unchecked `[ ]` tasks are
> real, not-yet-done improvements intended to be executed in Kiro.

- [x] 1. `GhostReplay` facade: tools, models, agents, invariants, state/reset, record, replay,
  inject, diff, export/load, regression helpers (`tests: packages/ghostreplay/tests/test_sdk.py`)
  - _Requirements: 1, 2, 3_
- [x] 2. Core depends only on pydantic; `server` extra (`test_sdk_import_does_not_need_the_server_extra`)
  - _Requirements: 4.1_
- [x] 3. CLI `inspect`, `diff`, `replay --app`, `export`, `test --import`
  - _Requirements: 5.1_
- [x] 4. External example `examples/invoice-agent` and the CI `sdk` job
  - _Requirements: 4.2_
- [x] 5. Homepage, guided demos, mode switch, Connect page (`apps/dashboard/e2e/guided.spec.ts`)
  - _Requirements: 6_
- [x] 6. Trace download/import endpoints and page (`tests/test_public_isolation.py`)
  - _Requirements: 7.1_
- [x] 7. `docs/sdk/` with every runnable block executed by `tests/test_sdk_docs.py`

- [ ] 8. Publish to PyPI (trusted publishing from a tagged release)
  - Add a release workflow that builds with `uv build`, checks metadata with `twine check`, and
    publishes on a `v*` tag via PyPI trusted publishing. Update `docs/sdk/installation.md`.
  - _Requirements: 8_
  - Verify: a tag on a fork publishes to TestPyPI; `pip install ghostreplay` works in a clean venv.

- [ ] 9. Order-independent matching for concurrent calls in one run
  - Allow `asyncio.gather` of decorated tools inside an agent: match concurrent calls by
    (name, match key) within a "concurrency window" instead of strict order, and record the
    window in the trace. Keep strict order as the default.
  - _Requirements: 9_
  - Verify: a new test in `test_sdk.py` with two concurrent tools replays identically in either
    completion order; strict mode still diverges on reordering.

- [ ] 10. Adapter for a popular agent framework's tool interface
  - Provide `ghostreplay.adapters.<framework>` that wraps that framework's tool objects with
    `@ghost.tool` semantics, without importing the framework at module import time.
  - _Requirements: 10_
  - Verify: an example under `examples/` records and replays a two-tool agent; docs page added.

- [ ] 11. Guided demo: "copy this incident as a regression test" button
  - On step 6, show the generated pytest source for the fixed case (`POST /api/regression/export`)
    in a copyable code block, next to the existing link to the developer Regression view.
  - _Requirements: 6.2_
  - Verify: e2e asserts the code block contains `run_case(load_case(`.
