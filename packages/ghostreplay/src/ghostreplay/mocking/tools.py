"""Tool interception interface: an allowlisted registry of tool specifications."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from ..core.errors import OfflineViolation, ToolValidationError, UnknownToolError

ToolCategory = Literal["http", "database", "aws", "agent"]


@dataclass
class ToolSpec:
    """Declares one tool an agent may call.

    ``handler`` receives validated keyword arguments and returns a JSON-able result or raises
    a :class:`~ghostreplay.core.errors.ToolError`. ``observe`` (optional) returns the slice of
    simulated state relevant to the call; it is captured before and after execution so the
    inspector can show explicit, observable state changes.
    """

    name: str
    handler: Callable[..., Any]
    description: str = ""
    category: ToolCategory = "agent"
    destructive: bool = False
    args_model: type[BaseModel] | None = None
    timeout_ms: float | None = None
    observe: Callable[[dict[str, Any]], Any] | None = None
    match_fields: list[str] | None = None

    def validate(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.args_model is None:
            return dict(args)
        try:
            return self.args_model.model_validate(args).model_dump(mode="json", exclude_none=True)
        except ValidationError as exc:
            raise ToolValidationError(
                f"Invalid arguments for {self.name}: {exc.errors(include_url=False)[0]['msg']}",
                data={"errors": [str(e["loc"]) + ": " + e["msg"] for e in exc.errors()]},
            ) from None

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "destructive": self.destructive,
            "parameters": self.args_model.model_json_schema() if self.args_model else {},
        }


@dataclass
class ToolRegistry:
    """Allowlist of tools. Calling anything else raises :class:`UnknownToolError`."""

    _tools: dict[str, ToolSpec] = field(default_factory=dict)

    def register(self, spec: ToolSpec) -> ToolSpec:
        if spec.name in self._tools:
            raise ValueError(f"tool {spec.name!r} registered twice")
        self._tools[spec.name] = spec
        return spec

    def tool(self, name: str, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator form of :meth:`register`."""

        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.register(ToolSpec(name=name, handler=fn, **kwargs))
            return fn

        return deco

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError:
            raise UnknownToolError(
                f"Tool {name!r} is not registered (allowed: {', '.join(sorted(self._tools))})"
            ) from None

    def names(self) -> list[str]:
        return sorted(self._tools)

    def specs(self) -> list[ToolSpec]:
        return [self._tools[n] for n in self.names()]

    def offline_copy(self) -> ToolRegistry:
        """Same specs, but every handler and observer raises :class:`OfflineViolation`.

        Used during pure replay so that a bug in the engine can never reach a backend.
        """

        def _forbidden(name: str) -> Callable[..., Any]:
            def _raise(*_a: Any, **_k: Any) -> Any:
                raise OfflineViolation(f"tool handler {name!r} invoked during offline replay")

            return _raise

        copy = ToolRegistry()
        for spec in self.specs():
            copy.register(
                ToolSpec(
                    name=spec.name,
                    handler=_forbidden(spec.name),
                    description=spec.description,
                    category=spec.category,
                    destructive=spec.destructive,
                    args_model=spec.args_model,
                    timeout_ms=spec.timeout_ms,
                    observe=None,
                    match_fields=spec.match_fields,
                )
            )
        return copy
