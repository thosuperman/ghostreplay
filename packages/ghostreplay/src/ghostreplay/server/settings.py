"""Server settings, including the hardened profile used for public deployments.

Local development keeps everything open on 127.0.0.1. ``GHOSTREPLAY_PUBLIC=1`` switches to a
profile meant for an internet-facing demo:

* POST/DELETE and replay streams are rate-limited per client address;
* at most ``max_concurrent_runs`` engine runs execute at once (others get HTTP 503);
* request bodies are capped;
* clearing all executions is disabled (other visitors share the store);
* live-LLM mode is disabled regardless of ``GHOSTREPLAY_LIVE``;
* stored executions are capped per lab (oldest pruned);
* each visitor gets an anonymous session cookie and only ever sees the executions created
  in that session; those executions expire after ``session_ttl_s``;
* the replay stream's per-event delay is capped so one visitor cannot hold a run slot;
* the interactive API docs (``/docs``, ``/openapi.json``) are not served.

Nothing the API accepts can run commands or reach real services: tools are allowlisted
in-memory simulations and request bodies are validated data.
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from collections.abc import Mapping
from dataclasses import dataclass, field

LOCAL_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
)


def _flag(env: Mapping[str, str], name: str) -> bool:
    return env.get(name, "").strip().lower() in ("1", "true", "yes")


@dataclass(frozen=True)
class ServerSettings:
    public: bool = False
    allow_origins: tuple[str, ...] = LOCAL_ORIGINS
    max_body_bytes: int = 5 * 1024 * 1024
    rate_limit_per_minute: int = 0  # 0 disables rate limiting
    max_concurrent_runs: int = 0  # 0 means unlimited
    allow_clear: bool = True
    allow_live: bool = True
    max_executions: int | None = None
    trust_forwarded_for: bool = False
    isolate_sessions: bool = False
    session_ttl_s: float = 24 * 3600
    max_executions_per_session: int | None = None
    cookie_secure: bool = False
    max_stream_delay_ms: int = 2000
    expose_docs: bool = True

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> ServerSettings:
        env = os.environ if env is None else env
        public = _flag(env, "GHOSTREPLAY_PUBLIC")
        origins = tuple(
            o.strip() for o in env.get("GHOSTREPLAY_CORS_ORIGINS", "").split(",") if o.strip()
        )
        if not public:
            return cls(allow_origins=origins or LOCAL_ORIGINS)
        return cls(
            public=True,
            allow_origins=origins,
            max_body_bytes=int(env.get("GHOSTREPLAY_MAX_BODY_BYTES", 512 * 1024)),
            rate_limit_per_minute=int(env.get("GHOSTREPLAY_RATE_LIMIT_PER_MINUTE", 30)),
            max_concurrent_runs=int(env.get("GHOSTREPLAY_MAX_CONCURRENT_RUNS", 2)),
            allow_clear=False,
            allow_live=False,
            max_executions=int(env.get("GHOSTREPLAY_MAX_EXECUTIONS", 2000)),
            trust_forwarded_for=_flag(env, "GHOSTREPLAY_TRUST_PROXY"),
            isolate_sessions=env.get("GHOSTREPLAY_SESSION_ISOLATION", "1").strip() != "0",
            session_ttl_s=float(env.get("GHOSTREPLAY_SESSION_TTL_HOURS", 24)) * 3600,
            max_executions_per_session=int(env.get("GHOSTREPLAY_MAX_EXECUTIONS_PER_SESSION", 80)),
            cookie_secure=not _flag(env, "GHOSTREPLAY_INSECURE_COOKIES"),
            max_stream_delay_ms=int(env.get("GHOSTREPLAY_MAX_STREAM_DELAY_MS", 400)),
            expose_docs=False,
        )


@dataclass
class RateLimiter:
    """Sliding-window limiter keyed by client address (in-process; one per server)."""

    per_minute: int
    window_s: float = 60.0
    _hits: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def allow(self, key: str, now: float | None = None) -> tuple[bool, float]:
        """Return ``(allowed, retry_after_seconds)``."""
        if self.per_minute <= 0:
            return True, 0.0
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self.window_s:
                hits.popleft()
            if len(hits) >= self.per_minute:
                return False, self.window_s - (now - hits[0])
            hits.append(now)
            if len(self._hits) > 10_000:  # bound memory under address churn
                for k in [k for k, v in self._hits.items() if not v]:
                    del self._hits[k]
            return True, 0.0
