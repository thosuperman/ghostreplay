# Requirements — Failure injection and regression proof

## Introduction

The *Counterfactual Failure Lab*: inject controlled failures into recorded executions, run the
consequences honestly (strict offline replay or labelled branch execution), judge the result
with safety invariants, and turn the scenario into a PASS/FAIL regression test. Covers
`packages/ghostreplay/src/ghostreplay/mutation/`, `regression/`, the counterfactual, case and
demo parts of `lab/lab.py`, `server/cli.py` (`run`, `demo`, `export-cases`) and `cli.py`
(`ghostreplay test`).

Written after the implementation existed; requirements 1–7 describe current behaviour,
requirements 8–10 are planned improvements (see `tasks.md`).

## Requirement 1 — Fault catalog

**User story:** As a developer, I want a catalog of realistic production failures, so that I
can test my agent against them without building fault plumbing myself.

1.1 THE SYSTEM SHALL provide these fault kinds: `tool_timeout`, `timeout_after_commit`,
    `http_429`, `http_500`, `auth_failure`, `permission_denied`, `missing_field`, `null_value`,
    `duplicate_response`, `stale_data`, `incorrect_output`, `delayed_operation`,
    `partial_success`.
1.2 Each kind SHALL declare a title, description, strategy (`error`, `transform`,
    `execute_then_error`, `delay`), `requires_branch` and documented params.
1.3 THE SYSTEM SHALL serve the catalog at `GET /api/faults`.
1.4 IF a fault names an unknown kind THEN THE SYSTEM SHALL reject the plan before running.

## Requirement 2 — Targeting and application

2.1 WHEN a `FaultSpec` targets `(kind, name, occurrence, where)` THE SYSTEM SHALL apply it only
    to the interaction with that kind and name whose 1-based occurrence matches (all
    occurrences when `occurrence` is null) and whose request contains every `where` value.
2.2 WHEN a fault is applied THE SYSTEM SHALL mark the event source `injected` and store an
    `AppliedFault` with fault id, kind, strategy, description, `operation_executed` and the
    original response or error.
2.3 WHEN a transform fault's path does not exist THE SYSTEM SHALL leave the response unchanged
    and say so in the applied fault's description.
2.4 WHEN an `execute_then_error` or `delay` fault runs THE SYSTEM SHALL really execute the
    operation against the simulated backend, so the side effect is committed.
2.5 WHEN a replayed slot is replaced by a fault THE SYSTEM SHALL annotate it `substituted`.

## Requirement 3 — Counterfactual execution modes

**User story:** As a developer, I want to know whether a counterfactual result was observed or
merely assumed, so that I never trust an invented continuation.

3.1 WHEN `mode="replay"` THE SYSTEM SHALL run offline (`counterfactual-replay`), stop at the
    first divergence and note that branch mode is needed to see the continuation.
3.2 IF a fault `requires_branch` and the run is offline THEN THE SYSTEM SHALL refuse it rather
    than fake the side effect.
3.3 WHEN `mode="branch"` THE SYSTEM SHALL rebuild a fresh simulated environment, re-execute
    tools (verifying them against the recording while on-track), serve recorded model calls and
    nondeterminism while on-track, and execute live after divergence, labelling events
    `simulated` and the execution `branch`.
3.4 WHEN `mode="auto"` THE SYSTEM SHALL choose branch if any fault requires it or a different
    agent variant is under test, and offline counterfactual replay otherwise.
3.5 IF strict replay is requested for a different variant THEN THE SYSTEM SHALL refuse.

## Requirement 4 — Safety invariants

4.1 THE SYSTEM SHALL evaluate every scenario invariant after every execution, returning
    `passed`, `failed` or `inconclusive` with a message, explanation and evidence event ids.
4.2 WHEN an invariant `requires_state` and final state is not observable (offline
    counterfactual) THE SYSTEM SHALL report `inconclusive`, never `passed`.
4.3 THE SYSTEM SHALL offer generic invariants: `errors_surfaced` (unrecovered tool errors must
    not end in `success`) and `max_successful_calls`.

## Requirement 5 — Regression cases and reports

5.1 THE SYSTEM SHALL represent a case as data: id, title, app, scenario id, variant,
    conditions, faults, optional embedded reference execution, mode, invariant ids, expectation.
5.2 WHEN a case is derived from an execution THE SYSTEM SHALL expect `pass` for fix variants
    and `fail` for vulnerable variants unless told otherwise.
5.3 WHEN a case is written THE SYSTEM SHALL emit `<id>.case.json` and a runnable
    `test_<id>.py` inside the target directory (no path traversal).
5.4 WHEN `ghostreplay test` runs case files or directories THE SYSTEM SHALL print an
    explanation per case, write optional JSON and JUnit XML reports, and exit 1 when any case's
    outcome does not match its expectation.
5.5 THE SYSTEM SHALL resolve a case's scenario by id from the registry, never by import path.
5.6 WHEN any selected invariant is inconclusive or the agent crashed THE SYSTEM SHALL NOT count
    the case as passed.

## Requirement 6 — Guided demo story

6.1 WHEN a demo is prepared THE SYSTEM SHALL record the incident, replay it offline, record a
    healthy baseline, run the headline preset against the vulnerable and fixed variants in
    branch mode, diff them and run both regression cases.
6.2 Each step SHALL carry its observed verdict and, where the story depends on it, an
    `expected` verdict; `as_expected` and `DemoStory.ok` SHALL be computed from them.
6.3 WHEN `<lab> demo` runs and any step misses its expectation THE SYSTEM SHALL print which step
    and exit with status 1.

## Requirement 7 — Lab CLI commands

7.1 `<lab> run [--variant] [--incident] [--live]` SHALL record one run, print each invariant and
    exit 1 when any invariant failed.
7.2 `<lab> export-cases --out DIR` SHALL record a baseline, apply the headline preset and write
    one case per variant (vulnerable expects FAIL, fixed expects PASS).

## Requirement 8 — `reordered_response` fault kind (planned)

8.1 THE SYSTEM SHALL provide a replay-safe transform fault `reordered_response` that reverses
    (default) or rotates (`params.rotate: int`) the list at `params.path` (default: first list
    found) in a tool response.
8.2 WHEN the path is missing or not a list THE SYSTEM SHALL leave the response unchanged and
    say so in the applied fault's description.
8.3 THE SYSTEM SHALL list the new kind in `GET /api/faults`, and the Failure Lab SHALL offer
    default params for it.

## Requirement 9 — `clock_skew` fault for nondeterminism (planned)

9.1 THE SYSTEM SHALL allow `FaultTarget.kind = "nondeterminism"` so faults can target
    `clock.now`, `ids.new` and `random.random`.
9.2 THE SYSTEM SHALL provide a replay-safe `clock_skew` transform that shifts the ISO timestamp
    returned by `clock.now` by `params.skew_ms` (may be negative).
9.3 WHEN the schema changes THE SYSTEM SHALL mirror it in `apps/dashboard/src/api/types.ts`.

## Requirement 10 — Exporting any preset as a regression case (planned)

10.1 WHEN `<lab> export-cases --preset <id>` runs THE SYSTEM SHALL export cases for that preset
     instead of the headline preset, and reject unknown preset ids with exit status 2.
10.2 THE SYSTEM SHALL have a pytest that runs `<lab> demo` through `main([...])` and asserts exit
     status 0 for both labs.
