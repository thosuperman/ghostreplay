---
inclusion: always
---

# Product: GhostReplay Lab

**Tagline:** Break AI agents safely. Replay failures. Prove the fix.

## What it is

GhostReplay Lab is an open-source deterministic replay and failure-testing framework for AI
agents, plus a visual debugging environment. Developers record an agent execution, replay it
offline without contacting real services, inject controlled failures (the *Counterfactual
Failure Lab*), detect dangerous behaviour with safety invariants, fix the underlying bug and
prove the fix with generated regression tests.

It is **not** a generic observability dashboard. Every screen exists to answer one question:
*does this agent behave safely when the world misbehaves?*

## Core promise (never compromise)

1. Record → 2. Replay offline → 3. Inject failure → 4. Detect unsafe behaviour →
5. Fix → 6. Prove the fix with a PASS/FAIL regression test.

## Honesty rules

- Always label how an event was produced: `live`, `recorded`, `injected`, `simulated`.
- Always label execution modes: `record`, `replay`, `counterfactual-replay`, `branch`.
- Scripted demonstration models are labelled *scripted*; never present them as live LLM output.
- Never present a hypothetical continuation as a verified outcome. When a counterfactual needs
  new execution, run real (simulated-backend) code in `branch` mode and label it.
- The framework does not capture hidden model reasoning or unobservable application state.

## Audience

- Developers building tool-using agents (support, DevOps, finance, internal automation).
- Hackathon judges: a new visitor must understand the product in ~15 seconds and reach a fully
  prepared demo in one click ("Try the Duplicate Refund Demo").

## Flagship scenarios

- **Duplicate Refund** (Support Agent Lab): refund API times out *after* committing; a naive
  retry issues a second refund. Fix: intent-scoped idempotency key + reconciliation.
- **Unsafe Infrastructure Action** (DevOps Agent Lab): stale health data leads the agent to
  terminate healthy instances. Fix: a safety gate that re-verifies, checks blast radius and
  converts high-risk actions into change proposals.
