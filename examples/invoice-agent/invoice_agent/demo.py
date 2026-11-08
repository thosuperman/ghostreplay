"""Walk through the whole GhostReplay workflow on the invoice agent.

    invoice-agent-demo            (after `pip install`), or
    python -m invoice_agent.demo

Every number printed below comes from a real execution recorded in a local SQLite store
(INVOICE_AGENT_DATA, default ./.ghostreplay-invoice). Payments are simulated in memory.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from ghostreplay import fault

from .agent import ghost


def dollars(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def banner(n: int, title: str) -> None:
    print(f"\n{n}. {title}\n" + "-" * (len(title) + 3))


def main() -> int:
    timeout_after_commit = [fault("timeout_after_commit", "payments.pay")]

    banner(1, "Record a normal run (buggy agent, healthy payment service)")
    baseline = ghost.record(agent="buggy", title="baseline")
    print(baseline.explain())

    banner(2, "Inject a timeout after the payment commits")
    incident = ghost.record(agent="buggy", faults=timeout_after_commit, title="incident")
    paid = incident.final_state["total_paid_cents"]
    print(f"payments.pay calls: {len(incident.tool_calls('payments.pay'))}")
    print(f"vendor received:    {dollars(paid)} for a {dollars(12900)} invoice")
    print(incident.explain())

    banner(3, "Identify the bad call")
    for call in incident.tool_calls("payments.pay"):
        outcome = f"error {call.error.type}" if call.error else f"ok {call.response['payment_id']}"
        print(f"  seq {call.seq}: payments.pay {call.request} -> {outcome}")

    banner(4, "Replay the incident offline")
    replay = ghost.replay(incident)
    same = ghost.diff(incident, replay).identical
    print(
        f"status={replay.status} identical={same} "
        f"live calls={replay.live_calls} served from recording={replay.replayed_calls}"
    )

    banner(5, "Run the fixed agent under the same fault")
    fixed = ghost.record(agent="fixed", faults=timeout_after_commit, title="fixed")
    print(f"vendor received:    {dollars(fixed.final_state['total_paid_cents'])}")
    print(fixed.explain())

    banner(6, "Compare buggy and fixed")
    d = ghost.diff(incident, fixed)
    print(f"first divergence: {d.first_divergence['summary'] if d.first_divergence else 'none'}")
    print(
        f"  buggy: {len(incident.tool_calls('payments.pay'))} payment call(s), failed {incident.failed_invariants}"
    )
    print(
        f"  fixed: {len(fixed.tool_calls('payments.pay'))} payment call(s), failed {fixed.failed_invariants}"
    )

    banner(7, "Turn the incident into regression tests and run them")
    out = Path(tempfile.mkdtemp(prefix="invoice-regressions-"))
    for agent in ("buggy", "fixed"):
        _case, test_path = ghost.write_regression_test(
            incident, out, agent=agent, import_module="invoice_agent.agent"
        )
        report = ghost.check(ghost.regression_case(incident, agent=agent))
        verdict = "as expected" if report.outcome_matches_expectation else "UNEXPECTED"
        print(f"  {agent:5} -> {report.verdict} (expected {report.expect.upper()}, {verdict})")
        print(f"         wrote {test_path.name}")
    print(f"\nRun them with:  pytest {out}")

    ok = (
        baseline.passed and not incident.passed and same and replay.live_calls == 0 and fixed.passed
    )
    print("\nDemo check passed." if ok else "\nDEMO CHECK FAILED.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
