<p align="center">
  <img src="docs/assets/banner.png" alt="GhostReplay Lab — Break AI agents safely. Replay failures. Prove the fix." width="100%" />
</p>

<p align="center">
  <a href="https://github.com/thosuperman/ghostreplay/actions/workflows/ci.yml"><img src="https://github.com/thosuperman/ghostreplay/actions/workflows/ci.yml/badge.svg" alt="CI status" /></a>
  <img src="https://img.shields.io/badge/python-3.12%2B-3776ab" alt="Python 3.12+" />
  <img src="https://img.shields.io/badge/license-MIT-a78bfa" alt="MIT license" />
  <img src="https://img.shields.io/badge/runs-offline-22d3ee" alt="Runs offline" />
</p>

<p align="center">
  <b>Live demo: <a href="https://ghostreplay.hayaix.tech">ghostreplay.hayaix.tech</a></b>
  — no sign-up, no API keys.<br/>
  <a href="https://ghostreplay.hayaix.tech/demo/refund">Watch an AI agent fail</a> ·
  <a href="https://ghostreplay.hayaix.tech/demo/devops">DevOps demo</a> ·
  <a href="https://ghostreplay.hayaix.tech/connect">Connect your own agent</a>
</p>

**Catch the bug. Replay the failure. Prove the fix.** GhostReplay is a flight recorder and
crash-test lab for AI agents.

Your AI agent made a mistake. Maybe it refunded a customer twice, or deleted healthy
servers. GhostReplay helps you deal with it:

- It records exactly what the agent did.
- It replays the incident offline without repeating the side effects.
- It injects the failures that happen in production on purpose: timeouts after commit, 429s,
  stale data, permission errors.
- It flags dangerous behaviour with safety invariants.
- It turns the incident into a pytest regression that proves your fix.

It's an engineering tool for agent reliability, not a log viewer: logs tell you what happened
once, and GhostReplay lets you run it again.

```
 Record ──▶ Replay offline ──▶ Inject a failure ──▶ Detect unsafe behaviour ──▶ Fix ──▶ Prove (pytest)
```

<p align="center">
  <img src="docs/assets/screenshots/story-duplicate-refund.png" alt="Guided Duplicate Refund demo: incident fails, offline replay is identical, the fixed agent passes" width="100%" />
</p>

## Two applications, one framework

| | **Support Agent Lab** — `apps/support-agent` | **DevOps Agent Lab** — `apps/devops-agent` |
|---|---|---|
| Demo | **Try the Duplicate Refund Demo** | **Try the Unsafe Infrastructure Demo** |
| What goes wrong | Claude asks for one $129 refund. The local refund service commits it in SQLite but its response times out (injected delay); the app's retry policy re-sends the request, and the ledger shows $258 refunded. | Monitoring serves a stale view marking three healthy instances impaired (injected). In our live runs, Claude refused runbook v1's instruction to terminate them; with that decision injected, workflow v1 really shuts the instance services down. |
| Detected by | `refund.no_duplicate`, `refund.retries_are_idempotent`, `reply.matches_ledger` | `infra.no_unverified_destructive_action`, `infra.capacity_preserved`, `infra.destructive_requires_approval` |
| The fix | Intent-scoped idempotency key + reconciliation before retry | Runbook v2 + `SafetyGate` in code: direct probes, IAM check, blast-radius budget, human approval |
| Backends (real, on 127.0.0.1) | SQLite (orders, payments, refunds, refund attempts, audit events) + an HTTP refund service | Three HTTP instance services with `/health` + an HTTP controller with an allowlist of 9 operations |

Both apps run on their own, with their own port, CLI, scenario and tests. Everything they
share (recording, replay, mocking, faults, diffing, regression, storage, HTTP API, the local
service toolkit) lives in `packages/ghostreplay`.

### Real execution, honestly labelled

The guided demos re-execute **genuine Claude runs** (recorded live, shipped as read-only
captures): Claude's tool decisions are served from the capture, while every HTTP request, SQL
write, health check and termination runs again for real on the server. Developer-mode
recordings use a labelled scripted model; live mode calls Claude when you set a key. Every
execution is labelled (live LLM execution, scripted demo, genuine capture, controlled fault
injection, strict offline replay, re-execution, corrected re-execution). See
[docs/real-execution.md](docs/real-execution.md) for exactly what is real, what is injected,
and what our live runs taught us (Claude invented its own idempotency key, and refused an
unsafe runbook).

## Features

- **Deterministic offline replay.** Model calls, tool calls, clock reads, ids and random
  numbers are served from the recording in strict order. Tool handlers are swapped for
  stubs that raise, and sockets are blocked on the replaying thread.
- **Divergence detection.** A changed call, changed arguments, a missing recording or an
  unreached step is reported at the exact step with a field-level diff. Recorded responses
  are never consumed out of order, and replay never guesses a continuation.
- **Counterfactual Failure Lab.** 13 fault kinds can be injected at any recorded step.
  Faults that need a real side effect (*timeout after commit*) run as clearly labelled
  **branch** executions against a fresh environment.
- **Safety invariants** with passed / failed / inconclusive results, evidence events and
  explanations.
- **Regression generation.** Any scenario becomes a JSON case plus a pytest module, with
  JUnit XML and JSON reports for CI.
- **Structural diff** of any two executions: aligned interactions, first divergence, and a
  behavioural summary.
- **Dashboard.** Guided demos, execution explorer, timeline and inspector, live replay
  streaming, Failure Lab, diff and regression views.
- **Optional live AI mode.** Drive the agents with a real LLM (Anthropic), record it, then
  replay it offline for free. See [docs/live-ai.md](docs/live-ai.md).

## Quick start

Prerequisites: Python ≥ 3.12, [uv](https://docs.astral.sh/uv/), Node ≥ 20 (pnpm via `corepack`).

```bash
git clone https://github.com/thosuperman/ghostreplay.git && cd ghostreplay
./scripts/dev.sh
```

Open **http://127.0.0.1:5173** and click **Try the Duplicate Refund Demo** or **Try the
Unsafe Infrastructure Demo**. Each click records, replays, breaks, fixes and proves the
scenario with real executions.

With Docker (both labs and the dashboard on one port):

```bash
docker compose up --build
```

Then open http://127.0.0.1:8100.

No browser? Each app tells the whole story in the terminal and exits non-zero if any step
does not produce its expected outcome:

```bash
uv run support-agent-lab demo
```

```bash
uv run devops-agent-lab demo
```

<details>
<summary>Start the pieces separately</summary>

```bash
uv sync
```

```bash
uv run support-agent-lab serve      # API on :8101
```

```bash
uv run devops-agent-lab serve       # API on :8102
```

```bash
corepack pnpm install && corepack pnpm --dir apps/dashboard dev   # dashboard on :5173
```

</details>

## Screens

| | |
|---|---|
| ![Execution timeline and inspector](docs/assets/screenshots/timeline.png) | ![Failure Lab injecting timeout after commit](docs/assets/screenshots/failure-lab.png) |
| **Timeline + inspector**: every event with its source, request, response and state | **Failure Lab**: pick a step and a fault, run it against either agent variant |
| ![Side-by-side diff](docs/assets/screenshots/diff.png) | ![Regression results](docs/assets/screenshots/regression.png) |
| **Diff**: first divergence and field-level changes | **Regression**: FAIL on the vulnerable agent, PASS on the fixed one |

## How it works

<p align="center"><img src="docs/assets/architecture.png" alt="Architecture diagram" width="100%" /></p>

Agents written for GhostReplay reach the outside world only through `AgentRuntime`:

```python
result = rt.complete(ModelRequest(model=rt.model_name, messages=messages, tools=tools))
refund = rt.call_tool("payments.create_refund", {"payment_id": "pay_3KQ81", "amount_cents": 12900})
key = rt.new_id("idem")
now = rt.now()
```

Every call goes through a single `Session.interact`. Depending on the mode, it executes the
call, serves it from the recording, or injects a fault, and records exactly one event that
says **where its response came from**:

| Event source | Meaning |
|---|---|
| `live` | executed by the implementation (here, real local services) while recording |
| `recorded` | served from the recording; nothing was executed |
| `injected` | produced or altered by fault injection (the original response is kept on the event) |
| `simulated` | re-executed against fresh local services in branch mode (the name is historical: the work is real) |

| Execution mode | Meaning |
|---|---|
| `record` | run and record |
| `replay` | deterministic offline replay |
| `counterfactual-replay` | offline replay with faults; **stops at the first divergence** |
| `branch` | replayed prefix, then real re-execution against a fresh environment |

The [record/replay sequence diagram](docs/assets/record-replay-sequence.png),
[docs/architecture.md](docs/architecture.md) and [docs/diagrams.md](docs/diagrams.md) go deeper.

### Replay guarantees

Each guarantee below is covered by tests in `packages/ghostreplay/tests` and `apps/*/tests`.

- A replay of an unmodified recording is structurally identical to it: same kinds, names,
  requests, responses, errors, timestamps, durations and state.
- No tool handler, model adapter or socket is used during offline replay. An attempt is
  recorded and fails the run.
- Interactions are matched in strict order by kind, name and a hash of the redacted request.
  An unexpected, missing, reordered or changed call produces a divergence; it is never
  silently skipped.
- Recordings that are out of order, have duplicate ids, are from another schema version, or
  are otherwise malformed are rejected on load with a specific `TraceFormatError`.
- Strict counterfactual replay never invents behaviour after a divergence. Continuations
  only happen in labelled branch executions.

### Limitations

- Only interactions that go through `AgentRuntime` are replayed. Code that bypasses it is
  not replayed, and its network access is blocked during offline replay.
- The public guided demos re-execute **recorded** Claude decisions; they do not call the model
  again, and a re-execution that leaves the recorded path stops instead of guessing. Live
  model calls need `GHOSTREPLAY_LIVE=1` and a key. Developer-mode recordings and tests use a
  labelled scripted model.
- Branch executions are real executions of the agent code against fresh local services (a
  test SQLite database, local HTTP services), not predictions of what production would do.
- Some DevOps lab data (log lines, deploy history, IAM grants) are seeded fixtures.
- GhostReplay does not capture hidden model reasoning or state it cannot observe. State
  snapshots come only from explicit `observe` hooks and backend snapshots.

## Use it in your own agent (Python SDK)

```bash
pip install "ghostreplay @ git+https://github.com/thosuperman/ghostreplay@main#subdirectory=packages/ghostreplay"
```

```python
from ghostreplay import GhostReplay

ghost = GhostReplay("my-agent", storage="./ghostreplay-data")
ORDERS = {"ORD-123": {"id": "ORD-123", "total_cents": 12900}}  # stands in for your order API


@ghost.tool("orders.lookup")
def lookup_order(order_id: str) -> dict:
    return ORDERS[order_id]  # your real code runs here when recording


@ghost.agent()
def handle(task: dict) -> dict:
    order = lookup_order(task["order_id"])  # routed through GhostReplay
    return {"status": "success", "message": f"Found {order['id']}"}


run = ghost.record({"order_id": "ORD-123"})  # executes and records
again = ghost.replay(run)  # offline: lookup_order is NOT called
print(again.status, again.live_calls, ghost.diff(run, again).identical)  # completed 0 True
```

From there, three more steps:

- Inject failures: `ghost.record(..., faults=[fault("timeout_after_commit", "payments.charge")])`.
- Compare agents with `ghost.diff(...)`.
- Write regression tests with `ghost.write_regression_test(...)`; they run offline in CI.

GhostReplay records only the calls you route through `@ghost.tool` and `@ghost.model`. There
is no automatic instrumentation.

| Where to start | What it is |
|---|---|
| [docs/sdk/quickstart.md](docs/sdk/quickstart.md) | Five-minute quickstart. All 13 SDK pages have tested examples. |
| [docs/sdk/examples/quickstart.py](docs/sdk/examples/quickstart.py) | Record → fault → replay → fix → regression in about 90 lines |
| [examples/invoice-agent](examples/invoice-agent/README.md) | A separate Invoice Processing Agent built only on the public SDK |
| `ghostreplay inspect / diff / replay --app / export / test --import` | The developer CLI ([docs/sdk/trace-import-export.md](docs/sdk/trace-import-export.md)) |
| [docs/sdk/ci-integration.md](docs/sdk/ci-integration.md) | A GitHub Actions workflow with real sample output |

The lower-level engine API (`Lab`, `Scenario`, `AgentRuntime`) is what the two bundled labs use.
[`examples/minimal_agent.py`](examples/minimal_agent.py) shows it in about 100 lines.

## Testing

```bash
uv run pytest                                  # framework, both apps, regressions, deployment
```

```bash
uv run ruff check . && uv run ruff format --check .
```

```bash
corepack pnpm --dir apps/dashboard typecheck && corepack pnpm --dir apps/dashboard build
```

```bash
corepack pnpm --dir apps/dashboard e2e         # Playwright, against the real gateway
```

```bash
uv run ghostreplay test tests/regression --junit reports/junit.xml --json reports/report.json
```

The SDK and the external example, in a clean virtual environment (what the CI `sdk` job does):

```bash
uv build packages/ghostreplay --out-dir dist
python -m venv /tmp/gr && /tmp/gr/bin/pip install dist/ghostreplay-*.whl -e "examples/invoice-agent[test]"
cd examples/invoice-agent && /tmp/gr/bin/invoice-agent-demo && /tmp/gr/bin/pytest
```

Regenerate the committed regression cases:

```bash
uv run support-agent-lab export-cases --out tests/regression
```

```bash
uv run devops-agent-lab export-cases --out tests/regression
```

Vulnerable variants are expected to **FAIL**, which shows the detector catches the bug;
fixed variants must **PASS**. CI runs all of the above, plus both terminal demos and a
container smoke test ([.github/workflows/ci.yml](.github/workflows/ci.yml)).

## Deployment

The public demo at <https://ghostreplay.hayaix.tech> runs on a dedicated AWS Lightsail
instance (2 GB, `us-east-1`). Caddy handles HTTPS and serves the static dashboard, and each
lab runs as its own sandboxed systemd service with its own SQLite file. The labs have no
network access beyond loopback. Every visitor gets a private, expiring session. Scripts are
in [`deploy/lightsail/`](deploy/lightsail/README.md); provisioning, security, costs,
backups and the live verification results are in
[docs/deployment/AWS_LIGHTSAIL.md](docs/deployment/AWS_LIGHTSAIL.md).

For other hosts, one container serves both labs and the dashboard (`Dockerfile`,
`compose.yaml`, Render blueprint); see [docs/deployment.md](docs/deployment.md). Set
`GHOSTREPLAY_PUBLIC=1` on any internet-facing deployment. That enables rate limits,
concurrency caps, body limits, bounded storage and per-visitor session isolation, and
turns off live AI mode.

## Kiro integration

The [`.kiro/`](.kiro) directory is set up for spec-driven development in
[Kiro](https://kiro.dev):

- **Steering**: product, tech, structure, architecture, security, conventions (by file
  pattern), and competition (manual).
- **Specs**: `replay-engine`, `failure-injection`, `support-agent-lab`, `devops-agent-lab`
  and `dashboard`. Each has requirements, design and tasks, with the tests and verification
  commands that back them.
- **Hooks**: run the framework tests, scenario regressions, dashboard type check and secret
  scan when matching files are saved, and lint when the agent stops.

The specs describe the implementation as it exists and were written after it. Tasks marked
done were completed before the repository was opened in Kiro. Open tasks are real next
steps meant to be built with Kiro. [docs/kiro-workflow.md](docs/kiro-workflow.md) and
[docs/kiro-demo-prompts.md](docs/kiro-demo-prompts.md) describe that workflow.

## Security

- Demo tools talk only to disposable services on 127.0.0.1 (a test SQLite database, a local
  refund service, a local instance lab). There is no AWS SDK, no payment SDK and no real
  credentials on the server; on the server, systemd blocks all non-loopback network access
  for the labs. The optional live AI key is used only locally to record captures.
- Secrets are redacted before an event is stored; replay matching uses the same redaction.
- Tools are allowlisted and argument-validated. Unknown tools are recorded as errors and
  not run.
- Trace and case files are Pydantic-validated data and never executed. Errors are rebuilt
  through an allowlist. File access is confined to a base directory.
- Local servers bind to 127.0.0.1. The public profile adds rate limiting, resource limits
  and per-visitor session isolation. The production services cannot reach the network,
  including the cloud metadata endpoint (see
  [docs/deployment/SECURITY.md](docs/deployment/SECURITY.md)).

Report vulnerabilities as described in [SECURITY.md](SECURITY.md).

## Repository layout

```
.kiro/                 steering, specs and hooks for Kiro
packages/ghostreplay/  the shared framework (+ guarantee tests)
apps/support-agent/    Support Agent Lab (Duplicate Refund)
apps/devops-agent/     DevOps Agent Lab (Unsafe Infrastructure)
apps/dashboard/        React dashboard: guided demos, developer tools (+ Playwright e2e)
examples/invoice-agent/  external app built only on the public SDK
deploy/lightsail/      production deployment: provisioning, Caddy, systemd, backups
tests/                 generated regression cases, deployment and example tests
examples/              bring-your-own-agent example
docs/                  SDK docs (docs/sdk/), deployment (docs/deployment/), architecture, live AI, Kiro, assets
submission/            hackathon submission materials
```

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, conventions
and how to add a scenario, fault kind or invariant, and
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

MIT. See [LICENSE](LICENSE). Third-party licenses are listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
