"""Configuration for optional live-LLM mode.

Offline demo mode (scripted models) is the default and needs nothing. Live mode is an
explicit opt-in so that no request can reach a paid API by accident:

``GHOSTREPLAY_LIVE=1``
    enable live mode (the dashboard then offers "Live AI" when recording)
``GHOSTREPLAY_LIVE_PROVIDER``
    ``anthropic`` (the only provider implemented today)
``GHOSTREPLAY_LIVE_MODEL``
    model id, default ``claude-opus-5-5``
``GHOSTREPLAY_LIVE_EFFORT``
    ``low`` | ``medium`` | ``high`` | ``xhigh`` | ``max`` (default ``medium``)
``GHOSTREPLAY_LIVE_MAX_CALLS``
    hard cap on model calls per execution (default 12)

Credentials are read by the provider SDK from its usual environment variables
(``ANTHROPIC_API_KEY`` …); GhostReplay never stores or records them.
"""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Mapping
from dataclasses import dataclass

from ..mocking.model import ModelAdapter

PROVIDERS = ("anthropic",)
EFFORTS = ("low", "medium", "high", "xhigh", "max")
DEFAULT_MODEL = "claude-opus-5-5"


@dataclass(frozen=True)
class LiveModelConfig:
    provider: str = "anthropic"
    model: str = DEFAULT_MODEL
    effort: str = "medium"
    max_calls: int = 12
    max_tokens: int = 16000

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> LiveModelConfig | None:
        """Return the config when live mode is enabled, else ``None``."""
        env = os.environ if env is None else env
        if env.get("GHOSTREPLAY_LIVE", "").strip().lower() not in ("1", "true", "yes"):
            return None
        cfg = cls(
            provider=env.get("GHOSTREPLAY_LIVE_PROVIDER", "anthropic").strip().lower(),
            model=env.get("GHOSTREPLAY_LIVE_MODEL", DEFAULT_MODEL).strip(),
            effort=env.get("GHOSTREPLAY_LIVE_EFFORT", "medium").strip().lower(),
            max_calls=int(env.get("GHOSTREPLAY_LIVE_MAX_CALLS", "12")),
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if self.provider not in PROVIDERS:
            raise ValueError(f"unknown live provider {self.provider!r}; supported: {PROVIDERS}")
        if self.effort not in EFFORTS:
            raise ValueError(f"unknown effort {self.effort!r}; use one of {EFFORTS}")
        if not 1 <= self.max_calls <= 50:
            raise ValueError("GHOSTREPLAY_LIVE_MAX_CALLS must be between 1 and 50")

    @property
    def sdk_installed(self) -> bool:
        return importlib.util.find_spec(self.provider) is not None

    def describe(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model,
            "effort": self.effort,
            "max_calls": self.max_calls,
            "sdk_installed": self.sdk_installed,
        }

    def build(self, *, model: str | None = None) -> ModelAdapter:
        """A fresh adapter (with a fresh call budget) for one execution.

        ``model`` overrides the configured model, e.g. to continue a recording made with a
        different model id.
        """
        if self.provider == "anthropic":
            from .anthropic_adapter import AnthropicModel

            return AnthropicModel(
                model or self.model,
                effort=self.effort,
                max_calls=self.max_calls,
                max_tokens=self.max_tokens,
            )
        raise ValueError(self.provider)  # pragma: no cover - validate() prevents this
