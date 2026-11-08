---
inclusion: always
---

# Repository structure

```
packages/ghostreplay/src/ghostreplay/   shared framework (all real engine functionality)
  models/        versioned schema ghostreplay/v1: Event, Execution (+ integrity validator),
                 ExecutionSummary, FaultSpec/FaultTarget/FaultPreset, Divergence, results
  core/          canonical JSON + stable hashing, deep_diff, VirtualClock, DeterministicSources,
                 error hierarchy (GhostReplayError, TraceFormatError, ToolError family)
  recorder/      Recorder (sequenced events, listeners) + Redactor
  runtime.py     AgentRuntime: complete / call_tool / now / new_id / random / log / guard
  replay/        Session (record, replay, counterfactual-replay, branch) + offline_guard
  mocking/       ToolRegistry/ToolSpec allowlist, simulated HTTP service, database, AWS-like
                 cloud, ModelAdapter protocol + ScriptedModel
  llm/           optional live mode: LiveModelConfig (env), AnthropicModel adapter
  mutation/      fault catalog (15 kinds) + FaultPlan + apply_fault
  diff/          structural trace diff (alignment, typed entries, first divergence, behaviour)
  regression/    Invariant/Check/TraceView, RegressionCase/Report, runner, pytest + JUnit/JSON
  lab/           Scenario abstraction, registry (ghostreplay.scenarios entry points), Lab
                 orchestrator, guided demo story (DemoStep.expected / DemoStory.ok)
  storage/       SqliteStore (WAL, retention cap, ping), parse_document, safe import/export
  server/        create_app (per-lab HTTP API + SSE), ServerSettings/RateLimiter (public
                 profile), create_gateway (ghostreplay.labs entry points), lab_main CLI
  sdk.py         public SDK: GhostReplay (decorators, record/replay/inject/diff, traces,
                 regression helpers), Run, fault(); invariants.py re-exports ready-made checks
  cli.py         `ghostreplay inspect | diff | replay --app | export | test --import | scenarios | serve`
packages/ghostreplay/tests/   framework guarantee tests (toy-bank scenario in toy.py)
apps/support-agent/           Support Agent Lab — Duplicate Refund (support_agent package)
apps/devops-agent/            DevOps Agent Lab — Unsafe Infrastructure Action (devops_agent)
apps/dashboard/               React dashboard (src/api, src/components, src/lib, src/views)
tests/regression/             committed regression cases (*.case.json + generated test_*.py)
tests/                        deployment/gateway tests, public session isolation, example test, secret-scanner test
examples/minimal_agent.py     engine-level (Lab/Scenario) integration example
examples/invoice-agent/       separate project using only the public SDK (+ tests/regression)
docs/sdk/                     SDK docs; every runnable block is executed by tests/test_sdk_docs.py
apps/dashboard/src/views/     Home, GuidedDemo (+ guided/demos.ts), Connect, ImportTrace and the
                              developer views (Explorer, Execution, Replay, FailureLab, Diff, Regression)
scripts/                      dev.sh (start everything), secret_scan.py
docs/                         architecture, deployment (+ docs/deployment/ for production), live AI, Kiro workflow
deploy/lightsail/             production: provision, DNS, deploy/rollback, backups, Caddyfile, systemd units
.github/workflows/ci.yml      CI pipeline
Dockerfile, compose.yaml, render.yaml   container + hosting
.kiro/                        steering, specs, hooks, settings (this directory)
```

Each lab app has the same layout: `environment.py` (simulated world), `tools.py` (ToolSpecs
with Pydantic argument models), `model.py` (scripted policy), `agent.py` (harness with a
`vulnerable` and a `fixed` variant), `invariants.py`, `scenario.py` (Scenario subclass + fault
presets), `cli.py` (`build_lab` + `main` via `lab_main`). Apps register their scenario under the
`ghostreplay.scenarios` entry point and their lab under `ghostreplay.labs`.

## Principles

1. **One door.** Agents touch the world only through `AgentRuntime`. That is what makes
   deterministic replay possible without monkey-patching libraries.
2. **One code path.** Model calls, tool calls and nondeterminism all flow through
   `Session.interact`. Record, replay, fault injection and branch execution are policies of
   that one path, not separate engines.
3. **Framework knows no business logic.** No refunds or EC2 in `ghostreplay`; simulated backends
   are generic, apps supply data, tools, invariants and presets.
4. **Strict ordering, loud divergence.** Replay consumes recorded interactions in `seq` order;
   any mismatch produces a `divergence` event. Recordings that are out of order, have duplicate
   event ids or a different schema version are rejected on load (`TraceFormatError`).
5. **Fix in code you control.** Both variants of an app share one scripted model; they differ
   only in harness code (idempotent retry, SafetyGate).
6. **Simplicity.** Prefer a clear 50-line function over an abstraction with one user.
7. **Labs stay independent.** Each app runs alone (`<app> serve`); the gateway only hosts them
   side by side.
