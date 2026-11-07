"""Negative and edge-case tests for replay, mutation and persistence.

Each test drives the real engine (lab, session, store) and asserts on observable behaviour:
what was recorded, what was raised, and whether any handler or model ran.
"""

from __future__ import annotations

import json
import sqlite3

import pytest
from toy import BankAgent

from ghostreplay.core.errors import TraceFormatError
from ghostreplay.models import (
    EventKind,
    Execution,
    ExecutionStatus,
    FaultSpec,
    FaultTarget,
)
from ghostreplay.regression.cases import load_case
from ghostreplay.storage import SqliteStore, export_execution, import_execution
from ghostreplay.storage.parsing import parse_document

SC = "toy-bank"


def _as_dict(ex: Execution) -> dict:
    return json.loads(ex.model_dump_json())


def _interaction_indexes(doc: dict) -> list[int]:
    kinds = {"model_call", "tool_call", "nondeterminism"}
    return [i for i, e in enumerate(doc["events"]) if e["kind"] in kinds]


# -- missing / reordered / unexpected recordings ------------------------------------------


def test_replay_of_truncated_recording_reports_missing_recording(lab, counters):
    rec = lab.record(SC, "naive")
    doc = _as_dict(rec)
    last = _interaction_indexes(doc)[-1]
    dropped = doc["events"].pop(last)
    doc["id"] = "rec_truncated"
    lab.store.save(Execution.model_validate(doc))

    counters.handler_calls = counters.model_calls = 0
    rpl = lab.replay("rec_truncated")

    assert rpl.status == ExecutionStatus.DIVERGED
    assert rpl.divergence is not None and rpl.divergence.type == "unexpected_call"
    assert rpl.divergence.actual["name"] == dropped["name"]
    assert "Missing recording" in rpl.divergence.message
    # The engine never fell back to executing the missing interaction.
    assert counters.handler_calls == 0 and counters.model_calls == 0


def test_recording_with_out_of_order_events_is_rejected(lab, tmp_path):
    rec = lab.record(SC, "naive")
    doc = _as_dict(rec)
    a, b = _interaction_indexes(doc)[:2]
    doc["events"][a], doc["events"][b] = doc["events"][b], doc["events"][a]

    with pytest.raises(TraceFormatError, match="events out of order"):
        parse_document(Execution, doc, source="tampered trace")

    path = tmp_path / "tampered.trace.json"
    path.write_text(json.dumps(doc))
    with pytest.raises(TraceFormatError, match=r"trace file tampered\.trace\.json"):
        import_execution(tmp_path, path.name)


def test_reordered_interactions_diverge_at_the_first_swapped_call(lab, counters):
    """A recording that is internally consistent but in a different order than the agent's
    behaviour must diverge — never be matched out of order."""
    rec = lab.record(SC, "naive")
    doc = _as_dict(rec)
    tools = [i for i, e in enumerate(doc["events"]) if e["kind"] == "tool_call"]
    models = [i for i, e in enumerate(doc["events"]) if e["kind"] == "model_call"]
    first_model, first_tool = models[0], tools[0]
    # Swap the payloads but keep seq numbers increasing, so the document itself is valid.
    for key in ("kind", "name", "request", "response", "match_key", "model"):
        doc["events"][first_model][key], doc["events"][first_tool][key] = (
            doc["events"][first_tool][key],
            doc["events"][first_model][key],
        )
    doc["id"] = "rec_reordered"
    lab.store.save(Execution.model_validate(doc))

    counters.handler_calls = counters.model_calls = 0
    rpl = lab.replay("rec_reordered")
    assert rpl.status == ExecutionStatus.DIVERGED
    assert rpl.divergence.type == "mismatch"
    assert rpl.divergence.recorded_seq == doc["events"][first_model]["seq"]
    assert "Execution path changed" in rpl.divergence.message
    assert counters.handler_calls == 0 and counters.model_calls == 0


def test_unexpected_extra_tool_call_during_replay_is_not_executed(lab, counters, monkeypatch):
    rec = lab.record(SC, "naive")
    original = BankAgent.run

    def chatty(self, rt, task):
        result = original(self, rt, task)
        rt.call_tool("bank.balance", {"account": "acc-1"})  # not in the recording
        return result

    monkeypatch.setattr(BankAgent, "run", chatty)
    counters.handler_calls = 0
    rpl = lab.replay(rec.id)
    assert rpl.status == ExecutionStatus.DIVERGED
    assert rpl.divergence.type == "unexpected_call"
    assert counters.handler_calls == 0
    assert any(e.kind == EventKind.DIVERGENCE for e in rpl.events)


# -- mutations ------------------------------------------------------------------------------


def test_mutation_that_invalidates_the_recorded_path_stops_offline_replay(lab, counters):
    """Lowering the balance makes the agent skip the withdrawal. Offline replay must stop
    at that point instead of serving the recorded withdrawal or inventing a reply."""
    rec = lab.record(SC, "naive")
    fault = FaultSpec(
        id="low-balance",
        kind="incorrect_output",
        target=FaultTarget(name="bank.balance"),
        params={"set": {"balance": 10}},
    )
    counters.handler_calls = counters.model_calls = 0
    cf = lab.counterfactual(rec.id, [fault], mode="replay")

    assert cf.status == ExecutionStatus.DIVERGED
    assert cf.divergence is not None and cf.divergence.after_fault
    injected = next(e for e in cf.events if e.fault is not None)
    assert injected.response["balance"] == 10
    assert injected.fault.original_response["balance"] != 10
    # Nothing after the divergence was executed or served from the recording.
    assert counters.handler_calls == 0 and counters.model_calls == 0
    assert not any(e.name == "bank.withdraw" for e in cf.events if e.kind == EventKind.TOOL_CALL)


def test_same_mutation_in_branch_mode_runs_the_new_path_and_labels_it(lab):
    rec = lab.record(SC, "naive")
    fault = FaultSpec(
        id="low-balance",
        kind="incorrect_output",
        target=FaultTarget(name="bank.balance"),
        params={"set": {"balance": 10}},
    )
    br = lab.counterfactual(rec.id, [fault], mode="branch")
    assert br.status == ExecutionStatus.COMPLETED
    assert "escalating" in br.output.message.lower()
    assert br.final_state is not None
    assert not any(e.name == "bank.withdraw" for e in br.events if e.kind == EventKind.TOOL_CALL)


# -- malformed data -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: "{not json", "not valid JSON"),
        (lambda d: "[1, 2]", "must contain a JSON object"),
        (lambda d: {**d, "schema_version": "ghostreplay/v0"}, "unsupported schema_version"),
        (lambda d: {k: v for k, v in d.items() if k != "provenance"}, "provenance"),
        (lambda d: {**d, "__class__": "os.system"}, "Extra inputs are not permitted"),
        (
            lambda d: {**d, "events": [*d["events"], d["events"][-1]]},
            "events out of order",
        ),
    ],
)
def test_malformed_execution_documents_fail_with_useful_errors(lab, mutate, message):
    doc = _as_dict(lab.record(SC, "naive"))
    raw = mutate(doc)
    with pytest.raises(TraceFormatError, match=message):
        parse_document(Execution, raw, source="input")


def test_corrupt_store_row_is_reported_on_get_and_skipped_in_list(lab, tmp_path):
    store = SqliteStore(tmp_path / "db.sqlite3")
    good = lab.record(SC, "naive")
    store.save(good)
    bad = lab.record(SC, "safe")
    store.save(bad)
    with sqlite3.connect(store.path) as conn:
        conn.execute(
            "UPDATE executions SET body_json = ?, summary_json = ? WHERE id = ?",
            ('{"truncated', "{}", bad.id),
        )
    with pytest.raises(TraceFormatError, match=f"stored execution '{bad.id}'"):
        store.get(bad.id)
    assert [s.id for s in store.list()] == [good.id]
    assert store.get(good.id).id == good.id


def test_malformed_case_file_is_rejected(tmp_path):
    path = tmp_path / "broken.case.json"
    path.write_text(json.dumps({"id": "x", "scenario": "toy-bank"}))
    with pytest.raises(TraceFormatError, match=r"case file broken\.case\.json"):
        load_case(path)


def test_exported_trace_roundtrips_and_tampering_is_detected(lab, tmp_path):
    rec = lab.record(SC, "naive")
    path = export_execution(rec, tmp_path)
    assert import_execution(tmp_path, path.name) == rec
    doc = json.loads(path.read_text())
    doc["events"][1]["seq"] = 0
    path.write_text(json.dumps(doc))
    with pytest.raises(TraceFormatError):
        import_execution(tmp_path, path.name)


# -- persistence --------------------------------------------------------------------------


def test_store_prunes_oldest_executions_beyond_the_cap(lab):
    store = SqliteStore(":memory:", max_executions=3)
    ids = []
    for _ in range(5):
        ex = lab.record(SC, "naive")
        store.save(ex)
        ids.append(ex.id)
    kept = {s.id for s in store.list(app="toy")}
    assert kept == set(ids[-3:])
    assert store.count(app="toy") == 3


def test_file_store_uses_wal_and_survives_reopen(lab, tmp_path):
    path = tmp_path / "wal.sqlite3"
    store = SqliteStore(path)
    assert store.ping()
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    ex = lab.record(SC, "naive")
    store.save(ex)
    store.close()
    assert SqliteStore(path).get(ex.id) == ex


def test_demo_story_reports_whether_every_step_met_expectations(lab):
    story = lab.prepare_demo(SC)
    assert story.ok
    assert [s.expected for s in story.steps if s.expected] == [
        "fail",
        "pass",
        "fail",
        "pass",
        "pass",
    ]
    dumped = story.model_dump(mode="json")
    assert dumped["ok"] is True and all("as_expected" in s for s in dumped["steps"])
