# GhostReplay Lab

**Catch the bug. Replay the failure. Prove the fix.**

A flight recorder and crash-test lab for AI agents. When an agent makes an expensive mistake,
GhostReplay records what happened, reproduces it without repeating the side effects, and
proves that the corrected agent no longer makes it.

- Live demo: https://ghostreplay.hayaix.tech
- Video: https://youtu.be/J2ttyDNMfDY
- Source code (MIT): https://github.com/thosuperman/ghostreplay

---

## Inspiration

A customer writes in: the earbuds arrived broken, can I get a refund? An AI support agent
looks up the order, checks eligibility and calls the payment gateway to refund $129. The
gateway commits the refund, but the response times out. The agent does what any reasonable
retry loop does and tries again. The customer gets $258 back and is told $129.

Nothing in that story is exotic. Timeouts after commit, rate limits, stale reads and
permission errors happen in production every day. What is new is that an LLM is now deciding
what to do next, and the tools it calls move money and delete servers.

When that goes wrong, teams usually have a log and a lot of guesswork. You cannot safely
re-run the incident (it would refund the customer a third time), you cannot easily make the
gateway time out at exactly the right moment, and when you change the code you have no test
that proves this exact failure can never happen again.

We wanted the tool we wished we had: a flight recorder and a crash-test lab for tool-using
agents.

## What it does

GhostReplay Lab is an open-source framework plus a visual lab that runs one loop end to end:

```
Record ──▶ Replay offline ──▶ Inject a failure ──▶ Detect unsafe behaviour ──▶ Fix ──▶ Prove (pytest)
```

1. **Record.** Every model call, tool call, clock read and generated id is captured in order
   and redacted before it is stored.
2. **Replay offline.** The agent's real code runs again, but every response comes from the
   recording. Tool handlers are replaced by stubs that raise if called, and network sockets
   are blocked on the replaying thread. The replay is checked to be identical to the recording.
3. **Inject a failure.** Pick any recorded step and break it with one of 15 fault kinds:
   tool timeout, timeout after commit, HTTP 429, HTTP 500, authentication failure, permission
   denied, missing field, null value, duplicate response, reordered response, clock skew,
   stale data, incorrect output, delayed operation and partial success.
4. **Detect.** Safety invariants check the run: no duplicate refund, retries are idempotent,
   the reply matches the ledger, no destructive action on unverified evidence, capacity is
   preserved, destructive actions require approval.
5. **Fix.** Change the harness, not the model, and run the same failure again.
6. **Prove.** Export the scenario as a pytest regression case that FAILS on the vulnerable
   agent and PASSES on the fixed one, with JUnit XML and JSON reports for CI.

Two applications are built on the same framework:

| | Support Agent Lab | DevOps Agent Lab |
|---|---|---|
| Scenario | Duplicate Refund | Unsafe Infrastructure Action |
| What goes wrong | The payment gateway commits a $129 refund, the response times out, the agent retries without an idempotency key: **$258 refunded**, customer told $129. | After a bad deploy, a stale health view reports healthy instances as impaired; the agent **terminates all 3 healthy instances** of `checkout-api`, turning a bad deploy into an outage. |
| Invariants that fail | `refund.no_duplicate`, `refund.retries_are_idempotent`, `reply.matches_ledger` | `infra.no_unverified_destructive_action`, `infra.capacity_preserved` (0 left running, minimum 2), `infra.destructive_requires_approval` |
| The fix | Intent-scoped idempotency key (`refund:<ticket>:<payment>:<amount>`) and reconciliation before any retry | A SafetyGate: fresh direct verification of each target, IAM check, blast-radius budget, mandatory human approval; the agent proposes a rollback instead |
| After the fix | 1 refund, reply matches the ledger | 3 instances running, 1 change proposal filed |

Each lab has a **six-step guided demo** for first-time visitors:
[/demo/refund](https://ghostreplay.hayaix.tech/demo/refund) ("The Double Refund Incident") and
[/demo/devops](https://ghostreplay.hayaix.tech/demo/devops) ("The AI Agent That Almost Deleted
Healthy Servers"). It goes Meet the agent → Watch the failure → Investigate → Replay safely →
Test the fix → Verify. Each step drives a real execution on the server:

- recording the buggy agent;
- a strict offline replay, which reports how many responses were reused and that 0 tools ran;
- a fresh run of the fixed agent under the same failure;
- a structural diff;
- the regression tests.

Every number and every plain-English line is derived from those executions. A Guided /
Developer switch keeps the full developer dashboard one click away, and each guided step links
to the matching developer view. The same story also runs in a terminal with
`uv run support-agent-lab demo` and `uv run devops-agent-lab demo`, and CI fails if any step
produces an unexpected outcome.

**What is real.**

- **Model decisions.** In the guided demos they come from genuine Claude (`claude-opus-5-5`)
  tool-calling runs, recorded live and shipped as read-only captures.
- **Execution.** Each step re-executes a capture now, for real:
  - the support agent talks to a SQLite database and a local HTTP refund service with
    transactional commits and idempotency keys;
  - the DevOps agent talks to three HTTP instance services and an allowlisted controller,
    where health probes really call the instances and termination really shuts them down.
- **Faults are injected and labelled:** the refund service's delayed response after
  commit, the stale monitoring view, and a replaced model decision.
- **What stays offline.** The public server makes no paid model calls. Live mode
  (`GHOSTREPLAY_LIVE=1`) records new runs locally, and developer-mode recordings use a
  labelled scripted model.

Two findings came from the live runs:

- Claude passed its own idempotency key when the tool schema allowed it, so the buggy app
  now never offers one.
- Claude refused the unsafe runbook, so the DevOps demo shows that decision and then tests
  the workflow with an injected one.

See `docs/real-execution.md`.

## How it works

### One door between the agent and the world

GhostReplay does not monkey-patch HTTP clients or SDKs. An agent reaches the outside world
only through `AgentRuntime`:

```python
result = rt.complete(ModelRequest(model="support-sim-1", messages=messages, tools=tools))
refund = rt.call_tool("payments.create_refund", {"payment_id": "pay_3KQ81", "amount_cents": 12900})
key = rt.new_id("idem")
now = rt.now()
```

Every call goes through a single `Session.interact`, which, depending on the mode, executes
it, serves it from the recording, or injects a fault, and records exactly one event that
says where its response came from: `live`, `recorded`, `injected` or `simulated`.

### Four execution modes

| Mode | What happens |
|---|---|
| `record` | The agent runs against its world (in the labs, real local services) and every interaction is recorded. |
| `replay` | Deterministic, offline. Responses come from the recording; handlers are stubs; sockets are blocked. |
| `counterfactual-replay` | Offline replay with faults injected. It **stops at the first divergence** instead of guessing what the agent would have done next. |
| `branch` | The prefix is replayed and verified, then the agent really re-executes against a fresh environment. Needed for faults that require a real side effect, such as a timeout after commit. Labelled as a branch everywhere. |

Divergence is detected by interaction kind, name and a hash of the redacted request. When the
agent asks for something different from the recording, GhostReplay records a `divergence`
event with a field-level diff. Recorded responses are never consumed out of order.

### The rest of the framework

- **Recorder and redactor:** sequenced events; keys, tokens, `sk-` keys, AWS keys and
  Luhn-valid card numbers are scrubbed before anything is stored.
- **Offline guard:** a thread-local socket guard, so a lab server keeps serving HTTP on other
  threads while a replay is blocked from the network.
- **Mutation:** the 15-kind fault catalog, each with a strategy (`error`, `transform`,
  `execute_then_error`, `delay`) and a flag saying whether it needs branch execution. The
  original response is kept on the event so the UI can show exactly what changed.
- **Diff:** aligns two executions, finds the first divergence, and summarises behaviour:
  tool counts, committed destructive side effects, invariant outcomes, final state.
- **Regression:** invariants return `passed`, `failed` or `inconclusive` (never silently
  passed when the final state is unknown). Cases are pure, validated data; pytest modules and
  JUnit/JSON reports are generated from them.
- **Storage and server:** SQLite per lab, a FastAPI app with a Server-Sent Events replay
  stream, and a gateway (`ghostreplay serve`) that mounts every installed lab and the
  dashboard on one port.

### Dashboard

React, TypeScript (strict), Vite and Tailwind CSS. Views: Guided demo, Execution Explorer,
Timeline and Inspector, Replay Studio (the replay engine streams each event as it records
it), Counterfactual Failure Lab, Structural Diff, and Regression Results with pytest export.

### Deployment

The live demo runs on a dedicated AWS Lightsail instance (2 GB, `us-east-1`). Caddy handles
HTTPS and serves the dashboard. Each lab runs as its own sandboxed systemd service with no
network access beyond loopback, so it can't reach the cloud metadata endpoint or any AWS API.

The public profile (`GHOSTREPLAY_PUBLIC=1`) adds:

- per-client rate limits and a cap on concurrent runs;
- body size and retention caps;
- a private, expiring session for every visitor;
- no data clearing, and live AI mode forced off.

Uploaded traces are validated and stored for inspection only. The server never executes
visitor code. A one-container option (Dockerfile, Render Blueprint) is included for other
hosts.

## Why deterministic replay matters

Agents are non-deterministic twice over: the model may answer differently, and the world
(clocks, ids, services) changes under them. Without replay, "I fixed it" means "I couldn't
reproduce it this time". GhostReplay records every source of non-determinism through one
door, so a replay reproduces the incident byte for byte, offline, with zero risk of touching
a real system. That turns a production incident into something you can step through,
inspect, diff, and share as a file.

## Why failure injection matters

Most agent bugs are not in the happy path. They appear when a tool times out after doing its
job, when a status endpoint is stale, or when a permission check fails halfway through. Those
conditions are rare and hard to trigger on purpose, so they are rarely tested. GhostReplay
lets you take a healthy recording, break exactly one step, and see what the agent does. And
it is honest about what it knows: a fault that only changes what the agent sees can run fully
offline, while a fault that needs a real side effect runs as a labelled branch execution. It
never invents a continuation.

## Skeleton Crew: one skeleton, two apps

The framework is the skeleton; each lab is a thin, independent application on top of it.

**Shared (`packages/ghostreplay`):** `AgentRuntime`, `Session` and its four modes, recorder
and redactor, offline guard, simulated backend building blocks and `ScriptedModel`, the fault
catalog, diff engine, invariant and regression engine, pytest and JUnit generation, SQLite
storage, the HTTP API with SSE replay, the lab CLI (`serve`, `run`, `demo`, `export-cases`),
the guided-demo orchestrator, the gateway, the live LLM adapter, and the whole dashboard.

**App-specific (each lab):** its own world of real local services (a SQLite shop database
and an HTTP refund service, or HTTP instance services and an allowlisted controller), its
allowlisted tools, a scripted model policy for offline tests, the agent harness in a
vulnerable and a fixed variant, domain invariants, incident conditions, named fault presets
and its genuine Claude captures.

Each lab plugs in through Python entry points (`ghostreplay.scenarios` and
`ghostreplay.labs`) and runs on its own (`uv run support-agent-lab serve`) or alongside the
other behind the gateway. At the time of writing, each lab is about 940 lines of Python
against about 5,750 lines of framework, and neither lab contains any replay, fault, diff or
regression logic of its own. A refund bug and an infrastructure outage are caught by the same
code.

## Bring your own agent: the Python SDK

The labs prove the framework is reusable inside this repository. The SDK proves it outside.
`GhostReplay` is a small decorator API over the same engine:

```python
from ghostreplay import GhostReplay, fault

ghost = GhostReplay("my-agent", storage="./ghostreplay-data")


@ghost.tool("payments.charge", destructive=True)
def charge(order_id: str, amount_cents: int, key: str | None = None) -> dict: ...


@ghost.agent("buggy")
def run(task: dict) -> dict: ...


incident = ghost.record(
    task, agent="buggy", faults=[fault("timeout_after_commit", "payments.charge")]
)
ghost.replay(incident)  # offline: no decorated function is called
ghost.write_regression_test(incident, "tests/regression", agent="fixed", import_module="my_agent")
```

It records only what you route through it. There's no automatic instrumentation, and the
documentation says so. The core package depends only on pydantic; the HTTP server is an
extra. A CLI covers `ghostreplay inspect`, `diff`, `replay --app`, `export` and
`test --import`.

`examples/invoice-agent` is a third, separate application that depends only on the public SDK.
A payment commits but times out, the buggy agent pays $258 for a $129 invoice, the offline
replay reproduces it with zero calls to the payment service, and the fixed agent passes the
generated regression tests. CI builds the SDK wheel, installs it with the example into a fresh
virtual environment, and runs all of this. Every code block in the SDK documentation
(`docs/sdk/`) is executed by the test suite.

## How we used Kiro

The repository contains a `.kiro/` directory that documents the project for Kiro:

- **Steering** documents (`.kiro/steering/`) describing the product and its honesty rules,
  the repository structure, the technology stack, coding conventions and the security model.
- **Specs** (`.kiro/specs/`) per component, each with `requirements.md`, `design.md` and
  `tasks.md`.
- **Agent hooks** (`.kiro/hooks/`) that run the framework guarantee tests when the framework
  changes, re-run scenario and regression checks when a lab changes, type-check the dashboard,
  keep the dashboard's TypeScript types in sync with the Pydantic schema, run lint and format
  checks, and scan for secrets.

Tasks marked `[x]` in the specs predate them; the open tasks were carried out in Kiro.

### Spec tasks executed in Kiro

We picked open tasks from the specs and ran them in Kiro's spec task view (Kiro 1.4.121). Kiro records each
execution in the spec's `tasks.meta.json`, which is committed alongside the result:

| Spec | Task | Result |
|---|---|---|
| `failure-injection` | 8. `reordered_response` fault kind | New fault kind: list items arrive reversed or rotated |
| `failure-injection` | 9. `clock_skew` fault kind | New fault kind on `clock.now` reads, so expiry and freshness checks can be broken on purpose. The catalog grew from 13 to 15 kinds |
| `devops-agent-lab` | 10. Invariant `infra.approval_chain_valid` | Fails on self-approved changes, actions that differ from the approved one, and proposals without evidence |
| `devops-agent-lab` | 11. `probe-timeout` preset and honest recovery in the SafetyGate | A failed probe blocks the action and is recorded as a handled, recovered error |
| `dashboard` | 14. Inspector: token usage, `served_by` and "Copy as JSON" | Model calls show usage (tokens, or characters for the scripted model) |
| `dashboard` | 15. Explorer: `live` / `scripted` badge | Every execution says whether a live model or a scripted policy decided |
| `dashboard` | 16. Failure Lab defaults for the new fault kinds | Clock reads become selectable targets for `clock_skew` |

Each task followed the spec's own rule: write or extend a test first, implement, run the
verification commands, then tick the task. The steering file `competition.md` kept Kiro's
changes within scope, and the honesty rules meant new UI says where a decision came from.
The commits are `33630a9`, `9f4e5ce` and `81610d8`.

## Challenges we ran into

- **Timeout after commit cannot be faked offline.** The refund really has to exist while the
  agent sees a timeout. Swapping a recorded response would lie about the world, so we built
  branch mode: replay and verify the prefix, then re-execute against a fresh environment of
  real local services, and label every re-executed event as such.
- **Not inventing continuations.** When a fault makes the agent take a different path, there
  is no recording for what comes next. Strict counterfactual replay therefore stops at the
  first divergence and reports it; only branch mode continues, by really running the agent.
- **Redaction versus matching.** Secrets must never be stored, yet replay must recognise the
  same request. The match key is a hash of the redacted request, using the same redactor as
  the recorder, and tools can restrict matching to selected fields.
- **Thread-safe offline guarantees.** Blocking the network globally would break the server
  that streams the replay. The guard is installed once but only refuses calls from a thread
  that is inside an offline replay.
- **Live LLM recordings.** Thinking blocks must be echoed back unchanged on the next turn, so
  recordings keep the provider-native content blocks. Branch counterfactuals of a live
  recording need a live model and are refused with a clear error when live mode is off.

More detail: `submission/devpost/challenges.md`.

## Accomplishments that we're proud of

- A replay that is checked to be structurally identical to the recording (kinds, names,
  requests, responses, errors, timestamps, durations and state for every event), with zero
  tool handlers invoked and the network blocked.
- An honest model of uncertainty: every event says where its response came from, every
  execution says how it ran, invariants can be `inconclusive`, and nothing simulated or
  scripted is presented as real.
- Two very different domains (customer support refunds and SRE incident response) on one
  framework, each caught and fixed with the same workflow.
- Regression tests generated from the incident that FAIL on the vulnerable agent and PASS
  on the fixed one, committed in `tests/regression/` and re-generated in CI.
- 189 Python tests in the main suite on 2026-11-09 (plus opt-in live-provider tests):
  framework guarantees, the SDK, both labs, generated regressions, deployment, public-session
  isolation, and every runnable code block in the SDK docs. There are 9 more in the external
  invoice example, and 16 Playwright tests drive the homepage, both guided demos, the Connect page, trace import and every
  developer view (one of them applies only to the public site). Each security guarantee in
  the README is covered by a test.
- A live, hardened deployment on AWS Lightsail with private per-visitor sessions, sandboxed
  lab services and no network egress.

## What we learned

- The hard part of agent reliability is usually not the model but the harness around it:
  both fixes are deterministic code (an idempotency key, a safety gate) and the model's
  decisions are unchanged.
- A single interception point beats patching libraries. Because every interaction goes
  through one place, replay, faults and diffs are properties of the framework rather than of
  each tool.
- Saying "we don't know" is a feature. Stopping at a divergence and marking invariants
  `inconclusive` makes the results trustworthy.
- Writing invariants as executable checks with evidence makes the explanation of a bug part
  of the test output.

## What's next for GhostReplay Lab

- Adapters for more model providers and popular agent frameworks, so existing agents can
  adopt the runtime with less wiring.
- More fault kinds (for example partial pagination) and multi-fault scenarios.
- Importing traces from existing observability formats as a starting point for replay.
- Publishing the SDK to PyPI, and a GitHub Action that comments regression results on pull
  requests.
- More labs on the same skeleton (for example data pipelines and coding agents).

## Built with

Python, uv, Pydantic, FastAPI, Uvicorn, SQLite, pytest, Ruff, TypeScript, React, Vite,
Tailwind CSS, pnpm, Playwright, AWS Lightsail, Caddy, systemd, Route 53, Docker, GitHub
Actions, Anthropic API (optional live mode), Kiro (steering, specs and hooks in `.kiro/`).

See `submission/devpost/technologies.md` for versions.
