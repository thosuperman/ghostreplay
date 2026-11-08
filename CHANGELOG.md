# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Real execution.**
  - The support lab runs on a real SQLite database and an HTTP refund service.
  - The DevOps lab runs on three HTTP instance services and an allowlisted HTTP controller.
  - Both run on 127.0.0.1, are created fresh per run, and are never started by a strict
    replay.
  - New `ghostreplay.labkit` building blocks for these services.
- **Genuine Claude captures** shipped as a read-only library (`scripts/capture_live.py`).
  `POST /api/runs/reexecute` re-runs a capture for real, serving its model decisions from
  the recording.
  - Guided demos are built on the captures, with actor-tagged stories and execution-type
    labels.
- **An opt-in live provider test** (`tests/live`) and live LLM extraction in the invoice
  example.

### Fixed

- The Anthropic adapter sent every tool with an empty input schema, because it ignored the
  `parameters` key, so live models could not pass arguments.
- Responses served from a recorded injected fault keep their fault label in replay and
  re-execution.
- Provenance no longer reports "simulated (in-memory)" backends for scenarios that use real
  services.

- **Python SDK** (`ghostreplay.GhostReplay`).
  - Decorators for tools (sync and async), model functions, agents, invariants, and state and
    reset hooks; `new_id()`, `now()` and `step()`.
  - `record`, strict offline `replay`, `inject` (fault injection, optionally re-executing
    another agent), `diff`, trace `export` and `load`, and regression helpers that write
    pytest modules.
  - Only routed calls are recorded.
- **CLI:** `ghostreplay inspect`, `diff`, `replay --app`, `export` and `test --import`.
- **External example:** `examples/invoice-agent`, a separate Invoice Processing Agent that
  depends only on the public SDK, with committed regression cases.
- **Guided demos** at `/demo/refund` and `/demo/devops`: six steps (meet the agent, failure,
  investigation, offline replay, fixed agent, regression verification), all driven by real
  executions.
- **New homepage**, a Guided / Developer mode switch, a Connect Your Agent page, and trace
  import and download (session-scoped, validated, re-redacted, never executed).
- **SDK documentation** in `docs/sdk/` (13 pages); every runnable code block is executed by
  `tests/test_sdk_docs.py`.
- **CI:** an `sdk` job that builds the wheel and runs the external example in a fresh virtual
  environment.

- Public demo deployed at https://ghostreplay.hayaix.tech on a dedicated AWS Lightsail
  instance (2 GB, `us-east-1`), with scripts in `deploy/lightsail/`:
  - provisioning, the Route 53 record and HTTPS via Caddy;
  - two sandboxed systemd services, one per lab, with no network access beyond loopback;
  - atomic releases with automatic rollback;
  - daily SQLite backups with a tested restore;
  - a five-minute health and resource monitor.
- Per-visitor session isolation in the public profile. An anonymous HttpOnly cookie scopes
  every API read and write to the visitor's own executions; those runs expire after 24
  hours and are capped per session. The store never lets one owner overwrite another
  owner's execution, and existing databases are migrated in place.
- Production deployment documentation in `docs/deployment/`: architecture, cost, domain and
  HTTPS, environment variables, security, backup and restore, update and rollback,
  troubleshooting.
- A Playwright test that a second browser session cannot see the first session's runs.

### Changed

- The core `ghostreplay` package now depends only on pydantic. FastAPI and uvicorn moved to
  the `server` extra, which the bundled labs depend on.
- Regression cases can carry the agent's task, and generated tests can import the app module.
- The DevOps call to action is now "Try the Unsafe Infrastructure Demo".
- The public profile no longer serves the OpenAPI docs and caps the replay stream's delay
  per event at 400 ms.
- The dashboard fits phone screens without zooming out.
- The dashboard shows developer start commands only when served from localhost.
- The browser tests create runs in the page's own session, so they also pass against a
  public deployment.

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

[Unreleased]: https://github.com/thosuperman/ghostreplay/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/thosuperman/ghostreplay/releases/tag/v0.1.0
