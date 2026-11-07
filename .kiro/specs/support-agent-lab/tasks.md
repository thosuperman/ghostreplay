# Implementation plan — Support Agent Lab

- [x] 1. Package skeleton `support-agent-lab` depending on `ghostreplay` (workspace)
- [x] 2. Simulated environment: orders DB + payments HTTP service with idempotency + incident condition
- [x] 3. Tools with Pydantic argument models and ledger observation
- [x] 4. Scripted model policy (labelled scripted)
- [x] 5. Agent harness: vulnerable and fixed refund execution
- [x] 6. Invariants (no_duplicate, within_order_total, retries_are_idempotent, reply.matches_ledger, errors.surfaced)
- [x] 7. Scenario + fault presets + CLI (`run`, `serve`, `demo`)
- [x] 8. Tests: incident fails, replay identical, counterfactual vulnerable FAIL / fixed PASS
- [x] 9. Generated regression cases committed under `tests/regression/`
