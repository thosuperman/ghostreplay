# Three-minute demo script

Setup (before recording): `./scripts/dev.sh`, open http://127.0.0.1:5173, click
**Executions → Clear** in both labs for a clean list.

| Time | Screen | Say / do |
|---|---|---|
| 0:00 | Home | "AI agents call real tools. When the world misbehaves — a timeout, a stale health check — they can do real damage. GhostReplay lets you break agents safely, replay the failure, and prove the fix." |
| 0:15 | Click **Try the Duplicate Refund Demo** | "One click. No API keys, everything simulated, every row is a real stored execution." |
| 0:25 | Step 1 · incident | "A customer asks for a $129 refund. The gateway commits it, but the response times out. The agent retries. Three safety invariants fail: two refunds, retries without an idempotency key, and the customer was told $129 while $258 moved." |
| 0:50 | Step 2 → **Watch the replay engine** | Start the replay. "This is the real engine streaming events. Every response is served from the recording — zero tool handlers invoked, network blocked. Identical to the recording." |
| 1:15 | Back → Step 3 | "Why? The first call's observable state shows refund_count = 1 *despite* the timeout. The retry carried no idempotency key." |
| 1:30 | Step 4 → **Open the Failure Lab** | Pick the healthy baseline, preset ★ *Refund times out after commit*. "This fault needs a real side effect, so GhostReplay runs it as a labelled branch execution — it never invents a continuation." Run → FAIL. |
| 1:55 | Switch variant to *fixed*, run again | "Same failure, fixed harness: intent-scoped idempotency key plus reconciliation. PASS — one refund." |
| 2:10 | Step 5 → **Open side-by-side diff** | "First divergence: create_refund arguments gained idempotency_key. Invariants flip from FAIL to PASS." |
| 2:25 | Step 6 → **Export the pytest regression** | "It's now a pytest regression: FAILS on the vulnerable agent, PASSES on the fixed one, with JUnit output for CI." |
| 2:40 | Switch to **DevOps Agent Lab** | "Same framework, different domain: stale health data makes an SRE agent terminate a healthy fleet. The SafetyGate re-verifies, checks blast radius and turns it into a change proposal." |
| 2:55 | — | "Record. Replay. Break. Fix. Prove." |

Terminal alternative: `uv run support-agent-lab demo` and `uv run devops-agent-lab demo` print
the same story with real execution ids.
