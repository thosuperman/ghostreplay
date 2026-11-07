"""A simulated HTTP service: routes, deterministic latency and chaos rules."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..core.clock import Clock
from ..core.errors import (
    AuthError,
    HttpError,
    PermissionDenied,
    RateLimited,
    ToolError,
    ToolTimeout,
)


@dataclass
class HttpRequest:
    method: str
    path: str
    params: dict[str, str]
    json: Any
    headers: dict[str, str]

    def header(self, name: str) -> str | None:
        lname = name.lower()
        for k, v in self.headers.items():
            if k.lower() == lname:
                return v
        return None


@dataclass
class HttpResponse:
    status: int
    body: Any = None
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class ChaosRule:
    """Environment-level misbehaviour of the simulated service (part of the simulated world).

    ``commit_then_timeout``: the handler runs (side effect committed) and then the client sees
    a timeout — the classic ambiguous failure.
    """

    method: str
    path: str
    mode: str  # "commit_then_timeout" | "timeout" | "status"
    status: int = 500
    times: int = 1
    latency_ms: float = 30_000.0
    hits: int = 0


Handler = Callable[[HttpRequest], HttpResponse]


class MockHttpService:
    """In-memory HTTP API. No sockets are opened, ever."""

    def __init__(self, name: str, clock: Clock, *, base_latency_ms: float = 40.0) -> None:
        self.name = name
        self.clock = clock
        self.base_latency_ms = base_latency_ms
        self._routes: list[tuple[str, re.Pattern[str], Handler]] = []
        self.chaos: list[ChaosRule] = []
        self.request_log: list[dict[str, Any]] = []

    def route(self, method: str, pattern: str) -> Callable[[Handler], Handler]:
        regex = re.compile("^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", pattern) + "$")

        def deco(fn: Handler) -> Handler:
            self._routes.append((method.upper(), regex, fn))
            return fn

        return deco

    def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Perform a simulated request. Returns the body for 2xx, raises ``ToolError`` otherwise."""
        method = method.upper()
        req = HttpRequest(
            method, path, {k: str(v) for k, v in (params or {}).items()}, json, dict(headers or {})
        )
        self.clock.advance(self.base_latency_ms)
        rule = self._match_chaos(method, path)
        if rule is not None and rule.mode == "timeout":
            self.clock.advance(rule.latency_ms)
            self._log(req, None, "timeout")
            raise ToolTimeout(
                f"{self.name}: {method} {path} timed out after {rule.latency_ms:.0f} ms",
                data={"committed": False, "service": self.name},
            )
        if rule is not None and rule.mode == "status":
            self._log(req, rule.status, "chaos")
            raise _status_error(self.name, method, path, rule.status, {"error": "chaos"})

        response = self._dispatch(req)
        if rule is not None and rule.mode == "commit_then_timeout":
            self.clock.advance(rule.latency_ms)
            self._log(req, response.status, "committed_then_timeout")
            raise ToolTimeout(
                f"{self.name}: {method} {path} timed out after {rule.latency_ms:.0f} ms "
                "(no response received)",
                data={"service": self.name},
            )
        self._log(req, response.status, "ok")
        if response.status >= 400:
            raise _status_error(self.name, method, path, response.status, response.body)
        return response.body

    def _dispatch(self, req: HttpRequest) -> HttpResponse:
        for method, regex, handler in self._routes:
            m = regex.match(req.path)
            if m and method == req.method:
                req.params.update(m.groupdict())
                return handler(req)
        return HttpResponse(404, {"error": f"no route for {req.method} {req.path}"})

    def _match_chaos(self, method: str, path: str) -> ChaosRule | None:
        for rule in self.chaos:
            if rule.method == method and rule.path == path and rule.hits < rule.times:
                rule.hits += 1
                return rule
        return None

    def _log(self, req: HttpRequest, status: int | None, outcome: str) -> None:
        self.request_log.append(
            {
                "method": req.method,
                "path": req.path,
                "status": status,
                "outcome": outcome,
                "at": self.clock.now().isoformat(),
            }
        )


def _status_error(service: str, method: str, path: str, status: int, body: Any) -> ToolError:
    msg = f"{service}: {method} {path} -> HTTP {status}"
    data = {"status": status, "body": body, "service": service}
    if status == 429:
        return RateLimited(msg, data=data)
    if status == 401:
        return AuthError(msg, data=data)
    if status == 403:
        return PermissionDenied(msg, data=data)
    return HttpError(msg, retryable=status >= 500, data=data)
