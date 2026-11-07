# Requirements — Dashboard

## Introduction

A dark-mode developer tool (`apps/dashboard`, React + TypeScript strict + Vite + Tailwind v4)
that drives both labs through the shared HTTP API. Every number and event on screen comes from
a real execution stored by a lab server. In development it proxies `/lab/support` and
`/lab/devops` to the lab servers; in deployment the gateway serves its build at `/`.

Written after the implementation existed; requirements 1–7 describe current behaviour,
requirements 8–9 are planned improvements (see `tasks.md`).

## Requirement 1 — First 15 seconds

**User story:** As a first-time visitor, I want to understand the product and see it work with
one click, so that I do not need to read docs first.

1.1 THE home page SHALL state the promise (record → replay → break → detect → prove) and offer
    two one-click demos: "Try the Duplicate Refund Demo" and "Try the Unsafe Infrastructure Demo".
1.2 WHEN a demo card is clicked THE dashboard SHALL open the lab's guided story, which calls
    `POST /api/demo/prepare` and links every step to the real executions it produced.
1.3 IF the story reports `ok: false` THEN THE dashboard SHALL show an alert naming each step whose
    verdict differs from its `expected` verdict.

## Requirement 2 — Screens

2.1 Execution Explorer: lists executions (mode, variant, status, duration, tool calls, failed
    invariants) and records new runs under healthy or incident conditions.
2.2 Execution view: timeline with source badges and simulated-time bars, plus an Inspector with
    prompt/request, response or error, state before/after, injected fault and replay verdict.
2.3 Replay Studio: replays over Server-Sent Events, rendering each event as the engine emits it;
    the pacing control sets the engine's `delay_ms`.
2.4 Failure Lab: choose a recording, a target event, a fault kind (from `GET /api/faults`) with
    JSON params or a preset, an agent variant and a mode; shows what changed and whether branch
    execution was needed.
2.5 Diff: side-by-side aligned interactions, first divergence, field-level changes, behaviour
    table.
2.6 Regression: run the case for every variant with PASS/FAIL per invariant and explanations;
    export the pytest module and case file.

## Requirement 3 — Honest labels

3.1 Mode, event source and model provenance (scripted vs live, label, tool backends) SHALL be
    visible wherever executions or events are shown.

## Requirement 4 — Live AI option

4.1 WHERE `GET /api/info` reports a non-null `live_model` THE Explorer SHALL offer a "Model"
    selector with "Scripted" and "Live AI: <provider> <model> (≤N calls)".
4.2 WHERE `live_model` is null THE selector SHALL NOT be shown and runs SHALL be recorded with the
    scripted model.

## Requirement 5 — Lab connectivity

5.1 THE header SHALL poll each lab's `/api/info` and show whether it is up.
5.2 WHEN a lab is unreachable THE API client SHALL raise an error that tells the user how to
    start it.

## Requirement 6 — Types mirror the schema

6.1 `src/api/types.ts` SHALL mirror the Pydantic models field for field (including `DemoStep`
    `expected`/`as_expected`, `DemoStory.ok`, `LabInfo.live_model`).

## Requirement 7 — Quality and end-to-end coverage

7.1 THE dashboard SHALL type-check with `tsc --noEmit` in strict mode and build with Vite.
7.2 THE repository SHALL contain Playwright browser tests that run against the gateway (both labs
    + built dashboard) on a fresh store, or against `E2E_BASE_URL`.

## Requirement 8 — Inspector details for model calls (planned)

**User story:** As a developer debugging a live-model run, I want to see what the model call
cost and which model actually answered.

8.1 WHEN the selected event is a `model_call` THE Inspector SHALL show `response.usage` (input /
    output tokens, or scripted character counts) and `response.served_by` when present.
8.2 THE Inspector SHALL offer "Copy as JSON" for the selected event (the full `GREvent`).
8.3 An e2e test SHALL open an execution, select a model call and assert the usage block and the
    copy button are visible.

## Requirement 9 — Live/scripted badge in the Explorer list (planned)

9.1 THE Explorer list SHALL show a `live` badge for executions whose `model_provider` is not
    `scripted`, and `scripted` otherwise.
9.2 An e2e test SHALL assert that a freshly recorded run is labelled `scripted`.
