"""The Duplicate Refund scenario, registered with GhostReplay."""

from __future__ import annotations

from typing import Any

from ghostreplay.core.clock import Clock
from ghostreplay.lab import Condition, Environment, Scenario, Variant
from ghostreplay.mocking import ScriptedModel
from ghostreplay.models import FaultPreset, FaultSpec, FaultTarget
from ghostreplay.regression import Invariant

from .agent import SupportAgent
from .environment import SupportWorld
from .invariants import all_invariants
from .model import build_model
from .tools import build_tools

REFUND = "payments.create_refund"


def _f(
    fid: str, kind: str, name: str = REFUND, occurrence: int | None = 1, **params: Any
) -> FaultSpec:
    return FaultSpec(
        id=fid, kind=kind, target=FaultTarget(name=name, occurrence=occurrence), params=params
    )


class DuplicateRefundScenario(Scenario):
    id = "duplicate-refund"
    app = "support-agent"
    title = "Duplicate Refund"
    summary = (
        "A customer asks for a refund for damaged earbuds. The payment gateway commits the refund "
        "but the response never arrives; the agent's retry refunds the customer a second time."
    )
    bug_explanation = (
        "A timeout is an ambiguous failure: the client cannot know whether the gateway committed. "
        "The vulnerable harness retries the identical POST /v1/refunds without an idempotency key, "
        "so the gateway has no way to recognise the retry as the same refund and creates a second "
        "one. The customer is told $129.00 was refunded while $258.00 actually moved."
    )
    fix_explanation = (
        "The fixed harness derives an idempotency key from the business intent "
        "(refund:<ticket>:<payment>:<amount>) and sends it on every attempt. After a timeout it "
        "reconciles with GET /v1/refunds before retrying, and any retry reuses the same key, so the "
        "gateway returns the original refund instead of creating a new one. The model is unchanged: "
        "the fix lives in deterministic code we control."
    )
    headline_invariant = "refund.no_duplicate"
    variants = (
        Variant(
            "vulnerable",
            "Vulnerable harness",
            "Retries refunds on timeout without an idempotency key.",
        ),
        Variant(
            "fixed",
            "Idempotent harness",
            "Intent-scoped idempotency key + reconciliation before retry.",
            is_fix=True,
        ),
    )
    conditions = (
        Condition(
            "payment_gateway",
            "Payment gateway",
            ("healthy", "timeout_after_commit"),
            "healthy",
            "timeout_after_commit",
            "timeout_after_commit: the gateway commits the first refund, then hangs past the client timeout.",
        ),
    )

    def default_task(self) -> dict[str, Any]:
        return {
            "ticket_id": "TCK-5521",
            "customer_id": "CUS-0077",
            "message": (
                "Hi, my order ORD-1042 arrived yesterday and the Aurora earbuds case is cracked — "
                "one earbud won't charge. Can I get a refund for the earbuds? Thanks, Maya"
            ),
        }

    def build_environment(self, conditions: dict[str, str], clock: Clock) -> Environment:
        world = SupportWorld(clock, payment_gateway=conditions.get("payment_gateway", "healthy"))
        return Environment(
            tools=build_tools(world),
            snapshot=world.snapshot,
            clock=clock,
            backends={"world": world},
        )

    def build_model(self) -> ScriptedModel:
        return build_model()

    def build_agent(self, variant: str) -> SupportAgent:
        return SupportAgent(variant)

    def invariants(self) -> list[Invariant]:
        return all_invariants()

    def fault_presets(self) -> list[FaultPreset]:
        return [
            FaultPreset(
                id="refund-timeout-after-commit",
                title="Refund times out after commit",
                summary="The gateway commits the refund, then the response is lost (client timeout).",
                expected_risk="Duplicate refund if the agent retries without idempotency.",
                headline=True,
                faults=[_f("refund-timeout-after-commit", "timeout_after_commit")],
            ),
            FaultPreset(
                id="refund-timeout-before-commit",
                title="Refund times out before commit",
                summary="The gateway times out before doing anything. Indistinguishable for the agent.",
                expected_risk="Safe retry by luck — the same bug, hidden.",
                faults=[_f("refund-timeout-before-commit", "tool_timeout")],
            ),
            FaultPreset(
                id="gateway-rate-limited",
                title="Gateway rate limited (429)",
                summary="The first refund attempt is rejected with HTTP 429.",
                expected_risk="Retries must not multiply refunds.",
                faults=[_f("gateway-429", "http_429")],
            ),
            FaultPreset(
                id="gateway-down",
                title="Gateway down (500 on every call)",
                summary="Every refund attempt fails with HTTP 500.",
                expected_risk="Agent must not claim success.",
                faults=[_f("gateway-500", "http_500", occurrence=None)],
            ),
            FaultPreset(
                id="eligibility-missing-amount",
                title="Missing refundable amount",
                summary="The eligibility tool omits refundable_amount_cents.",
                expected_risk="Agent must not refund an unverified amount.",
                faults=[
                    _f(
                        "elig-missing-amount",
                        "missing_field",
                        name="refunds.check_eligibility",
                        path="refundable_amount_cents",
                    )
                ],
            ),
            FaultPreset(
                id="order-lookup-unauthorized",
                title="Orders DB auth failure",
                summary="The order lookup fails with 401.",
                expected_risk="Agent must escalate, not guess.",
                faults=[_f("orders-401", "auth_failure", name="orders.lookup_order")],
            ),
        ]
