"""Secret redaction applied to every payload before it is recorded."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

REDACTED = "[REDACTED]"

_SENSITIVE_EXACT = {
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "proxy_authorization",
    "cookie",
    "set_cookie",
    "card_number",
    "cvv",
    "cvc",
    "private_key",
    "access_key",
    "secret_access_key",
    "aws_secret_access_key",
    "aws_access_key_id",
    "client_secret",
    "session_token",
    "access_token",
    "refresh_token",
    "ssn",
    "x_api_key",
}
_SENSITIVE_SUFFIXES = (
    "_password",
    "_secret",
    "_api_key",
    "_access_token",
    "_refresh_token",
    "_session_token",
    "_private_key",
)

_VALUE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=\-]{8,}")),
    ("api_key", re.compile(r"\bsk-(?:live-|proj-|ant-)?[A-Za-z0-9_\-]{16,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    (
        "private_key",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    ),
]
_CARD_CANDIDATE = re.compile(r"\b(?:\d[ \-]?){12,18}\d\b")


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _normalise_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")


class Redactor:
    """Scrubs secret-looking keys and values from JSON-like payloads.

    Redaction is deliberately conservative about *keys* (exact names and suffixes, so that
    ``max_tokens`` or ``idempotency_key`` survive) and broad about *values* (any string that
    looks like a cloud key, bearer token, API key or Luhn-valid card number).
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        extra_keys: Iterable[str] = (),
        extra_patterns: Iterable[tuple[str, str]] = (),
    ) -> None:
        self.enabled = enabled
        self._keys = _SENSITIVE_EXACT | {_normalise_key(k) for k in extra_keys}
        self._patterns = list(_VALUE_PATTERNS) + [(n, re.compile(p)) for n, p in extra_patterns]
        self.redaction_count = 0

    def is_sensitive_key(self, key: str) -> bool:
        norm = _normalise_key(key)
        return norm in self._keys or norm.endswith(_SENSITIVE_SUFFIXES)

    def redact(self, value: Any) -> Any:
        if not self.enabled:
            return value
        return self._walk(value)

    def _walk(self, value: Any) -> Any:
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for k, v in value.items():
                if isinstance(k, str) and self.is_sensitive_key(k) and v not in (None, ""):
                    self.redaction_count += 1
                    out[k] = REDACTED
                else:
                    out[k] = self._walk(v)
            return out
        if isinstance(value, list):
            return [self._walk(v) for v in value]
        if isinstance(value, str):
            return self._scrub_string(value)
        return value

    def _scrub_string(self, text: str) -> str:
        result = text
        for name, pattern in self._patterns:
            result, n = pattern.subn(f"[REDACTED:{name}]", result)
            self.redaction_count += n

        def _card(match: re.Match[str]) -> str:
            digits = re.sub(r"\D", "", match.group(0))
            if 13 <= len(digits) <= 19 and _luhn_ok(digits):
                self.redaction_count += 1
                return "[REDACTED:card_number]"
            return match.group(0)

        return _CARD_CANDIDATE.sub(_card, result)
