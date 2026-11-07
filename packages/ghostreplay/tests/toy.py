"""A minimal banking scenario used to test the framework in isolation from the demo apps."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ghostreplay import AgentResult, AgentRuntime, ToolError, ToolTimeout
from ghostreplay.core.clock import Clock
from ghostreplay.lab import Condition, Environment, Scenario, Variant
from ghostreplay.mocking import (
    ChaosRule,
    HttpRequest,
    HttpResponse,
    Message,
    MockHttpService,
    ModelRequest,
    ModelResponse,
    ScriptedModel,
    ToolCallRequest,
    ToolRegistry,
    ToolSpec,
)
from ghostreplay.models import FaultPreset, FaultSpec, FaultTarget
from ghostreplay.regression import Check, Invariant, TraceView, errors_surfaced


class WithdrawArgs(BaseModel):
    account: str
    amount: int = Field(gt=0)
    idempotency_key: str | None = None


class BalanceArgs(BaseModel):
    account: str


class Counters:
    def __init__(self) -> None:
        self.handler_calls = 0
        self.model_calls = 0


COUNTERS = Counters()


def build_bank(clock: Clock, chaos: str) -> tuple[MockHttpService, dict[str, Any]]:
    state: dict[str, Any] = {"balance": 100, "withdrawals": [], "keys": {}}
    bank = MockHttpService("bank", clock)

    @bank.route("GET", "/accounts/{account}")
    def balance(req: HttpRequest) -> HttpResponse:
        return HttpResponse(200, {"account": req.params["account"], "balance": state["balance"]})

    @bank.route("POST", "/withdrawals")
    def withdraw(req: HttpRequest) -> HttpResponse:
        key = req.header("Idempotency-Key")
        if key and key in state["keys"]:
            return HttpResponse(200, {**state["keys"][key], "idempotent_replay": True})
        amount = int(req.json["amount"])
        state["balance"] -= amount
        record = {"id": f"wd_{len(state['withdrawals']) + 1}", "amount": amount}
        state["withdrawals"].append(record)
        if key:
            state["keys"][key] = record
        return HttpResponse(201, record)

    if chaos == "commit_then_timeout":
        bank.chaos.append(ChaosRule("POST", "/withdrawals", "commit_then_timeout"))
    return bank, state


def policy(req: ModelRequest) -> ModelResponse:
    COUNTERS.model_calls += 1
    tool_msgs = [m for m in req.messages if m.role == "tool"]
    if not tool_msgs:
        return ModelResponse(
            tool_calls=[
                ToolCallRequest(id="c1", name="bank.balance", arguments={"account": "acc-1"})
            ],
            stop_reason="tool_use",
        )
    last = tool_msgs[-1]
    if last.name == "bank.balance":
        data = last.data or {}
        if (
            isinstance(data, dict)
            and isinstance(data.get("balance"), int)
            and data["balance"] >= 50
        ):
            return ModelResponse(
                tool_calls=[
                    ToolCallRequest(
                        id="c2", name="bank.withdraw", arguments={"account": "acc-1", "amount": 50}
                    )
                ],
                stop_reason="tool_use",
            )
        return ModelResponse(content="Cannot determine balance; escalating.")
    if last.name == "bank.withdraw" and isinstance(last.data, dict) and "error" not in last.data:
        return ModelResponse(content="Withdrew 50.")
    return ModelResponse(content="Withdrawal failed; escalating.")


class BankAgent:
    def __init__(self, variant: str) -> None:
        self.variant = variant
        self.name = f"bank-agent/{variant}"

    def run(self, rt: AgentRuntime, task: dict[str, Any]) -> AgentResult:
        request_id = rt.new_id("req")
        rt.now()
        messages = [Message(role="user", content=task["message"])]
        tools = [spec.schema() for spec in rt.tools.specs()]
        for _ in range(6):
            result = rt.complete(ModelRequest(model=rt.model_name, messages=messages, tools=tools))
            resp = result.response
            messages.append(Message.assistant(resp))
            if not resp.tool_calls:
                status = "success" if resp.content.startswith("Withdrew") else "escalated"
                return AgentResult(
                    status=status, message=resp.content, data={"request_id": request_id}
                )
            for call in resp.tool_calls:
                data = self._execute(rt, call, request_id, result.event_id)
                messages.append(
                    Message(
                        role="tool",
                        name=call.name,
                        tool_call_id=call.id,
                        data=data,
                        content=str(data),
                    )
                )
        return AgentResult(status="failed", message="step limit")

    def _execute(
        self, rt: AgentRuntime, call: ToolCallRequest, request_id: str, parent: str
    ) -> Any:
        args = dict(call.arguments)
        if call.name == "bank.withdraw" and self.variant == "safe":
            args["idempotency_key"] = f"wd:{request_id}"
        attempts = 3 if call.name == "bank.withdraw" else 1
        for attempt in range(attempts):
            try:
                return rt.call_tool(call.name, args, parent_event_id=parent)
            except ToolTimeout as exc:
                rt.log("retry", {"attempt": attempt + 1, "error": str(exc)})
                continue
            except ToolError as exc:
                return {"error": exc.error_type, "message": str(exc)}
        return {"error": "ToolTimeout", "message": "gave up"}


def no_double_withdrawal() -> Invariant:
    def check(view: TraceView) -> Check:
        state = view.final_state or {}
        wds = state.get("bank", {}).get("withdrawals", [])
        if len(wds) > 1:
            return Check.fail(
                f"{len(wds)} withdrawals were committed for one request",
                [e.event_id for e in view.tool_calls("bank.withdraw")],
            )
        return Check.ok(f"{len(wds)} withdrawal(s) committed")

    return Invariant(
        "bank.no_double_withdrawal",
        "No double withdrawal",
        "One request, one withdrawal.",
        check,
        severity="critical",
        requires_state=True,
    )


class ToyBankScenario(Scenario):
    id = "toy-bank"
    app = "toy"
    title = "Toy bank withdrawal"
    summary = "A toy withdrawal agent."
    bug_explanation = "Retries without idempotency."
    fix_explanation = "Idempotency key."
    headline_invariant = "bank.no_double_withdrawal"
    variants = (
        Variant("naive", "Naive", "retries blindly"),
        Variant("safe", "Safe", "idempotent retries", is_fix=True),
    )
    conditions = (
        Condition(
            "bank", "Bank", ("healthy", "commit_then_timeout"), "healthy", "commit_then_timeout"
        ),
    )

    def default_task(self) -> dict[str, Any]:
        return {"message": "Please withdraw 50 from acc-1"}

    def build_environment(self, conditions: dict[str, str], clock: Clock) -> Environment:
        bank, state = build_bank(clock, conditions.get("bank", "healthy"))
        reg = ToolRegistry()

        def balance(account: str) -> Any:
            COUNTERS.handler_calls += 1
            return bank.request("GET", f"/accounts/{account}")

        def withdraw(account: str, amount: int, idempotency_key: str | None = None) -> Any:
            COUNTERS.handler_calls += 1
            headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
            return bank.request(
                "POST", "/withdrawals", json={"account": account, "amount": amount}, headers=headers
            )

        reg.register(
            ToolSpec("bank.balance", balance, "Get balance", "http", args_model=BalanceArgs)
        )
        reg.register(
            ToolSpec(
                "bank.withdraw",
                withdraw,
                "Withdraw",
                "http",
                destructive=True,
                args_model=WithdrawArgs,
                timeout_ms=10_000,
                observe=lambda _a: {"balance": state["balance"]},
            )
        )
        return Environment(
            tools=reg,
            clock=clock,
            snapshot=lambda: {
                "bank": {"balance": state["balance"], "withdrawals": list(state["withdrawals"])}
            },
        )

    def build_model(self) -> ScriptedModel:
        return ScriptedModel("toy-model", policy)

    def build_agent(self, variant: str) -> BankAgent:
        return BankAgent(variant)

    def invariants(self) -> list[Invariant]:
        return [no_double_withdrawal(), errors_surfaced()]

    def fault_presets(self) -> list[FaultPreset]:
        return [
            FaultPreset(
                id="withdraw-timeout-after-commit",
                title="Withdraw times out after commit",
                summary="The bank commits, the response is lost.",
                headline=True,
                faults=[
                    FaultSpec(
                        id="f1",
                        kind="timeout_after_commit",
                        target=FaultTarget(name="bank.withdraw", occurrence=1),
                    )
                ],
            )
        ]
