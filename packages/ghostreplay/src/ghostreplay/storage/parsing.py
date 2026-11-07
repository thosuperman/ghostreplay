"""Turn untrusted bytes (files, database rows, HTTP bodies) into validated models.

Everything GhostReplay loads is plain JSON validated by Pydantic; nothing is unpickled or
evaluated. Failures become :class:`TraceFormatError` with a short, specific message instead
of a stack trace or — worse — a partially loaded recording.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ValidationError

from ..core.errors import TraceFormatError


def describe_validation_error(exc: ValidationError, limit: int = 3) -> str:
    parts = []
    for err in exc.errors()[:limit]:
        loc = ".".join(str(p) for p in err.get("loc", ())) or "document"
        parts.append(f"{loc}: {err.get('msg', 'invalid')}")
    more = exc.error_count() - limit
    if more > 0:
        parts.append(f"... and {more} more problem(s)")
    return "; ".join(parts)


def parse_document[M: BaseModel](
    model: type[M],
    raw: str | bytes | dict[str, Any],
    *,
    source: str,
) -> M:
    """Parse ``raw`` as ``model`` or raise ``TraceFormatError`` naming ``source``."""
    try:
        data = json.loads(raw) if isinstance(raw, str | bytes) else raw
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise TraceFormatError(f"{source} is not valid JSON: {exc}") from None
    if not isinstance(data, dict):
        raise TraceFormatError(f"{source} must contain a JSON object, got {type(data).__name__}")
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise TraceFormatError(
            f"{source} is not a valid {model.__name__}: {describe_validation_error(exc)}"
        ) from None
