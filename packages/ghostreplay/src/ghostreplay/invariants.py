"""Ready-made safety invariants for :meth:`GhostReplay.add_invariant`.

Write your own with ``@ghost.invariant(...)``; these cover common checks.
"""

from .regression.invariants import (
    Check,
    Invariant,
    TraceView,
    errors_surfaced,
    max_successful_calls,
)

__all__ = ["Check", "Invariant", "TraceView", "errors_surfaced", "max_successful_calls"]
