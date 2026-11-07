"""Redaction, path safety, storage and tool allowlist guarantees."""

from __future__ import annotations

import json

import pytest

from ghostreplay.core.clock import VirtualClock
from ghostreplay.core.errors import ToolValidationError, UnknownToolError, UnsafePathError
from ghostreplay.mocking import ToolRegistry, ToolSpec
from ghostreplay.models import EventKind, EventSource
from ghostreplay.recorder import REDACTED, Recorder, Redactor
from ghostreplay.storage import SqliteStore, export_execution, import_execution, safe_join


def test_redactor_scrubs_keys_and_values_but_keeps_benign_fields():
    r = Redactor()
    data = {
        "api_key": "abc123",
        "headers": {"Authorization": "Bearer abcdefghijklmnop", "Idempotency-Key": "refund:1"},
        "note": "use key AKIAABCDEFGHIJKLMNOP and sk-live-abcdefghijklmnopqrstuv",  # secret-scan: allow
        "card": "4242 4242 4242 4242",
        "order_number": "1234567890123",  # not Luhn valid -> kept
        "max_tokens": 1000,
        "idempotency_key": "refund:1",
        "nested": [{"password": "hunter2"}],
    }
    out = r.redact(data)
    assert out["api_key"] == REDACTED
    assert out["headers"]["Authorization"] == REDACTED
    assert out["headers"]["Idempotency-Key"] == "refund:1"
    assert "AKIA" not in out["note"] and "sk-live" not in out["note"]
    assert out["card"] == "[REDACTED:card_number]"
    assert out["order_number"] == "1234567890123"
    assert out["max_tokens"] == 1000 and out["idempotency_key"] == "refund:1"
    assert out["nested"][0]["password"] == REDACTED


def test_recorder_persists_only_redacted_payloads(lab):
    from ghostreplay.models import Execution, ExecutionMode, Provenance

    ex = Execution(
        id="r",
        app="t",
        scenario="s",
        variant="v",
        agent="a",
        mode=ExecutionMode.RECORD,
        created_at="x",
        started_at="x",
        provenance=Provenance(model_provider="scripted", model="m", model_is_live=False, label="l"),
    )
    rec = Recorder(ex, VirtualClock())
    ev = rec.emit(
        EventKind.TOOL_CALL,
        "t",
        source=EventSource.LIVE,
        request={"token": "s3cr3t", "q": "Bearer zzzzzzzzzzzz"},
        response={"aws_secret_access_key": "x"},
    )
    dumped = ev.model_dump_json()
    assert "s3cr3t" not in dumped and "zzzzzzzzzzzz" not in dumped and '"x"' not in dumped


def test_tool_registry_is_an_allowlist_with_validation():
    from pydantic import BaseModel

    class Args(BaseModel):
        n: int

    reg = ToolRegistry()
    reg.register(ToolSpec("ok", lambda n: n * 2, args_model=Args))
    with pytest.raises(UnknownToolError):
        reg.get("rm_rf")
    with pytest.raises(ToolValidationError):
        reg.get("ok").validate({"n": "not-a-number"})


def test_unknown_tool_call_is_recorded_as_error_not_executed(lab):
    from ghostreplay.core.errors import ToolError
    from ghostreplay.models import Execution, ExecutionMode, Provenance
    from ghostreplay.replay import Session
    from ghostreplay.runtime import AgentRuntime

    ex = Execution(
        id="u",
        app="t",
        scenario="s",
        variant="v",
        agent="a",
        mode=ExecutionMode.RECORD,
        created_at="x",
        started_at="x",
        provenance=Provenance(model_provider="scripted", model="m", model_is_live=False, label="l"),
    )
    clock = VirtualClock()
    rt = AgentRuntime(
        Session(Recorder(ex, clock), mode=ExecutionMode.RECORD, clock=clock),
        tools=ToolRegistry(),
        model=None,
        sources=None,
        agent_name="a",
    )  # type: ignore[arg-type]
    with pytest.raises(ToolError):
        rt.call_tool("shell.exec", {"cmd": "rm -rf /"})
    assert ex.events[-1].error and "not registered" in ex.events[-1].error.message


def test_safe_join_rejects_traversal(tmp_path):
    for bad in ["../x.json", "/etc/passwd", "a/b.json", "..", "x\\..\\y", ""]:
        with pytest.raises(UnsafePathError):
            safe_join(tmp_path, bad)
    assert safe_join(tmp_path, "ok.trace.json").parent == tmp_path.resolve()


def test_executions_persist_across_store_instances(lab, tmp_path):
    db = tmp_path / "gr.sqlite3"
    store = SqliteStore(db)
    ex = lab.record("toy-bank", "naive")
    store.save(ex)
    store.close()
    again = SqliteStore(db)
    loaded = again.get(ex.id)
    assert loaded == ex
    assert again.list(app="toy")[0].id == ex.id


def test_trace_export_import_roundtrip_validates(lab, tmp_path):
    ex = lab.record("toy-bank", "naive")
    path = export_execution(ex, tmp_path)
    assert import_execution(tmp_path, path.name) == ex
    bad = tmp_path / "bad.trace.json"
    bad.write_text(json.dumps({"id": "x", "events": "__import__('os').system('echo pwned')"}))
    with pytest.raises(ValueError):
        import_execution(tmp_path, "bad.trace.json")
