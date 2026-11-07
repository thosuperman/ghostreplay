# Requirements — Dashboard

## Introduction
A dark-mode developer tool that drives both labs through the shared HTTP API. Every number and
event on screen comes from a real execution stored by a lab server.

## Requirement 1 — First 15 seconds
1.1 The landing view SHALL state the promise (record → replay → break → fix → prove) and offer
    one-click demos: "Try the Duplicate Refund Demo" and "Try the Unsafe Infra Action Demo".
1.2 A demo click SHALL call `POST /api/demo/prepare` and open a guided story whose steps link
    to the real executions it produced.

## Requirement 2 — Screens
2.1 Execution Explorer: status, mode, variant, duration, tool calls, failed invariants.
2.2 Execution Timeline + Inspector: chronological events, source badges, request/response,
    state before/after, errors, injected faults, replay verdicts.
2.3 Replay Studio: replay over Server-Sent Events; the animation renders each event as the
    engine emits it, with its match verdict; speed control.
2.4 Failure Lab: choose execution, target event, fault kind/params or preset, agent variant;
    shows which event changed and why, and whether branch execution was required.
2.5 Diff Viewer: side-by-side aligned interactions; first divergence highlighted; field-level
    changes.
2.6 Regression: run cases for both variants, PASS/FAIL per invariant with explanations,
    export pytest source.

## Requirement 3 — Labels
3.1 Mode, source and model provenance (scripted vs live) SHALL be visible wherever events are.

## Requirement 4 — Quality
4.1 TypeScript strict, no runtime errors in console during demo flows, responsive ≥ 1280 px,
    usable at 1024 px.
