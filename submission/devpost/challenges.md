# Challenges we ran into

These are the technical problems that shaped GhostReplay's design. Each one is visible in the
code and covered by tests.

## 1. A timeout after commit cannot be expressed by swapping a response

The headline failure of the Support Agent Lab is a refund that the payment gateway commits
while the client times out. In a pure replay, all we can do is change what the agent sees.
We could return a timeout instead of the recorded refund, but then the simulated world would
not contain the refund. The agent's retry would look harmless, and the bug would be hidden by
the test harness itself.

**What we did:** the fault catalog gives each fault a strategy, and faults with
`execute_then_error` or `delay` strategies are marked `requires_branch`. Branch mode builds a
fresh, deterministic simulated environment, replays the recorded prefix while verifying each
re-executed tool result against the recording, then lets the operation really happen (the
refund exists) before the agent sees the timeout. Every event in such a run is labelled
`simulated`, and the execution is labelled `branch`. The dashboard shows "requires branch
execution" next to these faults.

## 2. Not inventing continuations

Once a fault makes the agent do something different, the recording has nothing to say about
what comes next. A tempting shortcut is to keep serving recorded responses, or to make up
plausible ones. Both produce results that look real but are not.

**What we did:** strict counterfactual replay stops at the first divergence. Divergence is
detected by interaction kind, name and a hash of the redacted request; the mismatch becomes a
`divergence` event with a field-level diff, and recorded responses are never consumed out of
order. To see what the agent does next, you have to run it: the Failure Lab offers
"Run as branch execution". Testing a different agent variant (for example the fixed harness)
against a recording also always uses branch mode, because the fixed code asks for different
things by design.

Invariants that depend on the final world state are reported as `inconclusive` for strict
offline counterfactuals instead of being silently passed, because the state of a world that
was never executed is unknown.

## 3. Redaction versus match keys

Secrets must never be persisted, so every payload is redacted before it is stored. But replay
must recognise "the same request" again, and the live request contains the unredacted value.
Hashing the raw request would make every replay diverge (or would require storing the
secret).

**What we did:** the match key is `sha256(kind, name, canonical_json(redact(request)))`,
computed with the same redactor the recorder uses. The redactor is deliberately conservative
about keys (exact names and suffixes, so `max_tokens` and `idempotency_key` survive) and broad
about values (AWS keys, bearer tokens, `sk-` keys, GitHub tokens, private keys, Luhn-valid
card numbers). Tools can also restrict matching to selected fields (`ToolSpec.match_fields`)
when a request contains values that legitimately vary.

## 4. Blocking the network without breaking the server

Offline replay should be physically unable to reach the network, not just "configured not
to". But the lab server must keep serving HTTP, including the Server-Sent Events stream that
shows the replay as it happens.

**What we did:** the offline guard patches `socket` once per process, but the patched
functions only refuse when the calling thread is inside an offline replay. Replay also swaps
in a tool registry whose handlers raise if called, so "zero tool handlers invoked" is
enforced rather than assumed.

## 5. Determinism beyond model and tool calls

Clocks, generated ids and random numbers make two runs differ even when the agent's
decisions are the same.

**What we did:** time, ids and randomness are runtime calls too (`rt.now()`, `rt.new_id()`,
`rt.random()`), recorded as `nondeterminism` events. A `VirtualClock` advances by simulated
latency while recording and by the recorded duration on replay, so replayed timestamps and
durations equal the recording's. A test compares kinds, names, requests, responses, errors,
timestamps, durations and state for every event.

## 6. Live LLM recordings

The optional live mode drives the agents with a real model through the Anthropic API. Two
details mattered:

- **Thinking-block echo.** The Messages API requires the assistant's content blocks,
  including thinking blocks, to be passed back unchanged on the next turn. A
  provider-neutral message format would lose them. Recordings therefore keep the
  provider-native content blocks next to the neutral response, and the adapter echoes them
  back (omitting internal blocks before a mid-output fallback marker, as the API requires).
- **No silent switching.** Replay and strict counterfactuals of a live recording are fully
  offline and need no key. Branch counterfactuals continue past the divergence, so they need
  a live model with the recording's model id and are refused with a clear error when live
  mode is off. A scripted recording never silently switches to a paid API, and a live
  recording never silently continues with a script.

Live mode also has a per-execution call budget, records refusals as errors, and is always off
in the public deployment profile.

## 7. Making a public demo safe to host

A public instance lets anyone trigger engine runs. Every tool is already an allowlisted
in-memory simulation, and nothing in requests or trace files is executed. On top of that, the
public profile (`GHOSTREPLAY_PUBLIC=1`) adds per-client rate limits, a cap on concurrent runs
(HTTP 503 beyond it), a request body cap, retention limits for stored executions, disables
clearing all data, and forces live mode off.

## 8. One framework, two domains

A refund bug and an infrastructure outage have little in common at the domain level. Keeping
both labs thin meant pushing every reusable concept (variants, incident conditions, fault
presets, invariants, guided-demo steps, regression export) into the framework's `Scenario`
abstraction, so each lab only provides its simulated world, tools, scripted policy, harness
variants and invariants.
