GhostReplay Lab: catch the bug, replay the failure, prove the fix.

A flight recorder and crash-test lab for AI agents. In this demo:

- A support agent driven by Claude refunds a customer $258 instead of $129. The refund
  service commits the refund, its reply is delayed past the timeout (an injected fault), and
  the application's retry policy refunds again. The duplicate is real, in a real SQLite ledger.
- GhostReplay replays the incident offline: no model call, no refund, no database write, and
  an identical result.
- The fixed agent, with an idempotency key and a check before retrying, refunds $129 once
  under the same failure. Generated regression tests fail before the fix and pass after it.
- A second agent: an auto-remediation workflow with stale monitoring. Claude refused the
  unsafe runbook; with that decision injected, v1 shuts down three healthy services, and v2's
  safety gate blocks it and asks a human.
- The Python SDK brings the same workflow to your own agent.

Live demo: https://ghostreplay.hayaix.tech
Source (MIT): https://github.com/thosuperman/ghostreplay

Everything runs against isolated test services with fictional data. No real money moves and no
cloud account is touched. Narration is a synthetic voice.
