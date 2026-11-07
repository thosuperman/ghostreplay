---
inclusion: fileMatch
fileMatchPattern: ["packages/ghostreplay/**/*.py", "apps/support-agent/**/*.py", "apps/devops-agent/**/*.py"]
---

# Engine architecture (loaded when editing framework or lab Python code)

Full write-up: #[[file:docs/architecture.md]]

## Session.interact — the single policy point
`ghostreplay/replay/session.py`. For each `Operation` (kind, name, request, destructive,
timeout_ms, observe, match_request):

1. **Divergence check** (when a reference recording exists and the run is on-track): the next
   recorded interaction must have the same kind, name and `match_key`
   (`stable_hash(kind, name, redact(match_request))`; `ToolSpec.match_fields` narrows the
   request). Problems become a `Divergence` of type `mismatch`, `unexpected_call`,
   `incomplete` (from `finish()`) or `result_mismatch` (branch verification). Offline modes
   raise `ReplayDivergenceError` / `MissingRecordingError`; branch mode continues live.
2. **Fault plan**: `FaultPlan.match(kind, name, request, occurrence)`; `apply_fault` uses the
   catalog strategy `error | transform | execute_then_error | delay`.
3. **Response source**: record → invoke (`live`); replay / counterfactual-replay → recorded
   response or re-raised recorded error (`recorded`); fault → `injected` (original response
   kept on `event.fault`); branch → tools re-executed and verified against the recording,
   model + nondeterminism served from the recording while on-track, everything `simulated`
   after divergence.
4. Exactly one event is emitted through the `Recorder` (redaction happens there).

Never add a second path that bypasses `interact`; never consume recorded responses out of
order; never swallow `GhostReplayError` in agent or harness code.

## Lab orchestration (`lab/lab.py`)
- `record` / `replay` / `counterfactual(mode="auto"|"replay"|"branch")` / `diff` /
  `run_case` / `case_from_execution` / `export_case` / `prepare_demo`.
- `auto` picks `branch` when a fault `requires_branch` or a different variant is tested.
- Offline modes get no model adapter and an `offline_copy()` of the tool registry, inside
  `offline_guard()`.
- Model choice: runs derived from a recording keep its kind of model. A live recording can only
  be branched when live mode is configured; a scripted one never switches to a paid API.
- Invariants are evaluated after every execution; `requires_state` invariants are
  `inconclusive` when final state is unobservable (offline counterfactual).
- `prepare_demo` builds six `DemoStep`s with `expected` verdicts; `DemoStory.ok` is false when
  any step misses its expectation and the CLI `demo` command then exits 1.

## Persistence and loading
- `SqliteStore`: indexed columns + summary JSON + body JSON; WAL + `synchronous=NORMAL` for
  file stores; optional `max_executions` retention per app; `ping()` for health checks.
- All untrusted bytes go through `storage.parsing.parse_document`, which raises
  `TraceFormatError` with a short message (bad JSON, non-object, schema errors).
  `Execution` itself rejects out-of-order `seq`, duplicate `event_id` and foreign
  `schema_version`.

## Extending
- New fault kind: catalog entry in `mutation/catalog.py`, behaviour in `mutation/faults.py`,
  test in `packages/ghostreplay/tests/test_mutation.py`, default params in
  `apps/dashboard/src/views/FailureLab.tsx` (`DEFAULT_PARAMS`).
- New invariant: a factory returning `Invariant` in the app's `invariants.py`, added to
  `all_invariants()`, with a test in the app's tests and evidence event ids in the `Check`.
- Schema change: edit `models/`, then mirror `apps/dashboard/src/api/types.ts` (the
  schema-sync hook asks for this).
