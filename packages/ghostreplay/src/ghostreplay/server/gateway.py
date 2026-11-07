"""One-process deployment: every installed lab plus the built dashboard behind one port.

Each lab app registers a ``build_lab(store)`` factory under the ``ghostreplay.labs`` entry
point group. The gateway mounts each lab's API at ``/lab/<name>`` (the same paths the Vite
dev server proxies) and serves the dashboard build at ``/``. The labs stay independent
applications; the gateway only hosts them side by side.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from .. import __version__
from ..lab import Lab
from ..llm import LiveModelConfig
from ..storage import SqliteStore
from .app import create_app
from .settings import ServerSettings

LAB_ENTRY_POINT_GROUP = "ghostreplay.labs"
LabFactory = Callable[[SqliteStore], Lab]


def discover_labs() -> dict[str, LabFactory]:
    return {ep.name: ep.load() for ep in entry_points(group=LAB_ENTRY_POINT_GROUP)}


def create_gateway(
    *,
    db_dir: str | Path,
    dashboard_dir: str | Path | None = None,
    settings: ServerSettings | None = None,
    labs: dict[str, LabFactory] | None = None,
) -> FastAPI:
    settings = settings or ServerSettings.from_env()
    factories = labs if labs is not None else discover_labs()
    if not factories:
        raise RuntimeError(f"no labs installed (entry point group {LAB_ENTRY_POINT_GROUP!r})")
    gateway = FastAPI(title="GhostReplay Lab", version=__version__, docs_url=None)
    mounted: dict[str, Lab] = {}
    for name, factory in sorted(factories.items()):
        store = (
            SqliteStore(":memory:", max_executions=settings.max_executions)
            if str(db_dir) == ":memory:"
            else SqliteStore(
                Path(db_dir) / f"{name}.sqlite3", max_executions=settings.max_executions
            )
        )
        lab = factory(store)
        lab.live = LiveModelConfig.from_env() if settings.allow_live else None
        gateway.mount(f"/lab/{name}", create_app(lab, settings=settings))
        mounted[name] = lab

    @gateway.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, Any]:
        return {"status": "ok", "labs": sorted(mounted)}

    @gateway.get("/api/health")
    def health() -> dict[str, Any]:
        status = {}
        for name, lab in mounted.items():
            try:
                status[name] = "ok" if lab.store.ping() else "degraded"
            except Exception:
                status[name] = "unavailable"
        if any(v != "ok" for v in status.values()):
            raise HTTPException(503, {"labs": status})
        return {"status": "ok", "version": __version__, "labs": status}

    if dashboard_dir is not None and Path(dashboard_dir, "index.html").is_file():
        root = Path(dashboard_dir).resolve()
        index = root / "index.html"

        @gateway.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            candidate = (root / path).resolve()
            if path and candidate.is_file() and root in candidate.parents:
                headers = (
                    {"Cache-Control": "public, max-age=31536000, immutable"}
                    if path.startswith("assets/")
                    else None
                )
                return FileResponse(candidate, headers=headers)
            return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return gateway
