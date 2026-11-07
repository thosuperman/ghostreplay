<p align="center">
  <img src="apps/dashboard/public/ghost.svg" width="72" alt="" />
</p>

<h1 align="center">GhostReplay Lab</h1>
<p align="center"><b>Break AI agents safely. Replay failures. Prove the fix.</b></p>

GhostReplay is an open-source **deterministic replay and failure-testing framework for
tool-using AI agents**, plus a visual lab to drive it. It records what an agent actually did,
replays it offline without touching a single service, injects the failures that happen in
production (timeouts after commit, 429s, stale data, permission errors…), flags dangerous
behaviour with safety invariants, and turns the scenario into a pytest regression that proves
the fix.

```
 Record ──▶ Replay offline ──▶ Inject a failure ──▶ Detect unsafe behaviour ──▶ Fix ──▶ Prove (pytest)
```

Two independent applications are built on the same framework:

| App | Scenario | What goes wrong | The fix |
|---|---|---|---|
| **Support Agent Lab** (`apps/support-agent`) | Duplicate Refund | The payment gateway commits a refund, the response times out, the agent retries and refunds the customer twice. | Intent-scoped idempotency key + reconciliation before retry. |
| **DevOps Agent Lab** (`apps/devops-agent`) | Unsafe Infrastructure Action | A stale health view reports healthy instances as impaired; the agent terminates the whole fleet during a bad deploy. | A SafetyGate: independent verification, IAM check, blast-radius budget, human approval. |

Everything runs locally and offline. No API keys, no cloud account, no paid model.

---

## Quick start

Prerequisites: Python ≥ 3.12, [uv](https://docs.astral.sh/uv/), Node ≥ 20 (pnpm via `corepack`).

```bash
git clone https://github.com/thosuperman/ghost-replay.git && cd ghost-replay
./scripts/dev.sh
```

Open **http://127.0.0.1:5173** and click **Try the Duplicate Refund Demo**.

Or start the pieces yourself, each in its own terminal:

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

No browser? Each app tells the whole story in the terminal with real executions:

```bash
uv run support-agent-lab demo
```

```bash
uv run devops-agent-lab demo
```

### Tests

```bash
uv run pytest                      # framework guarantees, both apps, generated regressions, example
```

```bash
uv run ghostreplay test tests/regression --junit reports/junit.xml --json reports/report.json
```

```bash
uv run ruff check . && corepack pnpm --dir apps/dashboard build
```

---

## How it works

### One door between the agent and the world

Agents written for GhostReplay reach the outside world only through `AgentRuntime`:

```python
result = rt.complete(ModelRequest(model="support-sim-1", messages=messages, tools=tools))
refund = rt.call_tool("payments.create_refund", {"payment_id": "pay_3KQ81", "amount_cents": 12900, ...})
key    = rt.new_id("idem");  now = rt.now()
```

Every call goes through a single `Session.interact`, which — depending on the mode — executes
it, serves it from the recording, or injects a fault, and records exactly one event that says
**where its response came from**:

| Event source | Meaning |
|---|---|
| `live` | executed by the real implementation (here: a simulated backend) while recording |
| `recorded` | served from the recording; nothing was executed |
| `injected` | produced or altered by fault injection (original response kept on the event) |
| `simulated` | re-executed against a fresh simulated backend in branch mode |

| Execution mode | Meaning |
|---|---|
| `record` | live run, recorded |
| `replay` | deterministic offline replay — tool handlers replaced by stubs that raise, sockets blocked on the replay thread |
| `counterfactual-replay` | offline replay with faults; **stops at the first divergence** instead of guessing what the agent would do next |
| `branch` | replayed prefix, then real re-execution against a fresh simulated environment (needed for faults like *timeout after commit*) |

Divergence is detected by kind, name and a hash of the redacted request. A mismatch is
recorded as a `divergence` event with a field-level diff; recorded responses are never consumed
out of order.

### Framework modules (`packages/ghostreplay/src/ghostreplay`)

| Module | Responsibility |
|---|---|
| `models/` | versioned schema (`ghostreplay/v1`): `Event`, `Execution`, `FaultSpec`, results |
| `recorder/` | `Recorder` (sequenced events, listeners) and `Redactor` (keys, AWS keys, bearer tokens, `sk-` keys, Luhn-valid cards) |
| `runtime.py` | `AgentRuntime` — model, tools, clock, ids, randomness, step/guard annotations |
| `replay/` | `Session` (record / replay / counterfactual / branch) and the thread-local offline network guard |
| `mocking/` | allowlisted `ToolRegistry`, simulated HTTP service, database and AWS-like cloud, `ModelAdapter` + `ScriptedModel` |
| `mutation/` | fault catalog (13 kinds) and fault application |
| `diff/` | structural trace diff with first-divergence detection and behavioural summary |
| `regression/` | invariants, regression cases, runner, pytest generation, JSON + JUnit reports |
| `lab/` | `Scenario` abstraction, scenario registry (entry points), `Lab` orchestrator, guided demo |
| `storage/` | SQLite store, safe trace import/export |
| `server/` | FastAPI app factory (incl. Server-Sent-Events replay stream) and the shared lab CLI |

Deeper dive: [docs/architecture.md](docs/architecture.md).

### Integrating your own agent

[`examples/minimal_agent.py`](examples/minimal_agent.py) is a complete, runnable integration in
~100 lines: define tools on a simulated backend, a model adapter, an agent that uses
`AgentRuntime`, and a `Scenario`. Then:

```python
lab = Lab("example", [WeatherScenario()])
rec = lab.record("weather", "default")
rpl = lab.replay(rec.id)  # offline, identical
cf = lab.counterfactual(
    rec.id,
    [FaultSpec(id="f", kind="http_500", target=FaultTarget(name="weather.get"))],
    mode="branch",
)
print([i.status for i in cf.invariants])  # ['failed'] — agent hid the error
```

A real LLM plugs in by implementing `ModelAdapter` (`provider`, `model`, `is_live`, `complete`);
recordings then carry `model_is_live: true` and the UI labels them accordingly.

---

## The dashboard

`apps/dashboard` — React + TypeScript (strict) + Vite + Tailwind. It talks to both labs through
the same HTTP API and shows only stored executions.

- **Guided demo** — one click runs the full story with real executions: incident → offline
  replay → root cause → counterfactual → fix → regression proof.
- **Executions** — every run with mode, variant, tool calls, errors, committed destructive side
  effects and failed invariants; record new runs under healthy or incident conditions.
- **Timeline + Inspector** — chronological events with simulated-time bars, source badges,
  prompts, responses, errors, observable state before/after, injected faults, replay verdicts.
- **Replay Studio** — replays over Server-Sent Events; each row appears as the engine emits it,
  and the pacing slider slows the engine itself.
- **Failure Lab** — pick a recorded step and a fault (or a preset), choose the agent variant and
  execution mode, see exactly which field changed and whether branch execution was needed.
- **Diff** — side-by-side aligned interactions, first divergence, field-level changes,
  behavioural table.
- **Regression** — run a case against every agent variant, PASS/FAIL per invariant with
  explanations, export the pytest module and case file.

## HTTP API (per lab)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/info`, `/api/scenarios`, `/api/faults` | lab metadata, scenarios (variants, conditions, presets, invariants, tools), fault catalog |
| GET | `/api/executions`, `/api/executions/{id}` | summaries, full execution |
| POST | `/api/runs/record` | record a run |
| POST | `/api/runs/replay` | offline replay + diff vs recording |
| GET | `/api/executions/{id}/replay/stream` | SSE replay stream (`delay_ms` paces the engine) |
| POST | `/api/runs/counterfactual` | inject faults/preset; `mode` = auto, replay, branch |
| GET | `/api/diff?a=&b=` | structural diff |
| POST | `/api/regression/run`, `/api/regression/export` | run cases for variants, generate pytest |
| POST | `/api/demo/prepare` | run the full guided story |

Interactive docs: http://127.0.0.1:8101/docs and http://127.0.0.1:8102/docs.

## Regression tests

`tests/regression/` contains committed cases generated by `export-cases`:

```bash
uv run support-agent-lab export-cases --out tests/regression
```

Each case is a JSON file (scenario id, variant, conditions, faults, embedded reference
recording, expectation) plus a 15-line pytest module. Vulnerable variants are expected to
**FAIL** (the detector must catch the bug); fixed variants must **PASS**. Case files are
validated data; scenarios are resolved by id from installed entry points — nothing in a case is
executed.

## Security and safety guarantees

- All demo tools are in-memory simulations; no AWS SDK, payment SDK or real credentials anywhere.
- Offline replay never invokes tool handlers or model adapters and blocks socket access from the
  replaying thread (other server threads are unaffected).
- Secrets are redacted before an event is stored; replay matching uses the same redaction.
- Tools are allowlisted and argument-validated; unknown tools are recorded as errors, not run.
- Trace and case files are Pydantic-validated data; errors are rebuilt via an allowlist.
- File import/export is confined to a base directory; servers bind to 127.0.0.1.

Each guarantee has a test in `packages/ghostreplay/tests`.

## Honest limitations

- Deterministic replay covers interactions that go through `AgentRuntime`. Code that bypasses it
  is not replayed (and is blocked during offline replay).
- The demo agents use **scripted models** — deterministic policies standing in for an LLM so
  the demo is free and reproducible. They are labelled `scripted` everywhere and never presented
  as live model output.
- Branch executions are real executions of the agent code against simulated backends, not
  predictions of what production would have done.
- GhostReplay does not capture hidden model reasoning or state it cannot observe; state
  snapshots come only from explicit `observe` hooks and backend snapshots.

## Repository layout

```
.kiro/                 steering, specs (requirements/design/tasks) and agent hooks
packages/ghostreplay/  the shared framework + its guarantee tests
apps/support-agent/    Support Agent Lab (Duplicate Refund)
apps/devops-agent/     DevOps Agent Lab (Unsafe Infrastructure Action)
apps/dashboard/        React dashboard
tests/regression/      generated regression cases
examples/              bring-your-own-agent example
docs/                  architecture and demo script
scripts/dev.sh         start everything
```

## Kiro artifacts

The `.kiro/` directory holds the project's steering documents (product, structure, tech,
conventions, security, scope), a spec per component (`core-framework`, `support-agent-lab`,
`devops-agent-lab`, `dashboard`, each with requirements → design → tasks) and agent hooks that
re-run the framework guarantees, re-check scenario outcomes, keep dashboard types in sync with the
Python schema, and review fixtures for secrets. Open the repository in Kiro to use them.

## License

MIT — see [LICENSE](LICENSE).
