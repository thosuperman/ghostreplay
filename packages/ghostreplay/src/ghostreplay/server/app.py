"""FastAPI app factory: the HTTP API every lab exposes to the dashboard."""

from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import queue
import re
import secrets
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .. import __version__
from ..core.errors import ExecutionNotFound, GhostReplayError, TraceFormatError
from ..diff import diff_executions
from ..models import Event, Execution, FaultSpec
from ..mutation import CATALOG
from ..recorder import Redactor
from ..regression.cases import RegressionCase
from ..storage import OwnershipConflict
from ..storage.parsing import parse_document
from .settings import RateLimiter, ServerSettings

if TYPE_CHECKING:
    from ..lab import Lab


class RecordRequest(BaseModel):
    scenario: str
    variant: str
    conditions: dict[str, str] = Field(default_factory=dict)
    title: str = Field(default="", max_length=200)
    model: Literal["scripted", "live"] = "scripted"


class CounterfactualRequest(BaseModel):
    execution_id: str
    faults: list[FaultSpec] = Field(default_factory=list, max_length=20)
    preset: str | None = None
    variant: str | None = None
    mode: Literal["auto", "replay", "branch"] = "auto"
    title: str = Field(default="", max_length=200)


class ReplayRequest(BaseModel):
    execution_id: str


class ReexecuteRequest(BaseModel):
    execution_id: str
    title: str = Field(default="", max_length=200)


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


RUN_PATH_SUFFIXES = ("/replay/stream",)
MAX_IMPORT_EVENTS = 5000


def redact_execution(ex: Execution) -> Execution:
    """Re-apply secret redaction to every payload of an imported trace.

    Traces produced by GhostReplay are already redacted; an uploaded file is untrusted, so the
    server redacts again before storing anything.
    """
    r = Redactor()
    data = ex.model_dump(mode="json")
    for key in ("task", "final_state", "output", "conditions"):
        data[key] = r.redact(data.get(key))
    for ev in data["events"]:
        for key in ("request", "response", "state_before", "state_after", "metadata", "error"):
            ev[key] = r.redact(ev.get(key))
    return Execution.model_validate(data)


SESSION_COOKIE = "gr_session"
_SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")


def session_owner(session_id: str) -> str:
    """The owner key stored with a visitor's executions (the cookie itself is never stored)."""
    return hashlib.sha256(session_id.encode()).hexdigest()[:32]


def create_app(
    lab: Lab,
    *,
    dashboard_dir: str | Path | None = None,
    title: str | None = None,
    settings: ServerSettings | None = None,
) -> FastAPI:
    settings = settings or ServerSettings()
    if not settings.allow_live:
        lab.live = None
    if settings.max_executions:
        lab.store.max_executions = settings.max_executions
    if settings.isolate_sessions:
        lab.store.owner_ttl_s = settings.session_ttl_s
        lab.store.max_per_owner = settings.max_executions_per_session
    library_ids: list[str] = []
    if settings.load_library and getattr(lab, "library_dir", None) is not None:
        from ..storage.library import load_library

        base = lab.store.base if hasattr(lab.store, "base") else lab.store
        library_ids = load_library(base, lab.library_dir)
    docs = settings.expose_docs
    app = FastAPI(
        title=title or f"GhostReplay Lab — {lab.app}",
        version=__version__,
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )
    if settings.allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.allow_origins),
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Content-Type"],
        )
    limiter = RateLimiter(settings.rate_limit_per_minute)
    runs = (
        threading.BoundedSemaphore(settings.max_concurrent_runs)
        if settings.max_concurrent_runs
        else None
    )

    def client_key(request: Request) -> str:
        if settings.trust_forwarded_for:
            fwd = request.headers.get("x-forwarded-for", "")
            if fwd:
                return fwd.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    @app.middleware("http")
    async def limits(request: Request, call_next):
        new_session: str | None = None
        if settings.isolate_sessions:
            sid = request.cookies.get(SESSION_COOKIE, "")
            if not _SESSION_RE.fullmatch(sid):
                sid = new_session = secrets.token_urlsafe(32)
            request.state.owner = session_owner(sid)
        mutating = request.method in ("POST", "PUT", "PATCH", "DELETE")
        if mutating:
            length = request.headers.get("content-length")
            if length is None and settings.public and request.method != "DELETE":
                return JSONResponse({"detail": "Content-Length required"}, status_code=411)
            if length is not None and int(length) > settings.max_body_bytes:
                return JSONResponse(
                    {"detail": f"request body exceeds {settings.max_body_bytes} bytes"},
                    status_code=413,
                )
        if mutating or request.url.path.endswith(RUN_PATH_SUFFIXES):
            ok, retry = limiter.allow(client_key(request))
            if not ok:
                return JSONResponse(
                    {"detail": "rate limit exceeded; try again shortly"},
                    status_code=429,
                    headers={"Retry-After": str(max(1, int(retry)))},
                )
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        if new_session is not None:
            response.set_cookie(
                SESSION_COOKIE,
                new_session,
                max_age=int(settings.session_ttl_s),
                httponly=True,
                secure=settings.cookie_secure,
                samesite="lax",
                path="/",
            )
        return response

    def lab_for(request: Request) -> Lab:
        """The lab as seen by this request: scoped to the visitor's session when isolated."""
        owner = getattr(request.state, "owner", None)
        if owner is None:
            return lab
        scoped = copy.copy(lab)
        scoped.store = lab.store.scoped(owner)
        return scoped

    @contextlib.contextmanager
    def run_slot() -> Iterator[None]:
        if runs is None:
            yield
            return
        if not runs.acquire(timeout=5):
            raise HTTPException(503, "the lab is busy running other executions; retry shortly")
        try:
            yield
        finally:
            runs.release()

    def get_execution(lab: Lab, execution_id: str):
        try:
            return lab.store.get(execution_id)
        except ExecutionNotFound as exc:
            raise HTTPException(404, str(exc)) from None

    def guarded(fn, *args: Any, **kwargs: Any):
        try:
            with run_slot():
                return fn(*args, **kwargs)
        except ExecutionNotFound as exc:
            raise HTTPException(404, str(exc)) from None
        except (ValueError, GhostReplayError) as exc:
            raise HTTPException(400, str(exc)) from None

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        """Liveness: the process is up."""
        return {"status": "ok"}

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        """Readiness: the store answers queries."""
        try:
            ok = lab.store.ping()
        except Exception as exc:  # report, don't crash the probe
            raise HTTPException(503, f"store unavailable: {type(exc).__name__}") from None
        return {
            "status": "ok" if ok else "degraded",
            "app": lab.app,
            "version": __version__,
            "executions": lab.store.count(app=lab.app),
        }

    @app.get("/api/info")
    def info() -> dict[str, Any]:
        live = lab.live.describe() if lab.live is not None else None
        return {
            "app": lab.app,
            "version": __version__,
            "schema_version": "ghostreplay/v1",
            "scenarios": [{"id": s.id, "title": s.title} for s in lab.scenarios.values()],
            "offline": True,
            "public": settings.public,
            "can_clear": settings.allow_clear,
            "live_model": live,
            "storage": "sqlite" if settings.public else lab.store.path,
            "isolated_sessions": settings.isolate_sessions,
            "session_ttl_hours": (
                round(settings.session_ttl_s / 3600, 2) if settings.isolate_sessions else None
            ),
        }

    @app.get("/api/scenarios")
    def scenarios() -> list[dict[str, Any]]:
        return [s.describe() for s in lab.scenarios.values()]

    @app.get("/api/faults")
    def faults() -> list[dict[str, Any]]:
        return [k.to_dict() for k in CATALOG.values()]

    @app.get("/api/executions")
    def executions(
        request: Request,
        scenario: str | None = None,
        limit: int = Query(100, ge=1, le=500),
        imported: bool = False,
    ):
        """This lab's executions, or with ``imported=true`` the traces imported from other apps."""
        lab = lab_for(request)
        if imported:
            rows = [s for s in lab.store.list(limit=limit) if s.app != lab.app]
        else:
            rows = lab.store.list(app=lab.app, scenario=scenario, limit=limit)
        return [s.model_dump(mode="json") for s in rows]

    @app.get("/api/executions/{execution_id}")
    def execution(execution_id: str, request: Request) -> dict[str, Any]:
        ex = get_execution(lab_for(request), execution_id)
        return {**ex.model_dump(mode="json"), "summary": ex.summary().model_dump(mode="json")}

    @app.get("/api/executions/{execution_id}/trace")
    def download_trace(execution_id: str, request: Request) -> JSONResponse:
        """The execution as a portable, versioned trace file (already redacted)."""
        ex = get_execution(lab_for(request), execution_id)
        return JSONResponse(
            ex.model_dump(mode="json"),
            headers={"Content-Disposition": f'attachment; filename="{ex.id}.trace.json"'},
        )

    @app.post("/api/traces/import")
    async def import_trace(request: Request) -> dict[str, Any]:
        """Store an uploaded trace for inspection (data only: nothing in it is executed).

        The body is validated against the trace schema, re-redacted, capped in size and
        event count, and stored in the caller's own session like any other execution. A trace
        is replayable on this server only if it belongs to a scenario this lab runs.
        """
        raw = await request.body()
        if len(raw) > settings.max_body_bytes:
            raise HTTPException(413, f"trace exceeds {settings.max_body_bytes} bytes")
        try:
            ex = parse_document(Execution, raw, source="uploaded trace")
        except TraceFormatError as exc:
            raise HTTPException(422, str(exc)) from None
        if len(ex.events) > MAX_IMPORT_EVENTS:
            raise HTTPException(422, f"trace has more than {MAX_IMPORT_EVENTS} events")
        ex = redact_execution(ex)
        lab = lab_for(request)
        try:
            lab.store.save(ex)
        except OwnershipConflict:
            raise HTTPException(
                409, "a trace with this id already exists in another session"
            ) from None
        replayable = ex.scenario in lab.scenarios and ex.app == lab.app
        return {
            "execution": ex.summary().model_dump(mode="json"),
            "replayable_here": replayable,
            "note": (
                "This trace belongs to a scenario this lab runs, so it can be replayed here."
                if replayable
                else "Stored for inspection only. Replaying it needs the agent code that "
                "produced it: run `ghostreplay replay TRACE --app your_module:ghost` locally."
            ),
        }

    @app.delete("/api/executions")
    def clear(request: Request) -> dict[str, int]:
        if not settings.allow_clear:
            raise HTTPException(403, "clearing executions is disabled on this deployment")
        return {"deleted": lab_for(request).store.delete_all(app=lab.app)}

    @app.post("/api/runs/record")
    def record(req: RecordRequest, request: Request) -> dict[str, Any]:
        lab = lab_for(request)
        ex = guarded(
            lab.record,
            req.scenario,
            req.variant,
            conditions=req.conditions,
            title=req.title or f"Recorded run ({req.variant}, {req.model} model)",
            model=req.model,
        )
        return ex.summary().model_dump(mode="json")

    @app.get("/api/library")
    def library() -> dict[str, Any]:
        """Genuine captures shipped with this lab (shared, read-only for every session)."""
        from ..storage.library import library_manifest

        items = []
        for eid in library_ids:
            try:
                ex = lab.store.get(eid)
            except ExecutionNotFound:
                continue
            items.append(
                {
                    **ex.summary().model_dump(mode="json"),
                    "provider": ex.provenance.model_provider,
                    "model": ex.provenance.model,
                    "model_is_live": ex.provenance.model_is_live,
                    "provenance": ex.provenance.label,
                    "conditions": ex.conditions,
                    "faults": [f.model_dump(mode="json") for f in ex.faults],
                }
            )
        return {"manifest": library_manifest(getattr(lab, "library_dir", None)), "captures": items}

    @app.post("/api/runs/reexecute")
    def reexecute(req: ReexecuteRequest, request: Request) -> dict[str, Any]:
        """Run a recording again for real (same code, live tools, recorded model decisions)."""
        lab = lab_for(request)
        ref = get_execution(lab, req.execution_id)
        ex = guarded(lab.reexecute, req.execution_id, title=req.title)
        return {
            "execution": ex.summary().model_dump(mode="json"),
            "diff": diff_executions(ref, ex).model_dump(mode="json"),
        }

    @app.post("/api/runs/replay")
    def replay(req: ReplayRequest, request: Request) -> dict[str, Any]:
        lab = lab_for(request)
        ex = guarded(lab.replay, req.execution_id)
        ref = get_execution(lab, req.execution_id)
        return {
            "execution": ex.summary().model_dump(mode="json"),
            "diff": diff_executions(ref, ex).model_dump(mode="json"),
        }

    @app.post("/api/runs/counterfactual")
    def counterfactual(req: CounterfactualRequest, request: Request) -> dict[str, Any]:
        lab = lab_for(request)
        ref = get_execution(lab, req.execution_id)
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
    def diff(a: str, b: str, request: Request) -> dict[str, Any]:
        return guarded(lab_for(request).diff, a, b).model_dump(mode="json")

    @app.post("/api/demo/prepare")
    def demo(req: DemoRequest, request: Request) -> dict[str, Any]:
        return guarded(lab_for(request).prepare_demo, req.scenario, req.preset).model_dump(
            mode="json"
        )

    @app.post("/api/regression/export")
    def export(req: CaseFromExecution, request: Request) -> dict[str, Any]:
        return guarded(
            lab_for(request).export_case, req.execution_id, variant=req.variant, expect=req.expect
        )

    @app.post("/api/regression/run")
    def run_cases(req: RunCasesRequest, request: Request) -> list[dict[str, Any]]:
        lab = lab_for(request)
        cases: list[RegressionCase] = []
        if req.case is not None:
            cases.append(req.case)
        if req.execution_id:
            ex = get_execution(lab, req.execution_id)
            sc = guarded(lab.scenario, ex.scenario)
            variants = req.variants or [v.id for v in sc.variants]
            cases += [
                guarded(lab.case_from_execution, req.execution_id, variant=v) for v in variants
            ]
        if not cases:
            raise HTTPException(400, "provide execution_id or case")
        return [guarded(lab.run_case, c).model_dump(mode="json") for c in cases]

    @app.get("/api/executions/{execution_id}/replay/stream")
    def replay_stream(
        execution_id: str, request: Request, delay_ms: int = Query(220, ge=0, le=2000)
    ):
        """Server-Sent Events: each event is emitted as the replay engine records it.

        ``delay_ms`` slows the engine itself (the listener sleeps inside the replay thread),
        so the UI animation is paced by real engine activity, not a canned animation.
        """
        lab = lab_for(request)
        delay_ms = min(delay_ms, settings.max_stream_delay_ms)
        ref = get_execution(lab, execution_id)
        if runs is not None and not runs.acquire(timeout=5):
            raise HTTPException(503, "the lab is busy running other executions; retry shortly")
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
                if runs is not None:
                    runs.release()
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
