# Requirements — GhostReplay core framework

## Introduction
The `ghostreplay` package records the observable execution of a tool-using AI agent, replays
it deterministically offline, injects controlled failures, compares executions structurally and
turns scenarios into PASS/FAIL regression tests. Two applications (Support Agent Lab, DevOps
Agent Lab) are built exclusively on this package.

## Requirement 1 — Execution recording
**User story:** As an agent developer, I want every model call, tool call and nondeterministic
input recorded in order, so that I can inspect and replay what my agent actually did.

1.1 WHEN an agent calls a model, a tool, the clock, the id generator or the random source
    through `AgentRuntime` THEN the system SHALL append exactly one event with execution id,
    event id, parent event id (when applicable), sequence number, kind, name, timestamp,
    duration, agent identity, source, request, response or error.
1.2 WHEN a tool declares an `observe` function THEN the system SHALL record state before and
    after the operation; otherwise state fields SHALL be null (no invented state).
1.3 THE system SHALL stamp every execution and event with `schema_version`.
1.4 WHEN an event is persisted THEN the system SHALL apply the configured `Redactor` to
    request, response, error, state and metadata.
1.5 THE system SHALL NOT claim to capture hidden model reasoning.

## Requirement 2 — Deterministic offline replay
**User story:** As a developer, I want to replay a recorded execution without contacting any
service, so that I can reproduce a failure exactly.

2.1 WHEN replaying THEN the system SHALL return recorded responses (or re-raise recorded errors)
    for interactions that match the next recorded interaction by kind, name and canonical
    request hash.
2.2 WHEN replaying THEN the system SHALL NOT invoke tool handlers or model adapters, and SHALL
    block outbound socket connections from the replaying thread.
2.3 WHEN the agent issues an interaction that does not match the next recorded interaction
    THEN the system SHALL record a `divergence` event with expected vs actual and a structural
    request diff, stop consuming the recording, and mark the execution `diverged`.
2.4 WHEN the agent issues an interaction after the recording is exhausted THEN the system SHALL
    raise `MissingRecordingError` (recorded as divergence `unexpected_call`).
2.5 WHEN the agent finishes before consuming all recorded interactions THEN the system SHALL
    report divergence `incomplete`.
2.6 Replaying an unmodified recording of a deterministic agent SHALL produce a trace that is
    structurally identical to the recording (same kinds, names, requests, responses, errors,
    timestamps and durations).

## Requirement 3 — Tool interception and mocking
3.1 THE system SHALL expose a `ToolRegistry` that only allows registered tools (allowlist) and
    validates arguments with an optional Pydantic model.
3.2 THE system SHALL provide generic simulated backends: HTTP service, database, AWS-like cloud.
3.3 Tools SHALL declare `destructive` and `category`; destructive calls SHALL be flagged on
    their events.
3.4 Simulated backends SHALL be deterministic for a given seed/fixture and virtual clock.

## Requirement 4 — Model adapters
4.1 THE system SHALL define a `ModelAdapter` protocol with `provider`, `model`, `is_live`.
4.2 THE system SHALL provide `ScriptedModel`, labelled `scripted` in provenance.

## Requirement 5 — Counterfactual Failure Lab (mutation)
5.1 THE system SHALL provide a fault catalog: tool_timeout, timeout_after_commit, http_429,
    http_500, missing_field, null_value, duplicate_response, delayed_operation, stale_data,
    incorrect_output, auth_failure, permission_denied, partial_success.
5.2 Each fault SHALL declare a strategy (`error`, `transform`, `execute_then_error`, `delay`)
    and whether it `requires_branch` (needs the operation to really execute against the
    simulated backend).
5.3 WHEN a fault targets an interaction (selector: tool name, occurrence, argument subset)
    THEN the system SHALL record the fault and the original response on the event and mark
    the event source `injected`.
5.4 WHEN a counterfactual replay diverges after a fault THEN the system SHALL stop and report
    that the continuation requires branch execution (it SHALL NOT fabricate a continuation).
5.5 WHEN running in `branch` mode THEN the system SHALL re-execute tools against a fresh
    simulated environment, serve recorded model responses while on-track, verify tool results
    against the recording, and execute the model adapter live after divergence, labelling
    every event's source.

## Requirement 6 — Structural diff
6.1 THE system SHALL align two traces by interaction signature and report added/removed calls,
    changed tool arguments, changed tool results, changed model inputs/outputs, changed errors,
    status/output changes and invariant outcome changes.
6.2 THE system SHALL report the first divergence index in both traces.
6.3 Field-level changes SHALL be reported as JSON paths with before/after values.

## Requirement 7 — Regression testing
7.1 THE system SHALL evaluate safety invariants returning passed / failed / inconclusive with
    evidence event ids and an explanation.
7.2 THE system SHALL represent a regression case as data (scenario id, variant, conditions,
    faults, optional reference execution, invariant ids, expectation).
7.3 THE system SHALL generate a runnable pytest module for a case and produce JSON and JUnit XML
    reports.

## Requirement 8 — Persistence and safety
8.1 Executions SHALL be persisted in SQLite and survive restarts.
8.2 Trace import SHALL validate with Pydantic and SHALL NOT execute content.
8.3 Export/import paths SHALL be confined to a base directory (no traversal).
