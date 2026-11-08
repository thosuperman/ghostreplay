# What is real in GhostReplay Lab

GhostReplay is a tool for debugging real agents, so the demos are built from real parts:

- a live model choosing tools;
- real HTTP services;
- real SQLite transactions;
- real health checks.

Some things are deliberately simulated or injected, and every execution says which. This page lists exactly what is what.

## At a glance

| Component | Real? | Where |
|---|---|---|
| Model decisions in the guided demos | **Real.** Genuine Claude (`claude-opus-5-5`) tool-calling runs, recorded live and shipped as read-only captures. The public server makes no paid model calls. | `apps/*/src/*/captures/*.trace.json` |
| Model decisions in developer-mode recordings and in tests | **Scripted.** A deterministic policy, labelled *Scripted demo* | `model.py` in each lab |
| Live model calls | Real when `GHOSTREPLAY_LIVE=1` and `ANTHROPIC_API_KEY` are set (local or self-hosted; forced off on the public server) | `ghostreplay/llm/anthropic_adapter.py` |
| Support lab database | **Real SQLite** with customers, orders, order items, payments, refunds, refund attempts, audit events and an outbox. Fresh per run, fictional test data. | `apps/support-agent/src/support_agent/environment.py` |
| Refund service | **Real HTTP server** on 127.0.0.1. Validates requests, commits in SQL transactions, honours `Idempotency-Key`, keeps a ledger of every attempt. | same file |
| DevOps instances | **Three real HTTP services** with `/health`. Terminating one really shuts it down. | `apps/devops-agent/src/devops_agent/lab.py` |
| DevOps controller | **Real HTTP API** with an allowlist of nine operations. Health probes really call the instances. | same file |
| DevOps logs, deploy history, IAM grants, diagnostics payload | **Seeded lab data**, served by the controller's control-plane model | `environment.py`, `ghostreplay/mocking/aws.py` |
| Invoice app | **Real SQLite** (vendors, invoices, payments) and a **real HTTP payment service**. Extraction calls Claude when `INVOICE_AGENT_LIVE=1`, otherwise a labelled deterministic parser. | `examples/invoice-agent/invoice_agent/` |
| Network reach | Loopback only. Nothing contacts a payment provider, AWS, Docker or any external host. On the server, systemd blocks all non-loopback traffic for the labs. | `docs/deployment/SECURITY.md` |

## How the model chooses tools

The agent loop sends Claude a system prompt, the conversation so far, and the JSON Schema of each tool the app exposes. Claude returns `tool_use` blocks. The application executes each requested call through GhostReplay (`rt.call_tool`), and the tool performs real HTTP and SQL work. The result goes back to Claude, and the loop repeats until Claude writes a final reply.

GhostReplay records every model request and response, every tool call with its arguments, result or error, and the state observed before and after destructive calls.

Two decisions belong to the application, not to the model, and the demos label them that way:

- **Retries.** In the support agent, retrying a timed-out refund is the application's retry policy. Claude asked for one refund.
- **Idempotency keys.** The model is never asked for an idempotency key. The buggy version's refund client has none; the fixed version derives a stable key itself.

Claude's private reasoning is not captured. The API returns thinking blocks with empty text, and only an opaque signature is stored, which the API needs if the conversation continues.

## The controlled faults

Each fault is labelled in the trace and in the UI:

| Fault | What is injected | What is still real |
|---|---|---|
| Refund timeout after commit (`payment_gateway=timeout_after_commit`) | The refund service holds its HTTP response for 2.7 s after committing; the client's socket timeout is 1.2 s | The HTTP request, the SQL commit, the client timeout, the retry and the second committed refund |
| Stale monitoring (`health_checks=stale`) | The controller's monitoring view returns a cached snapshot marking every instance `impaired` | The instances, which are healthy, the direct probes and any termination |
| Injected model decision (DevOps) | The model's second response is replaced with "terminate the impaired instances" (`incorrect_output` fault on the model call) | Everything after it: the termination really shuts the instance services down, or the v2 safety gate blocks it |
| `timeout_after_commit` on `payments.pay` (invoice app) | GhostReplay runs the real HTTP payment, then reports a timeout to the agent | The payment request and its SQL commit, the retry and the duplicate payment |

## Two findings from the live runs

These came from real Claude runs, and they're why the scenarios look the way they do:

1. **Claude invented its own idempotency key.** In the first live support run, the tool schema exposed an optional `idempotency_key` parameter, and Claude passed one (`ORD-1042-AUR-EB-01-damaged`). The service deduplicated the retry, so no duplicate happened. The buggy version now represents what it is meant to represent: an application whose refund client has no idempotency support, with the model never asked for a key. The duplicate comes from the application's retry policy.
2. **Claude refused the unsafe runbook.** Workflow v1 tells the model that monitoring is the source of truth and to terminate impaired instances. Claude read the stale view and the logs, said that terminating them would take the service fully offline, and terminated nothing. This happened in all three independent captures. The DevOps demo shows that decision as recorded. It then tests the workflow itself with a labelled injected decision, because a workflow's safety shouldn't depend on the model having a good day.

## Strict replay has no side effects

`lab.replay(id)` or `ghost.replay(run)` re-runs the agent code against the recording:

- Every model call and tool call is served from it.
- No world is built. The labs override `build_offline_environment`, so no database is created and no service is started.
- Tool handlers are stubs that raise if called.
- Sockets are blocked on the replaying thread.

`tests/test_real_execution.py` asserts that a replay makes zero calls, constructs no world and starts no service.

Re-execution (`lab.reexecute(id)`, `POST /api/runs/reexecute`) is different and labelled differently. Tools, HTTP and SQL run again for real against fresh services. Model calls are served from the recording for as long as the run follows it. If the run leaves the recorded path, it stops with "needs a new model decision" rather than inventing one.

## Reproduce the duplicate refund

With the scripted model (no key needed):

```bash
uv run support-agent-lab run --variant vulnerable --incident
uv run support-agent-lab run --variant fixed --incident
```

The same with the shipped genuine Claude capture, re-executed (no key needed):

```bash
uv run python -c "
from ghostreplay.storage import SqliteStore
from ghostreplay.storage.library import load_library
from support_agent.cli import build_lab
store = SqliteStore(':memory:'); lab = build_lab(store)
buggy = next(i for i in load_library(store, lab.library_dir) if store.get(i).variant == 'vulnerable')
run = lab.reexecute(buggy)
print(run.provenance.label)
print([(r['id'], r['amount_cents']) for r in run.final_state['payments']['refunds']])
print(run.final_state['refund_attempts'])"
```

With a live model (paid API calls):

```bash
set -a; . ./.env; set +a          # ANTHROPIC_API_KEY=... in a git-ignored .env
GHOSTREPLAY_LIVE=1 uv run support-agent-lab run --variant vulnerable --incident --live
```

## Tests

| Command | What it proves | Needs a key |
|---|---|---|
| `uv run pytest` | Real HTTP and SQL, timeout-after-commit, duplicates and idempotency, replay with no side effects, divergence, DevOps lab isolation and termination, the capture library, re-execution, the SDK, docs examples | No |
| `GHOSTREPLAY_LIVE_TESTS=1 GHOSTREPLAY_LIVE=1 uv run pytest tests/live -o addopts=""` | A live model chooses the tools; its decisions cause real HTTP and SQL side effects; replay makes no provider call | Yes |
| `cd examples/invoice-agent && INVOICE_AGENT_LIVE=1 pytest tests/test_live_extraction.py` | Real LLM extraction through the SDK, then an offline replay without calling it | Yes |

The automated suite uses the scripted model or the recorded captures. It verifies GhostReplay's behaviour, not the provider. Only the two live tests above verify the provider integration, and they were run on 2026-11-08.

## Re-recording the captures

```bash
set -a; . ./.env; set +a
GHOSTREPLAY_LIVE=1 uv run python scripts/capture_live.py
```

This records six runs (support buggy and fixed; DevOps v1, v2, and v1 and v2 with the injected decision) and saves them whatever the model decides. Re-execution and the tests depend on the production client timeout (1200 ms), so record with the default.

## Fully offline

Nothing requires a key:

- The guided demos re-execute the shipped captures.
- Developer-mode recordings use the scripted model.
- The SDK, tests and examples run without network access, apart from the loopback services they start.
