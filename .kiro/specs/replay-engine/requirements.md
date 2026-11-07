# Requirements — Replay engine

## Introduction

The replay engine is the part of `packages/ghostreplay` that records the observable execution
of a tool-using agent, persists it safely, replays it deterministically offline, detects and
reports divergence, compares executions structurally and serves all of that over HTTP. It
covers `models/`, `core/`, `recorder/`, `runtime.py`, `replay/`, `mocking/`, `llm/`, `diff/`,
`storage/`, `server/` and the `Lab.record` / `Lab.replay` paths of `lab/lab.py`.

Fault injection, counterfactual execution and regression proof are specified separately in
`.kiro/specs/failure-injection/`.

This document was written after the implementation existed; requirements 1–8 describe current
behaviour, requirements 9–10 describe planned improvements (see `tasks.md`).

## Requirement 1 — Execution recording

**User story:** As an agent developer, I want every model call, tool call and nondeterministic
input recorded in order, so that I can inspect and replay what my agent actually did.

1.1 WHEN an agent calls `AgentRuntime.complete`, `call_tool`, `now`, `new_id` or `random`
    THE SYSTEM SHALL append exactly one event with execution id, event id, parent event id
    (when given), monotonically increasing `seq`, kind, name, timestamp, duration, source,
    request and either a response or an error.
1.2 WHEN a tool declares an `observe` function THE SYSTEM SHALL record `state_before` and
    `state_after` for that call; otherwise both SHALL be null (no invented state).
1.3 THE SYSTEM SHALL stamp every execution and event with `schema_version` `ghostreplay/v1`.
1.4 WHEN an event is emitted THE SYSTEM SHALL apply the `Redactor` to request, response,
    error, state, metadata and the fault's original response/error before it is stored or
    sent to listeners.
1.5 WHEN an agent calls `rt.log` or `rt.guard` THE SYSTEM SHALL record an `agent_step` or
    `guard` event that is not matched during replay; `guard` events are included in diffs.
1.6 THE SYSTEM SHALL record execution provenance (`model_provider`, `model`, `model_is_live`,
    `label`, `tool_backends`) and SHALL NOT claim to capture hidden model reasoning.

## Requirement 2 — Deterministic offline replay

**User story:** As a developer, I want to replay a recorded execution without contacting any
service, so that I can reproduce a failure exactly.

2.1 WHEN replaying THE SYSTEM SHALL serve the recorded response (or re-raise the recorded error,
    rebuilt through the error-type allowlist) for each interaction that matches the next
    recorded interaction by kind, name and `match_key`.
2.2 WHILE an execution runs in `replay` or `counterfactual-replay` mode THE SYSTEM SHALL NOT
    invoke tool handlers, observers or model adapters, and SHALL block outbound socket access
    from the replaying thread only.
2.3 WHEN an unmodified recording of a deterministic agent is replayed THE SYSTEM SHALL produce
    events structurally identical to the recording (kinds, names, requests, responses, errors,
    timestamps, durations, state).
2.4 WHEN the same recording is replayed twice THE SYSTEM SHALL produce identical results.
2.5 WHEN replay starts THE SYSTEM SHALL use the recording's start time on a `VirtualClock` and
    advance it by each recorded duration.
2.6 IF a replay is requested without a reference recording THEN THE SYSTEM SHALL refuse with a
    `ValueError`.

## Requirement 3 — Divergence detection

**User story:** As a developer, I want replay to stop loudly at the exact step where behaviour
changed, so that I never debug a silently different run.

3.1 WHEN the agent issues an interaction whose kind or name differs from the next recorded
    interaction THE SYSTEM SHALL record a `divergence` event of type `mismatch` with expected
    and actual descriptions.
3.2 WHEN kind and name match but the `match_key` differs THE SYSTEM SHALL record a `mismatch`
    whose `changes` list the differing request paths.
3.3 WHEN the agent issues an interaction after the recording is exhausted THE SYSTEM SHALL raise
    `MissingRecordingError` and record divergence `unexpected_call`; the call SHALL NOT execute.
3.4 WHEN the agent finishes before consuming every recorded interaction THE SYSTEM SHALL record
    divergence `incomplete`.
3.5 WHEN an offline run diverges THE SYSTEM SHALL stop serving recorded responses, mark the
    execution `diverged` and keep the first divergence on `Execution.divergence`.
3.6 WHEN a branch run re-executes a tool and the simulated result differs from the recording
    THE SYSTEM SHALL record divergence `result_mismatch` and continue live.

## Requirement 4 — Execution integrity and safe loading

**User story:** As an operator, I want malformed or tampered recordings rejected with a clear
message, so that nothing is replayed in a silently different order.

4.1 THE SYSTEM SHALL parse every stored row, imported trace, case file and HTTP body through
    Pydantic and SHALL NOT execute, import or evaluate any content.
4.2 IF a document is not valid JSON, not a JSON object, or fails validation THEN THE SYSTEM
    SHALL raise `TraceFormatError` naming the source and the first problems.
4.3 IF an execution's events are not in strictly increasing `seq` order, contain a duplicate
    `event_id`, or carry a `schema_version` other than `ghostreplay/v1` THEN THE SYSTEM SHALL
    reject the document.
4.4 THE SYSTEM SHALL confine trace import/export to a base directory and reject unsafe names
    (separators, `..`, absolute paths).
4.5 THE SYSTEM SHALL reject trace and case files larger than 20 MiB.

## Requirement 5 — Persistence

5.1 THE SYSTEM SHALL persist executions in SQLite so they survive process restarts.
5.2 WHEN the store is file-backed THE SYSTEM SHALL use WAL journaling.
5.3 WHERE `max_executions` is configured THE SYSTEM SHALL keep only the newest N executions per
    app, pruning in the same transaction as the insert.
5.4 WHEN a stored row is unreadable THE SYSTEM SHALL raise `TraceFormatError` on `get` and skip
    (and log) the row on `list`.
5.5 THE SYSTEM SHALL expose a cheap `ping()` used by health endpoints.

## Requirement 6 — Structural diff

6.1 THE SYSTEM SHALL align two executions by interaction signature and report typed entries
    (`added_call`, `removed_call`, `changed_args`, `changed_result`, `changed_error`,
    `changed_model_input`, `changed_model_output`, `changed_value`, `added_guard`,
    `removed_guard`).
6.2 THE SYSTEM SHALL report the first divergence and an `identical` flag.
6.3 THE SYSTEM SHALL report field-level changes as paths with before/after values and a
    behavioural summary (status, outcome, per-tool counts, committed destructive calls,
    invariant outcomes).

## Requirement 7 — Live model recording and offline replay

**User story:** As a developer, I want to record a run driven by a real LLM and replay it
offline for free, so that live behaviour becomes reproducible.

7.1 THE SYSTEM SHALL keep live mode off unless `GHOSTREPLAY_LIVE` is `1`/`true`/`yes`, and SHALL
    validate provider, effort and call budget.
7.2 WHEN recording with `model="live"` THE SYSTEM SHALL record provider-neutral requests and
    responses including tool calls, token usage, `served_by` and provider-native content.
7.3 WHEN a live recording is replayed THE SYSTEM SHALL serve every model call from the recording
    without constructing a client or needing credentials.
7.4 IF a branch run is derived from a live recording and live mode is off THEN THE SYSTEM SHALL
    refuse with a clear error; a scripted recording SHALL never switch to a live model.
7.5 IF the model refuses or the per-execution call budget is exhausted THEN THE SYSTEM SHALL
    fail the run loudly (never record it as success).
7.6 WHEN the public deployment profile is active THE SYSTEM SHALL disable live mode.

## Requirement 8 — Serving labs (HTTP API, SSE, gateway, public profile)

8.1 THE SYSTEM SHALL expose per-lab endpoints for info, scenarios, fault catalog, executions,
    record, replay, counterfactual, diff, regression run/export and demo preparation.
8.2 WHEN a client opens `/api/executions/{id}/replay/stream` THE SYSTEM SHALL emit one SSE
    `event` per engine event as it is recorded, then `done` (or `error`).
8.3 THE SYSTEM SHALL expose `/healthz` (liveness) and `/api/health` (readiness via `ping`), per
    lab and on the gateway.
8.4 WHEN `ghostreplay serve` starts THE SYSTEM SHALL mount every lab registered under the
    `ghostreplay.labs` entry point at `/lab/<name>` and serve the dashboard build at `/`.
8.5 WHERE `GHOSTREPLAY_PUBLIC=1` THE SYSTEM SHALL apply a per-client rate limit to mutating
    requests and replay streams, cap concurrent engine runs (HTTP 503 beyond), cap request
    bodies (HTTP 413; 411 without Content-Length), disable clearing and cap stored executions.
8.6 THE SYSTEM SHALL bind to 127.0.0.1 by default and allow only local dev CORS origins unless
    configured.

## Requirement 9 — Provenance verification on load (planned)

**User story:** As a reviewer of a shared trace, I want to verify that its match keys really
correspond to its recorded requests, so that a hand-edited request cannot replay as if it were
the original.

9.1 WHEN `ghostreplay verify <trace.json>` runs THE SYSTEM SHALL recompute the `match_key` of
    every interaction event from its stored (already redacted) request and report each mismatch
    as `seq`, kind, name, expected and actual key.
9.2 WHERE a tool declares `match_fields` THE SYSTEM SHALL recompute the key over that subset,
    resolving the tool spec from the scenario registry by the execution's scenario id.
9.3 WHEN strict loading is requested (`import_execution(..., strict=True)` or `verify`) and any
    key mismatches THE SYSTEM SHALL raise `TraceFormatError` (CLI exit code 1).

## Requirement 10 — Precise result-mismatch reporting (planned)

10.1 WHEN a branch run records `result_mismatch` THE SYSTEM SHALL name the first differing
     response or error path(s) in the divergence message, as it already does for input changes.
10.2 THE SYSTEM SHALL have a dedicated test that provokes `result_mismatch` and asserts the
     reported path.
