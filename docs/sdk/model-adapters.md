# Model adapters

There are two ways to put a model call under GhostReplay's control. Both are explicit, and neither sends trace data anywhere.

## 1. `@ghost.model`: wrap any function (provider-neutral)

Wrap the function that calls your model. Its JSON-able keyword arguments become the recorded request, and its JSON-able return value becomes the recorded response. Inside it you can use any client (OpenAI, Anthropic, a local model, a rules engine).

```python
from ghostreplay import GhostReplay

ghost = GhostReplay("triage", live_models=False)  # set True when the function calls a real LLM


@ghost.model("classifier")
def classify(ticket: str) -> dict:
    # Real code would call an LLM here, e.g. client.messages.create(...)
    return {"label": "refund" if "refund" in ticket.lower() else "other"}


@ghost.agent()
def agent(task: dict) -> str:
    return classify(ticket=task["ticket"])["label"]


run = ghost.record({"ticket": "Please refund my order"})
replay = ghost.replay(run)
print(run.output.message, replay.model_calls()[0].source)  # refund recorded
```

During replay `classify` is not called: the recorded label is returned. So a replay costs nothing and is deterministic, even when the original call was a live, non-deterministic LLM.

## 2. `ModelAdapter` + `ghost.complete()`: structured chat and tool use

For agents built around a chat-style tool-use loop, GhostReplay has a small model interface:

- `ModelRequest(model, system, messages, tools)`;
- `ModelResponse(content, tool_calls, stop_reason)`;
- an adapter with `.complete(request)`.

The bundled demos use it, and so does `ScriptedModel`, a deterministic policy for tests and demos:

```python
from ghostreplay import GhostReplay
from ghostreplay.mocking import Message, ModelRequest, ModelResponse, ScriptedModel, ToolCallRequest


def policy(req: ModelRequest) -> ModelResponse:
    if not any(m.role == "tool" for m in req.messages):
        return ModelResponse(
            tool_calls=[
                ToolCallRequest(id="c1", name="kb.search", arguments={"q": "refund policy"})
            ],
            stop_reason="tool_use",
        )
    return ModelResponse(content="Refunds within 30 days.")


ghost = GhostReplay("helpdesk", model=ScriptedModel("helpdesk-sim", policy))


@ghost.tool("kb.search")
def search(q: str) -> dict:
    return {"hits": ["Refunds are accepted within 30 days."]}


@ghost.agent()
def agent(task: dict) -> str:
    messages = [Message(role="user", content=task["question"])]
    while True:
        resp = ghost.complete(ModelRequest(model=ghost.model_name, messages=messages))
        messages.append(Message.assistant(resp))
        if not resp.tool_calls:
            return resp.content
        for call in resp.tool_calls:
            messages.append(
                Message(
                    role="tool", name=call.name, tool_call_id=call.id, data=search(**call.arguments)
                )
            )


run = ghost.record({"question": "What is the refund policy?"})
print(run.output.message, "|", run.execution.provenance.label)
assert ghost.replay(run).live_calls == 0
```

### Live LLMs

`ghostreplay[live]` includes an Anthropic adapter (`ghostreplay.llm.LiveModelConfig`, configured from the `GHOSTREPLAY_LIVE_*` environment variables and `ANTHROPIC_API_KEY`). Any object with `provider`, `model`, `is_live`, `label` and `complete(request)` works as an adapter.

```python
# fragment
from ghostreplay.llm import LiveModelConfig

config = LiveModelConfig.from_env()  # None unless GHOSTREPLAY_LIVE=1
ghost = GhostReplay("helpdesk", model=config.build() if config else ScriptedModel("sim", policy))
```

Live calls happen only while recording. Replays of a live recording are served from it, with no API key needed.

## Labels

Every run carries a provenance label so a scripted decision is never mistaken for a live LLM. The labels are shown in `run.execution.provenance`, `ghostreplay inspect` and the dashboard:

| Label | Meaning |
|---|---|
| Scripted agent / scripted model | A deterministic policy (`ScriptedModel`), not an LLM |
| Live model call | A real provider request made while recording (`is_live=True`) |
| Recorded model response | `source="recorded"`: served from a recording during replay |
| App-defined model functions | Calls recorded through `@ghost.model`. They are labelled live only if you pass `live_models=True`. |

## Privacy

GhostReplay never sends traces, prompts or responses to any AI service. A model is called only when your own code calls it. Secret-looking values are redacted before events are stored. That covers keys such as `api_key`, `authorization` or `password`, and values such as `sk-…` keys, bearer tokens, AWS access keys and GitHub tokens.
