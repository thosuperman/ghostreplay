# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet.

## [0.1.0] - 2026-11-07

First public version: the shared GhostReplay framework, two labs built on it, a dashboard,
and a one-container deployment.

### Added

#### Framework (`packages/ghostreplay`)

- `AgentRuntime`, the single door between an agent and the world: model calls, tool calls,
  clock reads, ids and random numbers, plus step and guard annotations.
- `Session` with four execution modes: `record`, `replay` (deterministic and offline),
  `counterfactual-replay` (offline with injected faults, stops at the first divergence) and
  `branch` (replayed prefix, then labelled re-execution against a fresh simulated environment).
- Event sources on every event: `live`, `recorded`, `injected`, `simulated`.
- Divergence detection by kind, name and a hash of the redacted request, with field-level
  diffs. Recorded responses are never consumed out of order.
- Thread-local offline network guard and handler stubs that raise during offline replay.
- `Redactor` for sensitive keys, AWS access keys, bearer tokens, `sk-` keys, GitHub tokens,
  private keys and Luhn-valid card numbers, applied before anything is stored.
- Fault catalog with 13 kinds: `tool_timeout`, `timeout_after_commit`, `http_429`,
  `http_500`, `auth_failure`, `permission_denied`, `missing_field`, `null_value`,
  `stale_data`, `incorrect_output`, `duplicate_response`, `delayed_operation`,
  `partial_success`.
- Structural trace diff with first-divergence detection and a behavioural summary.
- Safety invariants with `passed`, `failed` and `inconclusive` results and evidence event ids.
- Regression cases as validated data, pytest module generation, and JUnit XML and JSON
  reports (`ghostreplay test`).
- Simulated backends: allowlisted `ToolRegistry`, HTTP service, database and AWS-like cloud;
  `ScriptedModel` for deterministic, labelled scripted decisions.
- SQLite storage and safe trace import and export confined to a base directory.
- FastAPI app factory with a Server-Sent Events replay stream, and a shared lab CLI
  (`serve`, `run`, `demo`, `export-cases`).
- Optional live LLM mode (`uv sync --extra live`, `GHOSTREPLAY_LIVE=1`) with an Anthropic
  adapter (default model `claude-opus-5-5`), a per-execution call budget, refusal handling,
  and fully offline replay of live recordings.

#### Applications

- Support Agent Lab (`apps/support-agent`): the Duplicate Refund scenario. A refund that
  times out after commit is retried without an idempotency key and the customer is refunded
  twice ($129 becomes $258). The fixed harness uses an intent-scoped idempotency key and
  reconciles before retrying.
- DevOps Agent Lab (`apps/devops-agent`): the Unsafe Infrastructure Action scenario. A stale
  health view makes the agent terminate all three healthy `checkout-api` instances. The fixed
  harness routes destructive actions through a SafetyGate (fresh verification, IAM check,
  blast-radius budget, human approval).
- Committed regression cases for both scenarios in `tests/regression/`.
- `examples/minimal_agent.py`, a complete bring-your-own-agent integration.

#### Dashboard (`apps/dashboard`)

- React, TypeScript (strict), Vite and Tailwind CSS dashboard with a one-click guided demo
  per lab, Execution Explorer, Timeline and Inspector, Replay Studio (live SSE stream),
  Counterfactual Failure Lab, Structural Diff and Regression Results with pytest export.
- Scripted and live executions are labelled as such.
- Playwright end-to-end tests that run against the one-process gateway or a deployment
  (`E2E_BASE_URL`).

#### Deployment and tooling

- `ghostreplay serve` gateway that mounts every installed lab and the built dashboard on
  one port, with `/healthz` and `/api/health`.
- Dockerfile (non-root user, health check), `compose.yaml` (read-only, resource limits) and
  a Render Blueprint (`render.yaml`).
- Public deployment profile (`GHOSTREPLAY_PUBLIC=1`): rate limits, concurrent-run cap, body
  size cap, execution retention cap, clearing disabled, live mode disabled.
- GitHub Actions CI with Python (ruff, tests, demos, regression cases), dashboard
  (typecheck, build), Playwright end-to-end, and container smoke-test jobs.
- `.kiro/` steering documents, per-component specs and agent hooks.

[Unreleased]: https://github.com/thosuperman/ghost-replay/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/thosuperman/ghost-replay/releases/tag/v0.1.0
