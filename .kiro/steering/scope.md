---
inclusion: always
---

# Scope boundaries and priorities

## P0 — must work
Shared framework; real recording; deterministic offline replay; tool mocks; structural diff;
Duplicate Refund scenario; Unsafe Infrastructure Action scenario; two separately runnable apps;
basic timeline; reliable PASS/FAIL regression checks.

## P1 — strong demo
Failure-injection UI; side-by-side diff viewer; replay controls; polished dark dashboard;
exportable test cases; clear failure explanations.

## P2 — only after P0 and P1 work
Advanced mutation operators; live model provider adapter; CI integration; additional scenarios.

## Never build
Registration, billing, multi-tenant SaaS, auth servers, cloud infrastructure, distributed
processing, enterprise admin.

## Phase discipline
Foundation → core framework (+ tests) → Support Agent → DevOps Agent → Dashboard → polish.
Verify each phase with executable tests before moving on. A feature is "done" only when a test
or a scripted end-to-end run demonstrates it.
