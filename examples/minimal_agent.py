"""Bring your own agent: the smallest end-to-end GhostReplay integration.

Run it with:  uv run python examples/minimal_agent.py

It defines a tiny weather agent, records it, replays it offline, injects an HTTP 500 and
shows that a regression invariant catches the agent claiming success after a failure.
Nothing here touches the network: the "weather API" is a simulated in-memory service.
"""

from __future__ import annotations

from typing import Any

from ghostreplay import AgentResult, AgentRuntime, ToolError
from ghostreplay.core.clock import Clock
from ghostreplay.diff import diff_executions
from ghostreplay.lab import Environment, Lab, Scenario, Variant
from ghostreplay.mocking import (
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
from ghostreplay.models import FaultSpec, FaultTarget
from ghostreplay.regression import Invariant, errors_surfaced


# 1. A model. Here a scripted policy; any ModelAdapter (e.g. a real LLM client) fits the same slot.
def policy(req: ModelRequest) -> ModelResponse:
    tool_results = [m for m in req.messages if m.role == "tool"]
    if not tool_results:
        return ModelResponse(
            tool_calls=[ToolCallRequest(id="c1", name="weather.get", arguments={"city": "Tokyo"})],
            stop_reason="tool_use",
        )
    data = tool_results[-1].data or {}
    if "error" in data:
        return ModelResponse(content="It's sunny in Tokyo!")  # BUG: ignores the failure
    return ModelResponse(content=f"It is {data['temp_c']}°C and {data['sky']} in Tokyo.")


# 2. An agent written against AgentRuntime (the only door to the outside world).
class WeatherAgent:
    name = "weather-agent"

    def run(self, rt: AgentRuntime, task: dict[str, Any]) -> AgentResult:
        messages = [Message(role="user", content=task["question"])]
        while True:
            result = rt.complete(ModelRequest(model=rt.model_name, messages=messages))
            if not result.response.tool_calls:
                return AgentResult(status="success", message=result.response.content)
            for call in result.response.tool_calls:
                try:
                    data = rt.call_tool(call.name, call.arguments, parent_event_id=result.event_id)
                except ToolError as exc:
                    data = {"error": exc.error_type}
                messages.append(Message(role="tool", name=call.name, data=data))


# 3. A scenario: fresh simulated world + model + agent + invariants.
class WeatherScenario(Scenario):
    id = "weather"
    app = "example"
    title = "Weather lookup"
    summary = bug_explanation = fix_explanation = "Minimal example."
    variants = (Variant("default", "Default", "The only variant"),)

    def default_task(self) -> dict[str, Any]:
        return {"question": "What's the weather in Tokyo?"}

    def build_environment(self, conditions: dict[str, str], clock: Clock) -> Environment:
        api = MockHttpService("weather-api", clock)

        @api.route("GET", "/weather/{city}")
        def weather(req: HttpRequest) -> HttpResponse:
            return HttpResponse(200, {"city": req.params["city"], "temp_c": 18, "sky": "cloudy"})

        tools = ToolRegistry()
        tools.register(
            ToolSpec(
                "weather.get",
                lambda city: api.request("GET", f"/weather/{city}"),
                "Current weather",
                "http",
            )
        )
        return Environment(tools=tools, snapshot=lambda: {}, clock=clock)

    def build_model(self) -> ScriptedModel:
        return ScriptedModel("weather-sim", policy)

    def build_agent(self, variant: str) -> WeatherAgent:
        return WeatherAgent()

    def invariants(self) -> list[Invariant]:
        return [errors_surfaced()]


def main() -> None:
    lab = Lab("example", [WeatherScenario()])

    recorded = lab.record("weather", "default")
    print(f"recorded  {recorded.id}: {recorded.output.message}")

    replayed = lab.replay(recorded.id)
    same = diff_executions(recorded, replayed).identical
    print(f"replayed  {replayed.id}: identical to recording = {same}")

    fault = FaultSpec(id="weather-500", kind="http_500", target=FaultTarget(name="weather.get"))
    broken = lab.counterfactual(recorded.id, [fault], mode="branch")
    print(f"broken    {broken.id}: agent said {broken.output.message!r}")
    for inv in broken.invariants:
        print(f"  [{inv.status.upper()}] {inv.id}: {inv.message}")


if __name__ == "__main__":
    main()
