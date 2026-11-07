<p align="center">
  <img src="docs/assets/banner.png" alt="GhostReplay Lab — Break AI agents safely. Replay failures. Prove the fix." width="100%" />
</p>

<p align="center">
  <a href="https://github.com/thosuperman/ghost-replay/actions/workflows/ci.yml"><img src="https://github.com/thosuperman/ghost-replay/actions/workflows/ci.yml/badge.svg" alt="CI status" /></a>
  <img src="https://img.shields.io/badge/python-3.12%2B-3776ab" alt="Python 3.12+" />
  <img src="https://img.shields.io/badge/license-MIT-a78bfa" alt="MIT license" />
  <img src="https://img.shields.io/badge/runs-offline-22d3ee" alt="Runs offline" />
</p>

**GhostReplay is an open-source deterministic replay and failure-testing framework for
tool-using AI agents.** It records what an agent actually did and replays it offline
without touching a single service. It injects the failures that happen in production
(timeouts after commit, 429s, stale data, permission errors), flags dangerous behaviour
with safety invariants, and turns the scenario into a pytest regression that proves the
fix.

```
 Record ──▶ Replay offline ──▶ Inject a failure ──▶ Detect unsafe behaviour ──▶ Fix ──▶ Prove (pytest)
```

<p align="center">
  <img src="docs/assets/screenshots/story-duplicate-refund.png" alt="Guided Duplicate Refund demo: incident fails, offline replay is identical, the fixed agent passes" width="100%" />
</p>

## Two applications, one framework

| | **Support Agent Lab** — `apps/support-agent` | **DevOps Agent Lab** — `apps/devops-agent` |
|---|---|---|
| Demo | **Try the Duplicate Refund Demo** | **Try the Unsafe AWS Operation Demo** |
| What goes wrong | The payment gateway commits a $129 refund, the response times out, the agent retries, and the customer is refunded $258. | A stale health view reports three healthy instances as impaired, and the agent terminates the whole fleet during a bad deploy. |
| Detected by | `refund.no_duplicate`, `refund.retries_are_idempotent`, `reply.matches_ledger` | `infra.no_unverified_destructive_action`, `infra.capacity_preserved`, `infra.destructive_requires_approval` |
| The fix | Intent-scoped idempotency key + reconciliation before retry | `SafetyGate`: direct verification, IAM check, blast-radius budget, human approval |
| Backends | simulated payments gateway, orders DB, CRM | simulated AWS-like EC2, CloudWatch, IAM, Lambda, deploys |

Both apps run on their own, with their own port, CLI, scenario and tests. Everything they
share (recording, replay, mocking, faults, diffing, regression, storage, HTTP API) lives in
`packages/ghostreplay`. Everything runs locally and offline, with no API keys, no cloud
account and no paid model.

## Features

- **Deterministic offline replay.** Model calls, tool calls, clock reads, ids and random
  numbers are served from the recording in strict order. Tool handlers are swapped for
  stubs that raise, and sockets are blocked on the replaying thread.
- **Divergence detection.** A changed call, changed arguments, a missing recording or an
  unreached step is reported at the exact step with a field-level diff. Recorded responses
  are never consumed out of order, and replay never guesses a continuation.
- **Counterfactual Failure Lab.** 13 fault kinds can be injected at any recorded step.
  Faults that need a real side effect (*timeout after commit*) run as clearly labelled
  **branch** executions against a fresh simulated environment.
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
git clone https://github.com/thosuperman/ghost-replay.git && cd ghost-replay
./scripts/dev.sh
```

Open **http://127.0.0.1:5173** and click **Try the Duplicate Refund Demo** or **Try the
Unsafe AWS Operation Demo**. Each click records, replays, breaks, fixes and proves the
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
| `live` | executed by the implementation (here, a simulated backend) while recording |
| `recorded` | served from the recording; nothing was executed |
| `injected` | produced or altered by fault injection (the original response is kept on the event) |
| `simulated` | re-executed against a fresh simulated backend in branch mode |

| Execution mode | Meaning |
|---|---|
| `record` | run and record |
| `replay` | deterministic offline replay |
| `counterfactual-replay` | offline replay with faults; **stops at the first divergence** |
| `branch` | replayed prefix, then real re-execution against a fresh simulated environment |

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
- The demo agents use **scripted models**: deterministic policies that stand in for an LLM,
  labelled `scripted` everywhere. Live AI mode is optional and opt-in.
- Branch executions are real executions of the agent code against simulated backends, not
  predictions of what production would have done.
- GhostReplay does not capture hidden model reasoning or state it cannot observe. State
  snapshots come only from explicit `observe` hooks and backend snapshots.

## Integrate your own agent

[`examples/minimal_agent.py`](examples/minimal_agent.py) is a complete integration in
about 100 lines:

```python
lab = Lab("example", [WeatherScenario()])
rec = lab.record("weather", "default")
rpl = lab.replay(rec.id)  # offline, identical
cf = lab.counterfactual(
    rec.id,
    [FaultSpec(id="f", kind="http_500", target=FaultTarget(name="weather.get"))],
    mode="branch",
)
print([i.status for i in cf.invariants])  # ['failed']: the agent hid the error
```

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

One container serves both labs and the dashboard, with health checks at `/healthz` and
`/api/health`. Set `GHOSTREPLAY_PUBLIC=1` on internet-facing deployments to enable rate
limits, concurrency caps, body limits and bounded storage, and to disable live AI mode. A
Render blueprint is included. See [docs/deployment.md](docs/deployment.md).

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

- All demo tools are in-memory simulations. There is no AWS SDK, no payment SDK and no
  real credentials anywhere, and none are needed.
- Secrets are redacted before an event is stored; replay matching uses the same redaction.
- Tools are allowlisted and argument-validated. Unknown tools are recorded as errors and
  not run.
- Trace and case files are Pydantic-validated data and never executed. Errors are rebuilt
  through an allowlist. File access is confined to a base directory.
- Local servers bind to 127.0.0.1. The public profile adds rate limiting and resource
  limits.

Report vulnerabilities as described in [SECURITY.md](SECURITY.md).

## Repository layout

```
.kiro/                 steering, specs and hooks for Kiro
packages/ghostreplay/  the shared framework (+ guarantee tests)
apps/support-agent/    Support Agent Lab (Duplicate Refund)
apps/devops-agent/     DevOps Agent Lab (Unsafe AWS Operation)
apps/dashboard/        React dashboard (+ Playwright e2e)
tests/                 generated regression cases, deployment and example tests
examples/              bring-your-own-agent example
docs/                  architecture, deployment, live AI, Kiro workflow, assets
submission/            hackathon submission materials
```

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, conventions
and how to add a scenario, fault kind or invariant, and
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

MIT. See [LICENSE](LICENSE). Third-party licenses are listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
