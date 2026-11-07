# Demo video script (target 2:55, hard limit under 3:00)

Story first: a customer is refunded twice, we replay it, break a healthy run the same way,
fix it, prove it, then show the same framework catching an SRE agent that terminates a
healthy fleet, and close with the Kiro workflow.

Labels below in "quotes" are the exact texts on screen in the dashboard (`apps/dashboard/src`).
Re-check them against the build you record, since the UI may still change.

Numbers used in the narration come from the real terminal demos
(`uv run support-agent-lab demo`, `uv run devops-agent-lab demo`): a $129 refund issued twice
($258 total), and 3 healthy `checkout-api` instances terminated (0 left running, minimum 2).

Speaking pace: about 150 words per minute. The narration below is about 430 words. If a take
runs long, use the trims at the end.

**Before recording:** read `recording-guide.md` (clean store, window size, which recordings
exist). The Kiro segment (2:33 to 2:50) must show **real** Kiro work only; see the note in
that segment.

---

## 0:00 to 0:12 · Cold open: the incident

**Screen:** Dashboard home page, hero visible ("Break AI agents safely. Replay failures.
Prove the fix."). Cursor still.

**Narration:**
> A customer asked for a $129 refund for broken earbuds. Our AI support agent sent her $258
> and told her $129. Nobody hacked anything. The payment gateway timed out *after* it had
> already refunded, and the agent simply retried.

## 0:12 to 0:22 · What GhostReplay is

**Screen:** Move the cursor over the two demo cards. Click **"Try the Duplicate Refund Demo"**.
The page shows "Preparing the demo with real executions…" with its checklist.

**Narration:**
> GhostReplay Lab records what an agent did, replays it offline, breaks it on purpose, and
> proves the fix. One click, no API keys. Every tool here is a simulation, and every row is a
> real stored execution.

## 0:22 to 0:38 · Step 1: the recorded incident

**Screen:** Guided demo loads. Point at the header badges "✓ bug reproduced" and
"✓ fix proven", then at step 1 "The incident" with its FAIL verdict and the three failed
invariants on the right (`refund.no_duplicate`, `refund.retries_are_idempotent`,
`reply.matches_ledger`). Briefly point at the timeline on the left.

**Narration:**
> This is the recorded incident. Three safety invariants fail: two refunds for one payment,
> a retry without an idempotency key, and a reply that doesn't match the ledger.

## 0:38 to 0:58 · Step 2: offline replay

**Screen:** Scroll to step 2 "Reproduce it offline". Point at the metrics "tool handlers
invoked 0", "network blocked", "diff vs recording identical". Click
**"▶ Watch the replay engine"**. In Replay Studio click **"▶ Start offline replay"** and let
rows stream into "Replay engine" with "✓ matched" badges.

**Narration:**
> Now we replay it. Same agent code, but every response comes from the recording. Zero tool
> handlers invoked, network blocked on the replay thread, and the result is identical to the
> recording. We can debug the incident without refunding anyone a third time.

## 0:58 to 1:08 · Step 3: why it happened

**Screen:** Browser back to the guided demo. Scroll to step 3 "Why it happened". Point at
the evidence card for the first `payments.create_refund` call: the timeout error and
"observable state after" showing the refund was recorded.

**Narration:**
> The evidence: the first refund call timed out, but the state shows the refund was
> committed. The retry carried no idempotency key.

## 1:08 to 1:33 · Step 4: break a healthy run on purpose

**Screen:** Scroll to step 4 "Break a healthy run on purpose". Click
**"Open the Failure Lab →"**. In "Counterfactual Failure Lab", the healthy recording is
preselected under "Recorded execution". Click the preset **"★ Refund times out after
commit"**; point at the "requires branch execution" badge. Leave "Execution mode" on
"Auto (branch only if required)". Click **"⚡ Inject failure and run"**. Result card
"3 · Result" shows **FAIL**.

**Narration:**
> Could we have caught this before production? Take a healthy run and break exactly one
> step: the refund times out after commit. That failure needs a real side effect, so
> GhostReplay runs it as a labelled branch execution against a fresh simulation. It never
> invents what the agent would have done. Result: FAIL, two refunds.

## 1:33 to 1:46 · The fix

**Screen:** Change "Agent variant under test" to **"Idempotent harness (fixed)"**. Click
**"⚡ Inject failure and run"** again. Result shows **PASS**.

**Narration:**
> The fix lives in the harness, not the model: an idempotency key derived from the refund
> intent, and a reconciliation check before any retry. Same failure: PASS, one refund.

## 1:46 to 1:56 · Step 5: the diff

**Screen:** Back to the guided demo, step 5 "Apply the fix and run the same failure". Point at
"First divergence between vulnerable and fixed" and the invariant table flipping from FAIL to
PASS. Click **"Open side-by-side diff →"** and show the highlighted "first divergence" row.

**Narration:**
> The structural diff shows exactly where behaviour changed: the refund call gained an
> idempotency key, and every invariant flips to PASS.

## 1:56 to 2:10 · Step 6: prove it

**Screen:** Back to the guided demo, step 6. Click **"Export the pytest regression →"**. In
"Regression Results" click **"▶ Run against every agent variant"**: the vulnerable case shows
FAIL with "expected FAIL ✓", the fixed case PASS with "expected PASS ✓". Click
**"Generate"** under "Export as pytest" to show the generated test. Optional 2-second cut to a
terminal running `uv run pytest tests/regression -q`.

**Narration:**
> And now it's a regression test. It fails on the vulnerable agent and passes on the fixed
> one, as pytest with JUnit output for CI.

## 2:10 to 2:33 · Same framework, different domain

**Screen:** Click the "DevOps Agent Lab" switch in the header (or go Home and click
**"Try the Unsafe Infrastructure Demo"**). Guided demo for "Unsafe Infrastructure Action":
step 1 shows FAIL with `infra.capacity_preserved` ("Only 0 checkout-api instance(s) left
running (minimum 2)"). Scroll to step 5 and point at the fixed column (PASS) and the quotes
"Vulnerable agent told the user" / "Fixed agent told the user".

**Narration:**
> Same framework, different domain. During a bad deploy, a stale health view marks a healthy
> fleet as impaired, and an SRE agent terminates all three instances. The fix is a
> SafetyGate: verify each target directly, check permissions and blast radius, require human
> approval. All three instances keep running, and the agent files a change proposal instead.
> Replay, faults, diff and regressions: all shared code.

## 2:33 to 2:50 · Kiro workflow (record only real work)

> **Author note, do not read aloud.** Record this segment only after real Kiro sessions
> (see `docs/kiro-workflow.md`). Show only what actually happened. Suggested shots, if they
> are real: the `.kiro/specs/<component>/tasks.md` view with an open task; Kiro executing
> that task; a hook from `.kiro/hooks/` firing (for example the framework guarantee tests)
> and its output; the resulting commit. Do not claim Kiro wrote the existing code: the specs
> and steering were written after the implementation to document it. Rewrite the narration
> below to match the footage.

**Screen:** Kiro with this repository open: steering documents, a spec, a hook run.

**Narration (template, edit to match the footage):**
> The project's steering, specs and hooks live in the repository's `.kiro` folder. Here I'm
> working through an open task from the spec, and the hook re-runs the framework's guarantee
> tests the moment the core changes.

## 2:50 to 2:57 · Close

**Screen:** Dashboard home page hero, then the repository URL and `<DEPLOYED_URL>` as a
lower-third.

**Narration:**
> GhostReplay Lab. Break AI agents safely. Replay failures. Prove the fix. Open source,
> MIT licensed.

---

## Trims if the take runs long

1. Drop the Replay Studio click (0:38 to 0:58): stay on step 2's metrics and say only
   "Zero tool handlers invoked, network blocked, identical to the recording." Saves ~8 s.
2. Drop the side-by-side diff click (1:46 to 1:56): point at the step 5 table only. Saves ~5 s.
3. Drop the terminal cut in step 6. Saves ~2 s.

## Honesty checks for the final cut

- The badges "offline · simulated backends" and "scripted models" are visible in the header
  in at least one shot (they appear on wide windows, see `recording-guide.md`).
- Do not describe scripted decisions as "the AI decided" without saying it is a scripted
  model, unless you recorded with live AI mode on.
- Do not show or mention a deployment, CI result or Kiro activity that did not happen.
