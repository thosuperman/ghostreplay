## Inspiration

A customer writes in: the earbuds arrived broken, can I get a refund? An AI support agent
looks up the order, checks the refund policy and asks the payment service to refund $129.
The service commits the refund, but its response times out. The app retries, as any retry
loop would. The customer gets **$258** back and is told $129.

Nothing in that story is exotic. Timeouts after commit, rate limits, stale reads and
permission errors happen in production every day. What is new is that an LLM now decides what
happens next, and the tools it calls move money and delete servers.

When that goes wrong, teams usually have a log and a lot of guesswork. You can't safely re-run
the incident (it would refund the customer a third time). You can't easily make the service
time out at exactly the right moment. And once you change the code, nothing proves this exact
failure can't happen again.

We wanted the tool we wished we had: **a flight recorder and a crash-test lab for AI agents.**

## What it does

GhostReplay Lab is an open-source framework, a Python SDK and a visual lab that run one loop
end to end:

**Record → Replay offline → Inject a failure → Detect unsafe behaviour → Fix → Prove with pytest**

1. **Record.** Every model call, tool call, clock read and generated id is captured in order,
   and secrets are redacted before anything is stored.
2. **Replay offline.** The agent's real code runs again, but every response comes from the
   recording. Tool functions are replaced by stubs that raise if called, and the network is
   blocked. The replay is checked to be identical to the recording.
3. **Inject a failure.** Break any recorded step with one of 15 fault kinds: a tool timeout, a
   timeout after commit, HTTP 429 or 500, an authentication failure, permission denied, a
   missing field, a null value, a duplicate response, reordered response items, clock skew,
   stale data, incorrect output, a delayed operation or a partial success.
4. **Detect.** Safety invariants check the run, for example no duplicate refund, retries are
   idempotent, capacity is preserved and destructive actions require approval.
5. **Fix** the code around the model and run the same failure again.
6. **Prove.** Export the incident as a pytest regression case that FAILS on the buggy agent and
   PASSES on the fixed one, with JUnit and JSON reports for CI.

Two applications run on the same framework, each with a six-step guided demo on the live site:

- **[The Double Refund Incident](https://ghostreplay.hayaix.tech/demo/refund).** The refund
  service commits $129 but answers too late, and the app's retry (with no idempotency key)
  refunds $258. The fix is an idempotency key plus a check for existing refunds before any
  retry: one refund, invariant PASS.
- **[The AI Agent That Almost Deleted Healthy Servers](https://ghostreplay.hayaix.tech/demo/devops).**
  Monitoring reports 3 healthy `checkout-api` instances as impaired after a bad deploy. When
  the workflow follows its runbook, it terminates all 3 and turns a bad deploy into an outage.
  The fix is runbook v2 plus a safety gate in code: probe each target directly, require
  approval, block the destructive call. All 3 servers stay up.

**What is real.** The model's decisions come from genuine Claude (`claude-opus-5-5`)
tool-calling runs, recorded live and shipped as read-only captures. Every click on the site
re-executes those runs for real:

- the support agent writes to a SQLite database through a local HTTP refund service with
  transactional commits and idempotency keys;
- the DevOps agent talks to three HTTP instance services and an allowlisted controller, where
  health probes really call the instances and termination really shuts them down.

Faults are injected on purpose and labelled everywhere. The public server makes no paid model
calls.

The live runs taught us two things. Claude refused the unsafe runbook, so the DevOps demo
shows that real decision and then tests the workflow with a labelled, injected one. "The model
was careful today" is not a safety control. And when the tool schema allowed it, Claude passed
its own idempotency key, so the buggy app never offers one: the bug lives in the application,
not the model.

**Bring your own agent.** The `GhostReplay` Python SDK puts the same engine behind a few
decorators (`@ghost.tool`, `@ghost.model`, `@ghost.agent`, `@ghost.invariant`). A separate
example app, an invoice-processing agent, uses only the public SDK and reproduces the same
class of bug end to end. Visitors can also import a trace file and inspect it in the browser.

## How we built it

- **One door between the agent and the world.** GhostReplay doesn't monkey-patch HTTP clients
  or SDKs. Every model call, tool call, clock read and id goes through one `Session.interact`,
  which, depending on the mode, executes it, serves it from the recording or injects a fault.
  It records exactly one event that says where the response came from.
- **Four execution modes.**
  - `record` runs the agent for real.
  - `replay` is deterministic and offline.
  - `counterfactual-replay` injects a fault offline and *stops at the first divergence* rather
    than guess what the agent would do next.
  - `branch` replays and verifies the prefix, then re-executes for real. It's needed for faults
    that require a real side effect, such as a timeout after commit.
- **Skeleton Crew.** One shared framework (`packages/ghostreplay`, about 7,700 lines of Python)
  and two thin, independent labs (about 1,200 and 1,300 lines). Neither lab contains any
  replay, fault, diff or regression logic of its own: a refund bug and an infrastructure outage
  are caught by the same code.
- **Stack.**
  - Python 3.12, Pydantic, FastAPI with Server-Sent Events, SQLite, pytest.
  - A React and TypeScript (strict) dashboard with Vite and Tailwind CSS.
  - Playwright end-to-end tests and GitHub Actions CI.
  - The Anthropic API for the live recordings.
- **Deployment.**
  - A dedicated AWS Lightsail instance behind Caddy (HTTPS).
  - Each lab is a sandboxed systemd service with no network access beyond loopback.
  - Private, expiring sessions per visitor, rate limits, and atomic releases with automatic
    rollback.
- **Kiro (1.4.121).**
  - Steering documents hold the product's honesty and security rules.
  - Each component has a spec (requirements, design, tasks).
  - Agent hooks run the framework tests, scenario regressions, type check, schema sync, lint
    and a secret scan.
  - We ran open spec tasks in Kiro's task view. That work added the `reordered_response` and
    `clock_skew` fault kinds, the `infra.approval_chain_valid` invariant, honest recovery for
    failed probes in the safety gate, model-usage details in the inspector, live/scripted
    badges in the explorer, and Failure Lab support for the new fault kinds.
  - Kiro's execution history is committed in each spec's `tasks.meta.json`.

## Challenges we ran into

- **A timeout after commit can't be faked offline.** The refund really has to exist while the
  agent sees a timeout. Swapping in a different recorded response would lie about the world,
  so we built branch mode: verify the recorded prefix, then really re-execute and label it.
- **Not inventing continuations.** Once a fault makes the agent take a different path, there's
  no recording of what comes next. Strict replay stops at the first divergence and reports it.
- **Redaction versus matching.** Secrets must never be stored, yet replay must recognise the
  same request. The match key is a hash of the *redacted* request, built by the same redactor
  as the recorder.
- **Offline without breaking the server.** Blocking the network globally would kill the server
  that streams the replay, so the guard only blocks the thread that is replaying.
- **Honest labels with a real LLM.** Real Claude refused the unsafe action, so the dangerous
  decision had to be injected. Keeping that injected decision labelled as injected through
  re-execution, replay and the UI took real work.
- **Determinism with real services.** Real HTTP latency, ids and timestamps had to be recorded
  (or run on virtual clocks) so a re-execution of a live run is still byte-for-byte comparable.

## Accomplishments that we're proud of

- A replay that is checked to be identical to the recording, event for event, with zero tool
  functions called and the network blocked.
- Honest labels throughout: every event says where its response came from (live, recorded,
  injected or re-executed), every run says how it ran, and invariants can say `inconclusive`
  instead of passing silently.
- Two very different domains (customer-support refunds and SRE incident response) caught and
  fixed with the same workflow, plus a third app built only on the public SDK.
- Regression tests generated from real incidents that FAIL on the buggy agent and PASS on the
  fixed one, committed and re-run in CI.
- 189 Python tests, 9 more in the invoice example and 16 Playwright end-to-end tests. Every
  code block in the SDK docs is executed by the test suite.
- A live, hardened public deployment that anyone can click through in a few minutes, with no
  sign-up and no API key.

## What we learned

- **Agent reliability is mostly harness reliability.** Both fixes are ordinary deterministic
  code (an idempotency key, a safety gate). The model's decisions didn't change.
- **Don't rely on the model's judgment.** Claude refused the dangerous runbook, which is good,
  but a different prompt, model or day might not. Test the workflow, not the model's mood.
- **One interception point beats patching libraries.** Because every interaction passes through
  one place, replay, faults and diffs are properties of the framework rather than of each tool.
- **"We don't know" is a feature.** Stopping at a divergence and marking invariants
  `inconclusive` makes the results trustworthy.
- **Spec-driven work pays off.** Writing requirements, design and tasks first kept each change
  small and testable, and the hooks re-run the right tests whenever a file is saved.

## What's next for GhostReplay Lab

- Publish the SDK to PyPI, and ship a GitHub Action that comments regression results on pull
  requests.
- Adapters for popular agent frameworks and more model providers, so existing agents need less
  wiring.
- Order-independent matching for concurrent tool calls, and multi-fault scenarios.
- Import traces from existing observability formats as a starting point for replay.
- More labs on the same skeleton, for example data pipelines and coding agents.
