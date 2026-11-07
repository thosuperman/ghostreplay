# Architecture

## The one-door principle

GhostReplay does not monkey-patch HTTP clients or SDKs. An agent reaches the outside world
only through `AgentRuntime`:

| Call | Recorded as | Replayed from |
|---|---|---|
| `rt.complete(ModelRequest)` | `model_call` (prompt + response) | recording, until divergence |
| `rt.call_tool(name, args)` | `tool_call` (args, result/error, optional state before/after) | recording (replay) or simulated backend (branch) |
| `rt.now()`, `rt.new_id()`, `rt.random()` | `nondeterminism` | recording |
| `rt.log(step, detail)` | `agent_step` (annotation, not replayed) | re-emitted by the agent |
| `rt.guard(decision, detail)` | `guard` (safety decision) | re-emitted by the agent |

Because every interaction passes through one place, replay is a property of the framework,
not of each tool. The flip side is explicit: **GhostReplay can only replay what goes through
the runtime.** Arbitrary third-party code that opens its own sockets is not replayable — and
in replay mode such access is blocked and reported (`OfflineViolation`).

## Session: one code path, four policies

`ghostreplay.replay.session.Session.interact(op, invoke)` handles every interaction.

```
             ┌──────────────── divergence check (if a reference exists and on-track) ───────┐
             │ next recorded interaction must have the same kind, name and match_key        │
             │ mismatch → `divergence` event; offline modes raise ReplayDivergenceError     │
             └──────────────────────────────────────────────────────────────────────────────┘
             ┌──────────────── fault plan (selector: kind, name, occurrence, where) ────────┐
             │ error | transform | execute_then_error | delay                               │
             └──────────────────────────────────────────────────────────────────────────────┘
             ┌──────────────── response source ─────────────────────────────────────────────┐
  record     │ invoke the implementation                                 source = live      │
  replay     │ recorded response / re-raise recorded error               source = recorded  │
  cf-replay  │ like replay, with faults; stops at first divergence       source = injected  │
  branch     │ tools re-executed on a fresh simulated env and verified;  source = simulated │
             │ model + nondeterminism from recording while on-track                         │
             └──────────────────────────────────────────────────────────────────────────────┘
```

`match_key = sha256(kind, name, canonical_json(redact(request)))`. Tools can restrict matching
to selected fields (`ToolSpec.match_fields`).

### Why branch mode exists

Some failures cannot be expressed by swapping a recorded response. *Timeout after commit*
requires the side effect to really happen (the refund exists) while the agent sees a timeout.
Branch mode builds a fresh, deterministic simulated environment, re-executes the tool calls
against it (verifying each result against the recording while on-track), and after the first
divergence runs the agent's model adapter live. Every event says where it came from, and the
execution is labelled `branch`. A counterfactual is never presented as a recording.

### Determinism

- `VirtualClock`: simulated services advance it to model latency; replay advances it by the
  recorded duration. Replayed timestamps and durations therefore equal the recording's.
- `DeterministicSources`: seeded ids and random numbers for scenario runs.
- Simulated backends are pure in-memory Python with deterministic ids.
- Test: `test_replay_is_structurally_identical_to_recording` compares kinds, names,
  requests, responses, errors, timestamps, durations and state for every event.

## Mutation catalog

| Fault | Strategy | Needs branch | What happens |
|---|---|---|---|
| `tool_timeout` | error | no | timeout, operation not performed |
| `timeout_after_commit` | execute_then_error | **yes** | operation performed, agent sees timeout |
| `http_429`, `http_500`, `auth_failure`, `permission_denied` | error | no | synthetic error |
| `missing_field`, `null_value`, `stale_data`, `incorrect_output`, `duplicate_response` | transform | no | baseline response edited by JSON path (`*` wildcard) |
| `delayed_operation` | delay | **yes** | latency added; past the tool timeout → timeout after commit |
| `partial_success` | execute_then_error | **yes** | operation performed, partial failure reported |

The original response is stored on the event (`fault.original_response`) so the UI can show
exactly what changed.

## Diff engine

`diff_executions(a, b)` aligns interaction signatures (`kind:name`, plus guard events) with
`difflib.SequenceMatcher`, then deep-diffs requests, responses and errors for aligned pairs.
It returns aligned rows, typed entries (`added_call`, `removed_call`, `changed_args`,
`changed_result`, `changed_error`, `changed_model_input`, `changed_model_output`,
`added_guard`, …), the first divergence, and a behavioural summary (status, outcome, per-tool
counts, committed destructive side effects, invariant outcomes, final-state changes).

## Regression

- `Invariant(id, title, description, check, severity, requires_state)` returns
  `passed | failed | inconclusive` with evidence event ids and an explanation.
- Invariants that need final state are `inconclusive` for offline counterfactuals (the state
  of a world that was never executed is unknown) — never silently passed.
- `RegressionCase` is pure data: scenario id, variant, conditions, faults, embedded reference
  execution, expectation. Scenarios are resolved by id from the registry / entry points.
- `write_case` emits `<id>.case.json` + `test_<id>.py`; `ghostreplay test` emits JUnit XML and
  JSON reports.

## Persistence

SQLite (`executions` table: indexed columns + summary JSON + full body JSON). One file per lab
under `.ghostreplay/`. Executions are validated with Pydantic on every load.

## Security model

See `.kiro/steering/security.md`. Enforced in code and covered by tests:
redaction before persistence (`test_redactor_*`, `test_recorder_persists_only_redacted_payloads`),
offline guard (`test_offline_guard_*`, `test_agent_network_access_during_replay_fails_loudly`),
handler stubs in replay (`test_replay_never_invokes_tool_handlers_or_model`), allowlisted tools
(`test_tool_registry_is_an_allowlist_with_validation`), path confinement
(`test_safe_join_rejects_traversal`), data-only trace import (`test_trace_export_import_roundtrip_validates`).
