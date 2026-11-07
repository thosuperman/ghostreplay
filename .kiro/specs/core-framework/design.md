# Design — GhostReplay core framework

## Overview

```
 agent code ──► AgentRuntime ──► Session.interact(op, invoke) ──► Recorder ──► Execution/Store
                 complete()          │  policy by mode:
                 call_tool()         │   record : invoke live            (source=live)
                 now()/new_id()      │   replay : serve recording         (source=recorded)
                 random()            │   branch : tools re-executed on    (source=simulated)
                                     │            fresh simulated env,
                                     │            model from recording
                                     │            until divergence
                                     └─ FaultPlan applied first           (source=injected)
```

### Single interaction path
Every interaction is an `Operation(kind, name, request, destructive, timeout_ms, observe)`.
`Session.interact` computes `match_key = sha256(kind, name, canonical_json(redact(request)))`.

Per call, in order:
1. **Divergence check** (only while on-track and a reference exists): compare with
   `reference.interactions[cursor]`. Mismatch → `divergence` event; `on_track = False`.
   In `replay` / `counterfactual-replay` → raise `ReplayDivergenceError` (status `diverged`).
2. **Fault** — `FaultPlan.match(op, occurrence)`; strategies:
   - `error` → synthesize `ToolError`; operation not executed.
   - `transform` → baseline (recorded if replaying on-track, else invoke) then edit by JSON path.
   - `execute_then_error` → invoke (commit), then raise error. `requires_branch`.
   - `delay` → advance virtual clock; exceeds `timeout_ms` → timeout after commit.
3. **Response** — record: invoke; replay on-track: recorded; branch: tools invoke + verify
   against recording (mismatch → divergence `result_mismatch`), model recorded while on-track
   else invoke, nondeterminism recorded while on-track else seeded deterministic source.

### Clocks and nondeterminism
`VirtualClock` drives timestamps and durations in scenario runs. Simulated services advance it
to model latency. Replay advances it by the recorded duration, so replay timestamps equal the
recording's. `now()`, `new_id()` and `random()` are interactions themselves.

### Data model (schema v1)
- `Event`: execution_id, event_id, parent_event_id, seq, kind, name, timestamp, duration_ms,
  agent, source, model, request, response, error(`ErrorInfo`), state_before, state_after,
  match_key, destructive, fault(`AppliedFault`), replay(`ReplayAnnotation`), metadata.
- `Execution`: id, app, scenario, variant, mode, status, provenance, task, output,
  reference_execution_id, faults, conditions, events, final_state, invariants, divergence.
- `FaultSpec`: id, kind, target(`FaultTarget`: kind, name, occurrence, where), params.
- `RegressionCase`, `RegressionReport`, `InvariantResult`, `TraceDiff`.

### Interfaces
```python
class Scenario(ABC):
    id, title, app, description, variants, conditions, fault_presets, invariants
    def build_environment(self, conditions, clock) -> Environment   # tools + snapshot()
    def build_model(self) -> ModelAdapter
    def build_agent(self, variant) -> Agent                          # run(rt, task) -> AgentResult
    def default_task(self) -> dict

class Lab:
    record(scenario_id, variant, conditions=None, faults=None) -> Execution
    replay(execution_id, on_event=None, step_delay_s=0) -> Execution
    counterfactual(execution_id, faults, variant=None, mode="auto") -> Execution
    diff(a_id, b_id) -> TraceDiff
    run_case(case) -> RegressionReport
```

### Diff algorithm
1. Interactions → signatures `kind:name`; `difflib.SequenceMatcher` aligns them.
2. `equal` pairs: deep-diff request/response/error → changed_* entries.
3. `replace` blocks: pair positionally where signatures match, rest added/removed.
4. First divergence = first aligned row that is not identical.
5. Behavioural summary: per-tool counts, destructive calls, status, output, invariants.

### Error handling
`GhostReplayError` → `ReplayDivergenceError`, `MissingRecordingError`, `OfflineViolation`,
`UnknownToolError`, `ToolError` (+ `ToolTimeout`, `HttpError`, `AuthError`,
`PermissionDenied`, `PartialFailure`, `ToolValidationError`). Recorded errors are rebuilt via an
allowlist map; unknown types become `ToolError`.

### Security
Offline guard patches socket connect/getaddrinfo with a thread-local flag; tool handlers are
replaced by a raising stub in replay; redaction before persistence; registry-based scenario
resolution; path confinement for files.

## Testing strategy
Unit tests per module plus guarantee tests: deterministic replay equality, handler never
invoked during replay, socket blocked, divergence reported, missing recording, fault semantics,
redaction, diff correctness, path traversal rejection, regression report generation.
