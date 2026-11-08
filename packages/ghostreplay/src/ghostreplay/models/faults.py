"""Fault specifications (data only — application logic lives in ``ghostreplay.mutation``)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class FaultTarget(BaseModel):
    """Selects which interaction(s) a fault applies to.

    ``occurrence`` is 1-based and counts interactions with the same kind and name. ``None``
    targets every occurrence. ``where`` restricts to requests containing the given key/values.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["tool_call", "model_call", "nondeterminism"] = "tool_call"
    name: str
    occurrence: int | None = Field(default=1, ge=1)
    where: dict[str, Any] = Field(default_factory=dict)


class FaultSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z0-9_.:\-]{1,80}$")
    kind: str
    target: FaultTarget
    params: dict[str, Any] = Field(default_factory=dict)
    description: str = ""


class FaultPreset(BaseModel):
    """A named, explained fault scenario offered by an application."""

    id: str
    title: str
    summary: str
    faults: list[FaultSpec]
    expected_risk: str = ""
    headline: bool = False
