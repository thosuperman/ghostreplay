---
inclusion: always
---

# Architecture principles and repository structure

```
packages/ghostreplay/src/ghostreplay/   shared framework (all real functionality)
  models/      versioned execution schema (Event, Execution, FaultSpec, ...)
  core/        canonical JSON hashing, clocks, deterministic sources, errors
  recorder/    Recorder + Redactor
  runtime/     AgentRuntime: the only door between an agent and the world
  replay/      Session (record / replay / branch), offline network guard
  mocking/     ToolRegistry, simulated HTTP / database / AWS backends, model adapters
  mutation/    fault catalog + fault application
  diff/        structural trace diff
  regression/  invariants, regression cases, runner, pytest generation, JUnit/JSON reports
  lab/         Scenario abstraction + Lab orchestrator
  storage/     SQLite store, safe trace import/export
  server/      FastAPI app factory used by every lab
apps/support-agent/   Support Agent Lab (Duplicate Refund)   — imports ghostreplay
apps/devops-agent/    DevOps Agent Lab (Unsafe Infra Action) — imports ghostreplay
apps/dashboard/       React dashboard, talks to any lab via the shared HTTP API
tests/regression/     generated, committed regression cases
```

## Principles

1. **One door.** Agents touch the outside world only through `AgentRuntime`
   (`complete`, `call_tool`, `now`, `new_id`, `random`). That is what makes deterministic
   replay possible without monkey-patching arbitrary libraries.
2. **One code path.** Model calls, tool calls and nondeterminism all flow through
   `Session.interact`. Record, replay, fault injection and branch execution are policies of
   that single path, not separate engines.
3. **Framework knows no business logic.** No refunds, orders or EC2 in `ghostreplay`. The
   simulated backends are generic (HTTP routes, tables, cloud resources); apps supply data.
4. **Strict ordering, loud divergence.** Replay consumes recorded interactions in order. Any
   mismatch produces a `divergence` event; recorded responses are never consumed out of order.
5. **Fix in code you control.** Both demo apps share one scripted model per scenario; the
   vulnerable and fixed variants differ only in harness code (retry/idempotency, safety gate).
6. **Simplicity.** Prefer a 50-line clear function over an abstraction with one user.
