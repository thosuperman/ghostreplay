---
inclusion: manual
---

# Competition context, scope and honesty (reference with #competition)

Use this file when planning work for the competition submission, deciding what to build next,
or writing anything a judge will read (README, demo script, video narration, submission text).

## Provenance — state it exactly, every time
- The framework, both labs and the dashboard were implemented **before** this repository was
  opened in Kiro. The specs in `.kiro/specs/` were written afterwards to document that
  implementation; tasks marked `[x]` describe work that already existed.
- Unchecked `[ ]` tasks are real, not-yet-done improvements intended to be executed in Kiro.
- Never claim or imply that Kiro generated, executed or completed something it did not.
  Evidence of Kiro usage must be genuine: spec task executions, hook runs and commits made
  during this phase. Do not fabricate chat logs, screenshots, timestamps or usage numbers.
- The capture procedure is in #[[file:docs/kiro-workflow.md]]; ready-made prompts for the open
  tasks are in #[[file:docs/kiro-demo-prompts.md]].

## Scope priorities

**P0 — must keep working:** shared framework; real recording; deterministic offline replay;
tool mocks; structural diff; Duplicate Refund scenario; Unsafe Infrastructure Action scenario;
two separately runnable apps; timeline; reliable PASS/FAIL regression checks; both guided demos
reporting `ok` (CLI `demo` exits 0).

**P1 — strong demo:** Failure Lab UI; side-by-side diff; Replay Studio (SSE); polished dark
dashboard; exportable test cases; clear failure explanations; one-container hosted demo.

**P2 — only once P0 and P1 are green:** more fault kinds; more invariants and presets; live
model provider adapters beyond the existing one; extra scenarios; inspector improvements.

**Never build:** registration, billing, multi-tenant SaaS, auth servers, real cloud
integrations, distributed processing, enterprise admin.

## Phase discipline
1. Pick one open task from a spec; read its requirement and acceptance criteria.
2. Write or extend the test first where practical (a failing test that demonstrates the gap).
3. Implement; let the hooks run (framework tests, scenario regressions, typecheck, secret scan,
   lint on stop).
4. Run the spec's verification commands; tick the task only when they pass.
5. Commit with an honest Conventional Commit message describing the change.

A feature is "done" only when a test or a scripted end-to-end run demonstrates it.

## What a first-time viewer must see in 15 seconds
The promise (record → replay → break → detect → fix → prove), two one-click demos ("Try the
Duplicate Refund Demo", "Try the Unsafe Infrastructure Demo"), and labels that make clear the
decisions come from a scripted model unless live AI mode is on.

## Submission rules
This file does not restate the competition's official rules, categories or deadlines; check
the official rules page before submitting and keep README claims consistent with the code.
