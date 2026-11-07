# Design — Support Agent Lab

## Components (`apps/support-agent/src/support_agent/`)
- `environment.py` — builds a `MockDatabase` (orders, customers) and a `MockHttpService`
  named `payments` with routes `POST /v1/refunds` (Idempotency-Key aware) and
  `GET /v1/refunds?payment_id=`. The `timeout_after_commit` condition makes the gateway commit
  the first refund and then lose the response (simulated 30 s latency → `ToolTimeout`).
- `tools.py` — `orders.lookup_order`, `refunds.check_eligibility`, `payments.create_refund`
  (destructive, observes the ledger), `payments.list_refunds`, `crm.send_reply`.
- `model.py` — scripted policy: reads tool results from the conversation and chooses the next
  tool call or final answer.
- `agent.py` — `SupportAgent(variant)`. Shared tool-calling loop; refund execution differs:
  - vulnerable: `for attempt in range(3): try create_refund(args) except ToolTimeout: retry`
  - fixed: key = `refund:{ticket}:{payment}:{amount}`; on timeout → `list_refunds` reconcile;
    retry with the same key only if nothing was committed.
- `invariants.py`, `scenario.py` (`DuplicateRefundScenario`), `cli.py`.

## Why the bug is real
A timeout is *ambiguous*: the client cannot know whether the server committed. Retrying a
non-idempotent POST after an ambiguous failure can apply the side effect twice. The fix makes
the operation idempotent end-to-end: the key is derived from the business intent, so every
retry (even after a process restart) maps to the same server-side record, and the agent
reconciles state before retrying.
