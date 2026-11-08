"""Building blocks for *real* local test services used by GhostReplay labs.

``LocalService`` is a genuine HTTP server (stdlib ``ThreadingHTTPServer``) bound to
127.0.0.1 on an ephemeral port. ``http_json`` is a genuine HTTP client with a socket timeout
that maps transport failures and status codes onto GhostReplay's replayable ``ToolError``
family. Requests really travel over the loopback network; nothing here is simulated.

Labs use them to run disposable services (a refund API, an instance fleet) per execution:
start them when a world is built, stop them when the execution ends.
"""

from __future__ import annotations

import json
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .core.errors import AuthError, HttpError, PermissionDenied, RateLimited, ToolError, ToolTimeout

MAX_BODY = 256 * 1024


@dataclass
class Request:
    method: str
    path: str
    params: dict[str, str]
    headers: dict[str, str]
    json: Any
    path_params: dict[str, str] = field(default_factory=dict)

    def header(self, name: str) -> str | None:
        return self.headers.get(name.lower())


@dataclass
class Response:
    status: int
    body: Any
    headers: dict[str, str] = field(default_factory=dict)
    #: Seconds to wait *after* the handler ran (and committed) before sending the response.
    delay_s: float = 0.0


Handler = Callable[[Request], Response]


class LocalService:
    """A real HTTP service on 127.0.0.1:<ephemeral port>, served from a background thread."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._routes: list[tuple[str, re.Pattern[str], Handler]] = []
        self.requests: list[dict[str, Any]] = []  # what actually arrived over the network
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # -- routing ---------------------------------------------------------------------------
    def route(self, method: str, pattern: str) -> Callable[[Handler], Handler]:
        regex = re.compile("^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", pattern) + "$")

        def deco(fn: Handler) -> Handler:
            self._routes.append((method.upper(), regex, fn))
            return fn

        return deco

    def _dispatch(self, req: Request) -> Response:
        for method, regex, fn in self._routes:
            m = regex.match(req.path)
            if m and method == req.method:
                req.path_params = m.groupdict()
                return fn(req)
        return Response(404, {"error": "not_found", "path": req.path})

    # -- lifecycle --------------------------------------------------------------------------
    @property
    def url(self) -> str:
        assert self._server is not None, "service not started"
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    @property
    def running(self) -> bool:
        return self._server is not None

    def start(self) -> LocalService:
        service = self

        class _H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_a: Any) -> None:  # keep test and server logs quiet
                return None

            def _handle(self) -> None:
                parsed = urllib.parse.urlsplit(self.path)
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_BODY:
                    self._send(Response(413, {"error": "body_too_large"}))
                    return
                raw = self.rfile.read(length) if length else b""
                try:
                    body = json.loads(raw) if raw else None
                except ValueError:
                    self._send(Response(400, {"error": "invalid_json"}))
                    return
                req = Request(
                    method=self.command,
                    path=parsed.path,
                    params=dict(urllib.parse.parse_qsl(parsed.query)),
                    headers={k.lower(): v for k, v in self.headers.items()},
                    json=body,
                )
                try:
                    resp = service._dispatch(req)
                except Exception as exc:  # a bug in the lab service: report it, don't hang
                    resp = Response(500, {"error": "internal_error", "detail": type(exc).__name__})
                with service._lock:
                    service.requests.append(
                        {"method": req.method, "path": req.path, "status": resp.status}
                    )
                if resp.delay_s:
                    time.sleep(resp.delay_s)
                self._send(resp)

            def _send(self, resp: Response) -> None:
                data = json.dumps(resp.body).encode()
                try:
                    self.send_response(resp.status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    for k, v in resp.headers.items():
                        self.send_header(k, v)
                    self.end_headers()
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass  # the client gave up (e.g. after its timeout); the work is already done

            do_GET = do_POST = do_PUT = do_DELETE = _handle

        server = ThreadingHTTPServer(("127.0.0.1", 0), _H)
        server.daemon_threads = True
        self._server = server
        self._thread = threading.Thread(
            target=server.serve_forever, name=f"labkit:{self.name}", daemon=True
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None


def http_json(
    method: str,
    url: str,
    *,
    service: str,
    json_body: Any = None,
    headers: dict[str, str] | None = None,
    timeout_s: float = 5.0,
) -> Any:
    """Make a real HTTP request and return the decoded JSON body of a 2xx response.

    Raises ``ToolTimeout`` when no response arrives within ``timeout_s`` (the server may still
    have done the work: that is the ambiguity this toolkit exists to reproduce), ``HttpError``
    and friends for error statuses, and ``HttpError`` for connection failures.
    """
    data = json.dumps(json_body).encode() if json_body is not None else None
    req = urllib.request.Request(url, data=data, method=method.upper())
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    path = urllib.parse.urlsplit(url).path
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read() or b"null")
        except ValueError:
            body = None
        raise _status_error(service, method, path, exc.code, body) from None
    except TimeoutError:
        raise ToolTimeout(
            f"{service}: {method} {path} timed out after {round(timeout_s * 1000)} ms "
            "(no response received)",
            data={"service": service, "timeout_ms": round(timeout_s * 1000)},
        ) from None
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError | socket.timeout):
            raise ToolTimeout(
                f"{service}: {method} {path} timed out after {round(timeout_s * 1000)} ms "
                "(no response received)",
                data={"service": service, "timeout_ms": round(timeout_s * 1000)},
            ) from None
        raise HttpError(
            f"{service}: {method} {path} -> connection failed ({exc.reason})",
            retryable=True,
            data={"service": service, "status": None},
        ) from None


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


__all__ = ["LocalService", "Request", "Response", "http_json"]
