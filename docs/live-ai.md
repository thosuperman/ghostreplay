# Live AI mode

GhostReplay has two ways to drive an agent:

| | Offline demo mode (default) | Live AI mode (opt-in) |
|---|---|---|
| Decisions | scripted policy (`support-sim-1`, `sre-sim-1`) | a real LLM via the provider's API |
| Needs | nothing | `GHOSTREPLAY_LIVE=1` + provider credentials |
| Reproducible | yes, byte for byte | the recording is; a new live run may differ |
| Labelled in UI and traces | `scripted` | provider + model, `live` |
| Tools | in-memory simulations | **the same** in-memory simulations |

Live mode never changes what the tools are: refunds, terminations and rollbacks still hit
the simulated gateway and cloud. A live model can make the agent *decide* differently; it
cannot touch a real system.

## Enable it

```bash
uv sync --extra live
```

```bash
export GHOSTREPLAY_LIVE=1 ANTHROPIC_API_KEY=...   # never commit keys
```

```bash
uv run support-agent-lab run --live
```

Optional variables: `GHOSTREPLAY_LIVE_MODEL` (default `claude-opus-5-5`),
`GHOSTREPLAY_LIVE_EFFORT` (`low`…`max`, default `medium`), and
`GHOSTREPLAY_LIVE_MAX_CALLS` (hard cap per execution, default 12). Start the labs with the
same variables and the dashboard shows a **Live AI** option when recording.

## What gets recorded

Each model call is a `model_call` event whose request is the provider-neutral
`ModelRequest` (system prompt, messages, tool schemas) and whose response holds the text,
tool calls, token usage, the model that actually answered (`served_by`), and the
provider-native content blocks. The adapter passes those blocks back unchanged on the next
turn, as the Messages API requires for thinking blocks.

## Replay and failure injection

- **Replay** of a live recording is fully offline: the API is not called and no key is
  needed. Responses come from the recording.
- **Strict counterfactual replay** works the same way and stops at the first divergence.
- **Branch counterfactuals** continue past the divergence, so they need a live model:
  they use the recording's model id, and are refused with a clear error when live mode is
  off. A scripted recording never silently switches to a paid API, and a live recording
  never silently continues with a script.

## Safety and cost controls

- Live mode is off unless `GHOSTREPLAY_LIVE=1`, and is always off in the public
  deployment profile (`GHOSTREPLAY_PUBLIC=1`).
- Per-execution call budget; exceeding it fails the run loudly.
- A refusal (`stop_reason: refusal`) is recorded as an error, never as success.
  Requests opt into the API's server-side refusal fallback (`fallbacks: "default"`).
- Credentials are read by the provider SDK from the environment; they never appear in
  requests that GhostReplay records.

## Adding a provider

Implement the `ModelAdapter` protocol (`provider`, `model`, `is_live`, `label`,
`complete(ModelRequest) -> ModelResponse`) and register it in
`ghostreplay/llm/config.py`. See `ghostreplay/llm/anthropic_adapter.py` for the request and
response mapping and `packages/ghostreplay/tests/test_live_model.py` for how to test an
adapter against a fake client.
