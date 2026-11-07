"""Guarantees of the Counterfactual Failure Lab."""

from __future__ import annotations

import pytest

from ghostreplay.core.clock import VirtualClock
from ghostreplay.core.errors import RateLimited, ToolTimeout
from ghostreplay.models import EventSource, ExecutionMode, ExecutionStatus, FaultSpec, FaultTarget
from ghostreplay.mutation import CATALOG, apply_fault


def _fault(
    kind: str, name: str = "bank.withdraw", occurrence: int | None = 1, **params
) -> FaultSpec:
    return FaultSpec(
        id=f"t-{kind}",
        kind=kind,
        target=FaultTarget(name=name, occurrence=occurrence),
        params=params,
    )


def test_catalog_covers_required_faults():
    required = {
        "tool_timeout",
        "http_429",
        "http_500",
        "missing_field",
        "null_value",
        "duplicate_response",
        "delayed_operation",
        "stale_data",
        "incorrect_output",
        "auth_failure",
        "permission_denied",
        "partial_success",
        "timeout_after_commit",
    }
    assert required <= set(CATALOG)
    assert CATALOG["timeout_after_commit"].requires_branch
    assert not CATALOG["http_500"].requires_branch


def test_branch_fault_reproduces_double_withdrawal_and_fix_prevents_it(lab):
    base = lab.record("toy-bank", "naive")
    assert all(i.status == "passed" for i in base.invariants)
    fault = [_fault("timeout_after_commit")]
    naive = lab.counterfactual(base.id, fault)
    assert naive.mode == ExecutionMode.BRANCH  # chosen automatically: needs a real side effect
    injected = [e for e in naive.events if e.source == EventSource.INJECTED]
    assert len(injected) == 1 and injected[0].fault.operation_executed
    assert injected[0].error.type == "ToolTimeout"
    assert len(naive.final_state["bank"]["withdrawals"]) == 2
    assert {i.id: i.status for i in naive.invariants}["bank.no_double_withdrawal"] == "failed"

    safe = lab.counterfactual(base.id, fault, variant="safe")
    assert len(safe.final_state["bank"]["withdrawals"]) == 1
    assert {i.id: i.status for i in safe.invariants}["bank.no_double_withdrawal"] == "passed"


def test_offline_counterfactual_stops_instead_of_inventing_a_continuation(lab, counters):
    base = lab.record("toy-bank", "naive")
    counters.handler_calls = counters.model_calls = 0
    cf = lab.counterfactual(base.id, [_fault("http_500", name="bank.balance")], mode="replay")
    assert cf.mode == ExecutionMode.COUNTERFACTUAL_REPLAY
    assert counters.handler_calls == 0 and counters.model_calls == 0
    faulted = next(e for e in cf.events if e.fault)
    assert faulted.replay.verdict == "substituted"
    assert (
        faulted.fault.original_response
        == next(e for e in base.events if e.name == "bank.balance").response
    )
    assert cf.status == ExecutionStatus.DIVERGED
    assert cf.divergence.after_fault
    assert cf.final_state is None
    assert any("branch mode" in n for n in cf.notes)
    by_id = {i.id: i.status for i in cf.invariants}
    assert by_id["bank.no_double_withdrawal"] == "inconclusive"


def test_same_fault_in_branch_mode_executes_continuation(lab):
    base = lab.record("toy-bank", "naive")
    cf = lab.counterfactual(base.id, [_fault("http_500", name="bank.balance")], mode="branch")
    assert cf.status == ExecutionStatus.COMPLETED
    assert cf.output.status == "escalated"
    assert any(e.source == EventSource.SIMULATED for e in cf.events if e.is_interaction)
    assert cf.final_state["bank"]["withdrawals"] == []


def test_branch_without_faults_stays_on_track_and_verifies_tools(lab):
    base = lab.record("toy-bank", "naive")
    cf = lab.counterfactual(base.id, [], mode="branch")
    assert cf.divergence is None
    assert cf.final_state == base.final_state
    tools = [e for e in cf.events if e.kind.value == "tool_call"]
    assert all(e.source == EventSource.SIMULATED and e.replay.verdict == "matched" for e in tools)


def test_requires_branch_faults_are_rejected_offline(lab):
    base = lab.record("toy-bank", "naive")
    with pytest.raises(ValueError):
        lab.counterfactual(base.id, [_fault("timeout_after_commit")], mode="replay")


def test_occurrence_targets_only_that_call(lab):
    base = lab.record("toy-bank", "naive")
    cf = lab.counterfactual(
        base.id, [_fault("http_500", name="bank.balance", occurrence=2)], mode="replay"
    )
    assert not any(e.fault for e in cf.events)  # balance is only called once
    assert cf.status == ExecutionStatus.COMPLETED


# --------------------------------------------------------------------------------------
# Direct fault application
# --------------------------------------------------------------------------------------


def _apply(kind: str, response, **params):
    return apply_fault(
        _fault(kind, **params),
        op_name="op",
        clock=VirtualClock(),
        timeout_ms=1000,
        baseline=lambda: response,
        execute=lambda: response,
    )


def test_transform_faults():
    resp = {"items": [{"id": 1, "status": "ok"}, {"id": 2, "status": "ok"}], "total": 2}
    assert "total" not in _apply("missing_field", resp, path="total").response
    assert _apply("null_value", resp, path="items.0.status").response["items"][0]["status"] is None
    out = _apply("incorrect_output", resp, set={"items.*.status": "impaired"}).response
    assert [i["status"] for i in out["items"]] == ["impaired", "impaired"]
    assert len(_apply("duplicate_response", resp).response["items"]) == 4
    assert resp["items"][0]["status"] == "ok"  # baseline untouched (deep copies)
    missing = _apply("missing_field", resp, path="nope")
    assert missing.response == resp and "not present" in missing.applied.description


def test_error_and_delay_faults():
    assert isinstance(_apply("http_429", {}).error, RateLimited)
    assert _apply("permission_denied", {}).error.error_type == "PermissionDenied"
    slow = _apply("delayed_operation", {"ok": 1}, delay_ms=5000)
    assert isinstance(slow.error, ToolTimeout) and slow.applied.operation_executed
    fast = _apply("delayed_operation", {"ok": 1}, delay_ms=10)
    assert fast.error is None and fast.response == {"ok": 1}


def test_unknown_fault_kind_rejected():
    with pytest.raises(ValueError):
        _apply("meteor_strike", {})
