"""FastAPI app factory: the HTTP API every lab exposes to the dashboard."""

from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from .. import __version__
from ..core.errors import ExecutionNotFound, GhostReplayError
from ..diff import diff_executions
from ..models import Event, FaultSpec
from ..mutation import CATALOG
from ..regression.cases import RegressionCase

if TYPE_CHECKING:
    from ..lab import Lab


class RecordRequest(BaseModel):
    scenario: str
    variant: str
    conditions: dict[str, str] = Field(default_factory=dict)
    title: str = Field(default="", max_length=200)


class CounterfactualRequest(BaseModel):
    execution_id: str
    faults: list[FaultSpec] = Field(default_factory=list, max_length=20)
    preset: str | None = None
    variant: str | None = None
    mode: Literal["auto", "replay", "branch"] = "auto"
    title: str = Field(default="", max_length=200)


class ReplayRequest(BaseModel):
    execution_id: str


class DemoRequest(BaseModel):
    scenario: str
    preset: str | None = None


class CaseFromExecution(BaseModel):
    execution_id: str
    variant: str | None = None
    expect: Literal["pass", "fail"] | None = None


class RunCasesRequest(BaseModel):
    execution_id: str | None = None
    variants: list[str] = Field(default_factory=list)
    case: RegressionCase | None = None


LOCAL_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]


def create_app(
    lab: Lab, *, dashboard_dir: str | Path | None = None, title: str | None = None
) -> FastAPI:
    app = FastAPI(title=title or f"GhostReplay Lab — {lab.app}", version=__version__)
    app.add_middleware(
        CORSMiddleware, allow_origins=LOCAL_ORIGINS, allow_methods=["*"], allow_headers=["*"]
    )

    def get_execution(execution_id: str):
        try:
            return lab.store.get(execution_id)
        except ExecutionNotFound as exc:
            raise HTTPException(404, str(exc)) from None

    def guarded(fn, *args: Any, **kwargs: Any):
        try:
            return fn(*args, **kwargs)
        except ExecutionNotFound as exc:
            raise HTTPException(404, str(exc)) from None
        except (ValueError, GhostReplayError) as exc:
            raise HTTPException(400, str(exc)) from None

    @app.get("/api/info")
    def info() -> dict[str, Any]:
        return {
            "app": lab.app,
            "version": __version__,
            "schema_version": "ghostreplay/v1",
            "scenarios": [{"id": s.id, "title": s.title} for s in lab.scenarios.values()],
            "offline": True,
            "storage": lab.store.path,
        }

    @app.get("/api/scenarios")
    def scenarios() -> list[dict[str, Any]]:
        return [s.describe() for s in lab.scenarios.values()]

    @app.get("/api/faults")
    def faults() -> list[dict[str, Any]]:
        return [k.to_dict() for k in CATALOG.values()]

    @app.get("/api/executions")
    def executions(scenario: str | None = None, limit: int = Query(100, ge=1, le=500)):
        return [
            s.model_dump(mode="json")
            for s in lab.store.list(app=lab.app, scenario=scenario, limit=limit)
        ]

    @app.get("/api/executions/{execution_id}")
    def execution(execution_id: str) -> dict[str, Any]:
        ex = get_execution(execution_id)
        return {**ex.model_dump(mode="json"), "summary": ex.summary().model_dump(mode="json")}

    @app.delete("/api/executions")
    def clear() -> dict[str, int]:
        return {"deleted": lab.store.delete_all(app=lab.app)}

    @app.post("/api/runs/record")
    def record(req: RecordRequest) -> dict[str, Any]:
        ex = guarded(
            lab.record,
            req.scenario,
            req.variant,
            conditions=req.conditions,
            title=req.title or f"Recorded run ({req.variant})",
        )
        return ex.summary().model_dump(mode="json")

    @app.post("/api/runs/replay")
    def replay(req: ReplayRequest) -> dict[str, Any]:
        ex = guarded(lab.replay, req.execution_id)
        ref = get_execution(req.execution_id)
        return {
            "execution": ex.summary().model_dump(mode="json"),
            "diff": diff_executions(ref, ex).model_dump(mode="json"),
        }

    @app.post("/api/runs/counterfactual")
    def counterfactual(req: CounterfactualRequest) -> dict[str, Any]:
        ref = get_execution(req.execution_id)
        faults = list(req.faults)
        if req.preset:
            faults = guarded(lambda: lab.scenario(ref.scenario).preset(req.preset).faults) + faults
        if not faults:
            raise HTTPException(400, "at least one fault (or a preset) is required")
        ex = guarded(
            lab.counterfactual,
            req.execution_id,
            faults,
            variant=req.variant,
            mode=req.mode,
            title=req.title,
        )
        return {
            "execution": ex.summary().model_dump(mode="json"),
            "diff": diff_executions(ref, ex).model_dump(mode="json"),
        }

    @app.get("/api/diff")
    def diff(a: str, b: str) -> dict[str, Any]:
        return guarded(lab.diff, a, b).model_dump(mode="json")

    @app.post("/api/demo/prepare")
    def demo(req: DemoRequest) -> dict[str, Any]:
        return guarded(lab.prepare_demo, req.scenario, req.preset).model_dump(mode="json")

    @app.post("/api/regression/export")
    def export(req: CaseFromExecution) -> dict[str, Any]:
        return guarded(lab.export_case, req.execution_id, variant=req.variant, expect=req.expect)

    @app.post("/api/regression/run")
    def run_cases(req: RunCasesRequest) -> list[dict[str, Any]]:
        cases: list[RegressionCase] = []
        if req.case is not None:
            cases.append(req.case)
        if req.execution_id:
            ex = get_execution(req.execution_id)
            sc = guarded(lab.scenario, ex.scenario)
            variants = req.variants or [v.id for v in sc.variants]
            cases += [
                guarded(lab.case_from_execution, req.execution_id, variant=v) for v in variants
            ]
        if not cases:
            raise HTTPException(400, "provide execution_id or case")
        return [guarded(lab.run_case, c).model_dump(mode="json") for c in cases]

    @app.get("/api/executions/{execution_id}/replay/stream")
    def replay_stream(execution_id: str, delay_ms: int = Query(220, ge=0, le=2000)):
        """Server-Sent Events: each event is emitted as the replay engine records it.

        ``delay_ms`` slows the engine itself (the listener sleeps inside the replay thread),
        so the UI animation is paced by real engine activity, not a canned animation.
        """
        ref = get_execution(execution_id)
        q: queue.Queue[tuple[str, Any] | None] = queue.Queue()

        def listener(ev: Event) -> None:
            q.put(("event", ev.model_dump(mode="json")))
            if delay_ms:
                time.sleep(delay_ms / 1000)

        def worker() -> None:
            try:
                ex = lab.replay(execution_id, listeners=[listener])
                d = diff_executions(ref, ex)
                q.put(
                    (
                        "done",
                        {
                            "execution": ex.summary().model_dump(mode="json"),
                            "diff": d.model_dump(mode="json"),
                        },
                    )
                )
            except Exception as exc:  # report to the client instead of hanging the stream
                q.put(("error", {"message": f"{type(exc).__name__}: {exc}"}))
            finally:
                q.put(None)

        threading.Thread(target=worker, daemon=True).start()

        def gen():
            yield "event: start\ndata: " + json.dumps({"reference": execution_id}) + "\n\n"
            while True:
                item = q.get()
                if item is None:
                    break
                kind, payload = item
                yield f"event: {kind}\ndata: {json.dumps(payload)}\n\n"

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    if dashboard_dir is not None and Path(dashboard_dir).is_dir():
        root = Path(dashboard_dir).resolve()

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            candidate = (root / path).resolve()
            if path and candidate.is_file() and root in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(root / "index.html")

    return app
