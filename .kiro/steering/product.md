---
inclusion: always
---

# Product: GhostReplay Lab

**Tagline:** Break AI agents safely. Replay failures. Prove the fix.

## What it is

GhostReplay Lab is an open-source deterministic replay and failure-testing framework for
tool-using AI agents (`packages/ghostreplay`), two independent demo applications built on it,
and a React dashboard that drives them. A developer records an agent execution, replays it
offline without contacting any service, injects controlled failures (the *Counterfactual
Failure Lab*), detects dangerous behaviour with safety invariants, fixes the harness and proves
the fix with a generated PASS/FAIL regression test.

It is **not** a generic observability dashboard. Every screen answers one question:
*does this agent behave safely when the world misbehaves?*

## Core loop (never compromise)

1. Record → 2. Replay offline → 3. Inject failure → 4. Detect unsafe behaviour →
5. Fix → 6. Prove the fix with a PASS/FAIL regression test.

## Honesty rules

- Every event says where its response came from: `live`, `recorded`, `injected`, `simulated`
  (plus `framework` for bookkeeping events).
- Every execution says how it ran: `record`, `replay`, `counterfactual-replay`, `branch`.
- Scripted demonstration models (`support-sim-1`, `sre-sim-1`) are labelled *scripted* and are
  never presented as live LLM output. Live-model recordings carry `model_is_live: true`.
- A hypothetical continuation is never presented as a verified outcome. Offline counterfactual
  replay stops at the first divergence; continuing requires `branch` mode, which really
  re-executes the agent against fresh simulated backends and is labelled as such.
- The framework does not capture hidden model reasoning or unobservable application state.
- Tools are always in-memory simulations, also in live AI mode: a live model can change what
  the agent *decides*, never what the tools touch.

## Audience

- Developers building tool-using agents (support, DevOps, finance, internal automation).
- First-time visitors (including judges): the promise must be clear in ~15 seconds, and one
  click must reach a fully prepared demo — **Try the Duplicate Refund Demo** or
  **Try the Unsafe Infrastructure Demo** on the home page.

## Flagship scenarios

| Lab | Scenario id | What goes wrong | Fix (in harness code, model unchanged) |
|---|---|---|---|
| Support Agent Lab (`apps/support-agent`) | `duplicate-refund` | Refund API commits, the response times out, the naive retry refunds the customer twice. | Intent-scoped idempotency key + reconciliation via `payments.list_refunds` before retry. |
| DevOps Agent Lab (`apps/devops-agent`) | `unsafe-infra-action` | A stale health view reports healthy instances as impaired; the agent terminates the fleet. | `SafetyGate`: direct re-verification, IAM check, blast-radius budget, change proposal for human approval. |

## Modes of use

- **Offline demo (default):** scripted models, no keys, fully reproducible.
- **Live AI (opt-in):** `GHOSTREPLAY_LIVE=1` + provider credentials; recordings replay offline
  without the API. See #[[file:docs/live-ai.md]].
- **Hosted demo:** one container (`ghostreplay serve`) with the public deployment profile
  (`GHOSTREPLAY_PUBLIC=1`). See #[[file:docs/deployment.md]].
