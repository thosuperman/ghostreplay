"""Tests for the invoice agent, written against the public GhostReplay SDK only."""

from __future__ import annotations

import pytest
from invoice_agent.agent import ghost

from ghostreplay import fault

TIMEOUT_AFTER_COMMIT = [fault("timeout_after_commit", "payments.pay")]


def test_healthy_run_pays_once():
    run = ghost.record(agent="buggy")
    assert run.passed
    assert run.final_state["total_paid_cents"] == 12900


def test_timeout_after_commit_makes_the_buggy_agent_pay_twice():
    run = ghost.record(agent="buggy", faults=TIMEOUT_AFTER_COMMIT)
    assert run.final_state["total_paid_cents"] == 25800
    assert set(run.failed_invariants) == {
        "payments.no_duplicate",
        "payments.amount_matches_invoice",
    }


def test_offline_replay_calls_nothing_and_matches(monkeypatch):
    incident = ghost.record(agent="buggy", faults=TIMEOUT_AFTER_COMMIT)
    from invoice_agent import payments

    def boom(*_a, **_k):
        raise AssertionError("the payment service was called during replay")

    monkeypatch.setattr(payments.LEDGER, "pay", boom)
    replay = ghost.replay(incident)
    assert replay.status == "completed"
    assert replay.live_calls == 0 and replay.replayed_calls == 4
    assert ghost.diff(incident, replay).identical


def test_fixed_agent_pays_once_under_the_same_fault():
    run = ghost.record(agent="fixed", faults=TIMEOUT_AFTER_COMMIT)
    assert run.passed
    assert run.final_state["total_paid_cents"] == 12900


@pytest.mark.parametrize(("agent", "expect"), [("buggy", "FAIL"), ("fixed", "PASS")])
def test_regression_case_gives_opposite_verdicts(agent, expect):
    incident = ghost.record(agent="buggy", faults=TIMEOUT_AFTER_COMMIT)
    report = ghost.check(ghost.regression_case(incident, agent=agent))
    assert report.verdict == expect
    assert report.outcome_matches_expectation
