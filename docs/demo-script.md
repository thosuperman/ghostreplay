# Demo video script (under 3:00)

The story: an AI agent makes an expensive mistake. GhostReplay records it, replays it without side effects, shows exactly why it happened, proves the fix, shows the same framework catching a second agent, and finally plugs into a developer's own Python agent.

**Where to record:**

- **Browser:** <https://ghostreplay.hayaix.tech>, in a fresh private window at 1440×900. Each window is a clean, private session.
- **Terminal:** a local checkout with `examples/invoice-agent` installed (see the end of this page).

**Every number is real.** It's read from the run on screen, and these are the values the demos reproduce:

- the refund demo: $129.00 requested, $258.00 refunded, 2 refunds committed;
- replay: 9 recorded responses reused, 0 tool executions;
- DevOps: 3 of 3 healthy servers terminated, 0 running (minimum 2).

If a take shows different numbers, narrate what is on screen.

**Narration** is about 420 words at roughly 150 words per minute. The on-screen labels below are in "quotes".

---

## 0:00–0:20 · The problem

**Screen:** Home page, hero: "Your AI Agent Made a Mistake. Now What?"

> AI agents don't just chat any more. They issue refunds, change infrastructure and move money. When one makes an expensive mistake, it's almost impossible to reproduce. The API call that failed won't fail the same way twice. GhostReplay is a flight recorder and crash-test lab for AI agents.

**Do:** Click "Watch an AI Agent Fail".

## 0:20–0:50 · The failure

**Screen:** "The Double Refund Incident". Step 1 shows the chat and the three tools. Click "Run the Agent". Step 2 appears.

> A customer asks for a $129 refund. Our support agent can call real tools: find the order, check eligibility, issue the refund. Let's run it… The customer received $258. Two refunds committed. Safety status: FAIL.

**Point at:** the facts row, then the three highlighted story lines.

> Here's what happened. The payment gateway committed the refund, but the response timed out. The agent assumed it had failed and retried the same request, with no idempotency key.

## 0:50–1:15 · Investigation

**Screen:** Step 3. Scroll the plain-English timeline. Open "Show technical details" and click the first `payments.create_refund` event in the inspector.

> GhostReplay recorded every decision and tool call in order. This is the exact call that caused it. The state before and after shows refund count going from zero to one, even though the call returned a timeout. The money had already moved.

**Do:** Click "Replay the Failure".

## 1:15–1:35 · Safe replay

**Screen:** Step 4 facts: "Recorded responses reused" 9, "External tool executions" 0, "Divergence" None, "Replay result" Identical.

> Now we reproduce it offline. GhostReplay re-runs the agent but answers every model and tool call from the recording. Nine responses reused, zero calls to the payment service, and the result is identical. We can replay this incident as often as we like without refunding anyone again.

**Do:** Click "Test the Fix".

## 1:35–2:00 · Verify the fix

**Screen:** Step 5 comparison table: Buggy $258.00, Fixed $129.00, "Duplicate refund" Yes / No, "Safety invariant" FAIL / PASS. Then click "Verify the Fix" and show step 6: "Before: FAILED", "After: PASSED".

> The fixed agent uses an idempotency key and checks existing refunds before retrying. It runs for real against the same timeout-after-commit failure: $129, exactly once. And GhostReplay turns the incident into a regression test. It fails for the buggy agent and passes for the fixed one. That's the proof, and it runs in CI forever.

## 2:00–2:20 · Second application

**Screen:** Click "Try DevOps Demo". Run through quickly: the failure headline "terminated 3 healthy servers", then step 5's "What the fixed agent did differently" list (direct probes ok, guard blocked termination, change waiting for human approval).

> Same framework, a completely different agent. A DevOps agent trusts stale monitoring data and terminates three healthy servers mid-incident. The fixed agent probes each instance directly, the safety guard blocks the termination, and it asks a human to approve a rollback instead. Every AWS action here is simulated.

## 2:20–2:45 · Developer integration

**Screen:** Terminal, in `examples/invoice-agent`. Show `invoice_agent/agent.py` briefly (the `@ghost.tool("payments.pay", destructive=True)` decorator), then run `invoice-agent-demo` and let steps 2, 4 and 7 scroll by.

> And it works with your own agent. This is a separate invoice-processing app using the GhostReplay Python SDK: decorate your tools and model calls, and you get record, offline replay, failure injection and generated pytest regressions. Same bug, caught the same way: $258 paid for a $129 invoice, replayed with zero live calls, fixed, and proven.

**Alternative screen:** the "Connect your agent" page with the quickstart code.

## 2:45–3:00 · Conclusion

**Screen:** Home page hero, then the "How it works" row: Record → Replay → Investigate → Fix → Verify.

> One framework. Multiple agents. Reproducible failures. Verified fixes. GhostReplay: catch the bug, replay the failure, prove the fix.

---

## Before recording

```bash
# Terminal segment (from a checkout)
cd examples/invoice-agent
pip install ../../packages/ghostreplay -e ".[test]"
export INVOICE_AGENT_DATA=":memory:"
invoice-agent-demo
```

- Open the site in a fresh private window so the Explorer starts empty.
- Each guided demo makes about four requests. The public site allows 30 per minute per lab, which is plenty for retakes.
- Don't show or imply Kiro authorship for anything that wasn't built in Kiro. See `docs/kiro-workflow.md`.

## Trims if a take runs long

- Investigation: skip opening the inspector and just point at the highlighted lines (saves about 8 s).
- DevOps: show only the failure headline and the comparison table (saves about 6 s).
- Terminal: show only the final "Demo check passed." output (saves about 5 s).
