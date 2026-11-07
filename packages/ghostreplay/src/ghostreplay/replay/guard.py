"""Offline guard: blocks outbound network access from a thread during offline replay.

The guard patches ``socket`` once per process, but the patched functions only refuse when
the *calling thread* is inside :func:`offline_guard`. A lab server can therefore keep
serving HTTP on other threads while a replay runs.
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from ..core.errors import OfflineViolation

_state = threading.local()
_install_lock = threading.Lock()
_installed = False


def is_offline() -> bool:
    return getattr(_state, "depth", 0) > 0


def _wrap(original: Callable[..., Any], what: str) -> Callable[..., Any]:
    def guarded(*args: Any, **kwargs: Any) -> Any:
        if is_offline():
            raise OfflineViolation(f"network access via {what} blocked during offline replay")
        return original(*args, **kwargs)

    guarded.__wrapped__ = original  # type: ignore[attr-defined]
    return guarded


def _install() -> None:
    global _installed
    with _install_lock:
        if _installed:
            return
        socket.socket.connect = _wrap(socket.socket.connect, "socket.connect")  # type: ignore[method-assign]
        socket.socket.connect_ex = _wrap(socket.socket.connect_ex, "socket.connect_ex")  # type: ignore[method-assign]
        socket.create_connection = _wrap(socket.create_connection, "socket.create_connection")
        socket.getaddrinfo = _wrap(socket.getaddrinfo, "socket.getaddrinfo")
        _installed = True


@contextmanager
def offline_guard() -> Iterator[None]:
    """Inside this context the current thread cannot open network connections."""
    _install()
    _state.depth = getattr(_state, "depth", 0) + 1
    try:
        yield
    finally:
        _state.depth -= 1
