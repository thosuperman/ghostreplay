# Implementation plan — core framework

- [x] 1. Foundation
  - [x] 1.1 uv workspace, `ghostreplay` package skeleton, Ruff + pytest config
  - [x] 1.2 Versioned schema models (`models/`): Event, Execution, FaultSpec, results
  - [x] 1.3 Canonical JSON + stable hashing, JSON-path helpers (`core/`)
  - [x] 1.4 Virtual/system clocks and deterministic sources
  - _Requirements: 1.1, 1.3_

- [x] 2. Recording
  - [x] 2.1 `Redactor` (key and value patterns, Luhn check) — _Req 1.4_
  - [x] 2.2 `Recorder` with listeners and redaction — _Req 1.1, 1.2_
  - [x] 2.3 `AgentRuntime` (complete / call_tool / now / new_id / random / log) — _Req 1.1_

- [x] 3. Mocking
  - [x] 3.1 `ToolRegistry` allowlist + Pydantic validation — _Req 3.1, 3.3_
  - [x] 3.2 Simulated HTTP service, database, AWS-like cloud — _Req 3.2, 3.4_
  - [x] 3.3 `ModelAdapter` protocol + `ScriptedModel` — _Req 4.1, 4.2_

- [x] 4. Replay engine
  - [x] 4.1 `Session.interact` with record / replay / branch policies — _Req 2.1, 5.5_
  - [x] 4.2 Divergence detection (mismatch, unexpected_call, incomplete, result_mismatch) — _Req 2.3–2.5_
  - [x] 4.3 Offline guard + handler stubs — _Req 2.2_
  - [x] 4.4 Test: replay of unmodified recording is structurally identical — _Req 2.6_

- [x] 5. Mutation
  - [x] 5.1 Fault catalog with strategies and `requires_branch` — _Req 5.1, 5.2_
  - [x] 5.2 Fault application incl. original response capture — _Req 5.3_
  - [x] 5.3 Counterfactual replay stops honestly on divergence — _Req 5.4_

- [x] 6. Diff engine — _Req 6.1–6.3_
- [x] 7. Regression: invariants, cases, runner, pytest generation, JSON/JUnit — _Req 7.1–7.3_
- [x] 8. Storage: SQLite store, safe import/export — _Req 8.1–8.3_
- [x] 9. Lab orchestrator + Scenario base class + FastAPI app factory (SSE replay stream)
- [x] 10. Guarantee test suite green (`uv run pytest packages/ghostreplay`)
