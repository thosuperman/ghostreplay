"""Clocks and deterministic sources of nondeterminism."""

from __future__ import annotations

import hashlib
import random
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Protocol

DEFAULT_EPOCH = datetime(2026, 10, 31, 9, 0, 0, tzinfo=UTC)


class Clock(Protocol):
    virtual: bool

    def now(self) -> datetime: ...

    def monotonic_ms(self) -> float: ...

    def advance(self, ms: float) -> None: ...


class SystemClock:
    """Wall clock. ``advance`` is a no-op (latency is real)."""

    virtual = False

    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic_ms(self) -> float:
        return time.perf_counter() * 1000.0

    def advance(self, ms: float) -> None:  # pragma: no cover - trivial
        return None


class VirtualClock:
    """Deterministic clock. Time moves only when someone calls :meth:`advance`.

    Simulated services advance it to model latency; replay advances it by the recorded
    duration, which is why replayed timestamps equal recorded ones.
    """

    virtual = True

    def __init__(self, start: datetime = DEFAULT_EPOCH) -> None:
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        self._start = start
        self._elapsed_ms = 0.0

    def now(self) -> datetime:
        return self._start + timedelta(milliseconds=self._elapsed_ms)

    def monotonic_ms(self) -> float:
        return self._elapsed_ms

    def advance(self, ms: float) -> None:
        if ms < 0:
            raise ValueError("cannot move a virtual clock backwards")
        self._elapsed_ms += ms


class DeterministicSources:
    """Seeded id and random generators used for reproducible runs."""

    def __init__(self, seed: str) -> None:
        self._seed = seed
        self._counter = 0
        self._random = random.Random(int(hashlib.sha256(seed.encode()).hexdigest()[:16], 16))

    def new_id(self, prefix: str = "id") -> str:
        self._counter += 1
        digest = hashlib.sha256(f"{self._seed}:{self._counter}".encode()).hexdigest()[:12]
        return f"{prefix}_{digest}"

    def random(self) -> float:
        return self._random.random()


class SystemSources:
    """Real nondeterminism (used for generic, non-scenario recordings)."""

    def new_id(self, prefix: str = "id") -> str:
        return f"{prefix}_{uuid.uuid4().hex[:12]}"

    def random(self) -> float:
        return random.random()
