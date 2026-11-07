# Design — Replay engine

Written after the implementation; it records the decisions the code embodies and the design of
the two planned improvements. Deeper narrative: `docs/architecture.md`.

## Components

| Concern | Module | Key types / functions |
|---|---|---|
| Schema | `models/events.py`, `models/execution.py` | `Event`, `EventKind`, `EventSource`, `Execution` (`_check_integrity`), `ExecutionSummary`, `Divergence`, `Provenance` |
| Hashing, diffs, paths | `core/canonical.py` | `stable_hash`, `to_jsonable`, `deep_diff`, `get_path`/`set_path`/`delete_path` |
| Time and ids | `core/clock.py` | `VirtualClock`, `SystemClock`, `DeterministicSources`, `DEFAULT_EPOCH` |
| Errors | `core/errors.py` | `GhostReplayError`, `ReplayDivergenceError`, `MissingRecordingError`, `OfflineViolation`, `TraceFormatError`, `ToolError` family + `from_info` allowlist |
| Recording | `recorder/recorder.py`, `recorder/redaction.py` | `Recorder.emit`, `Redactor` |
| Agent API | `runtime.py` | `AgentRuntime.complete/call_tool/now/new_id/random/log/guard` |
| Replay policy | `replay/session.py`, `replay/guard.py` | `Session.interact`, `Session.finish`, `offline_guard` |
| Tools and models | `mocking/` | `ToolRegistry` (+ `offline_copy`), `ToolSpec`, simulated HTTP/DB/AWS, `ModelAdapter`, `ScriptedModel` |
| Live model | `llm/config.py`, `llm/anthropic_adapter.py` | `LiveModelConfig.from_env/build/describe`, `AnthropicModel`, `LiveModelError` |
| Diff | `diff/structural.py` | `diff_executions` → `TraceDiff` |
| Storage | `storage/sqlite.py`, `storage/parsing.py`, `storage/files.py` | `SqliteStore`, `parse_document`, `safe_join`, `export_execution`, `import_execution` |
| Serving | `server/app.py`, `server/settings.py`, `server/gateway.py`, `server/cli.py`, `cli.py` | `create_app`, `ServerSettings.from_env`, `RateLimiter`, `create_gateway`, `lab_main`, `ghostreplay serve` |

## Decisions and rationale

### D1 — One door (`AgentRuntime`) instead of library monkey-patching
Agents reach the world only through the runtime. *Rationale:* deterministic replay becomes a
framework property instead of a per-SDK patch; the limitation is explicit (code that bypasses
the runtime is not replayed and is blocked offline). *Trade-off:* agents must be written
against the runtime; `examples/minimal_agent.py` shows the cost is ~100 lines.

### D2 — One policy point (`Session.interact`)
Record, replay, counterfactual-replay and branch are policies of a single function.
*Rationale:* fault injection and divergence detection apply uniformly to model calls, tool
calls and nondeterminism; there is no second engine to drift.

### D3 — Strict in-order consumption with a match key
`match_key = stable_hash(kind, name, redact(match_request))`. The cursor only advances on a
match; the first mismatch takes the run off-track. *Rationale:* out-of-order matching could
"succeed" on a different execution path and hide the very bug being debugged. Redacting before
hashing means secrets never influence (or leak through) matching. `ToolSpec.match_fields`
lets tools ignore volatile arguments.

### D4 — Offline isolation in depth
Offline modes get no model adapter, an `offline_copy()` registry whose handlers raise
`OfflineViolation`, and a thread-local socket guard. *Rationale:* any single layer could have a
bug; the guard is thread-local so a lab server keeps serving HTTP while a replay runs.

### D5 — Reject bad recordings at the boundary
`Execution` validates `seq` order, unique `event_id`s and `schema_version`; every load goes
through `parse_document` → `TraceFormatError`. *Rationale:* a recording that would replay in a
different order is worse than no recording. `list()` skips unreadable rows so one corrupt row
cannot take down the Explorer, while `get()` fails loudly.

### D6 — SQLite with WAL, retention and ping
One file per lab, indexed columns + summary JSON (fast lists) + body JSON (full fidelity).
WAL lets SSE readers and the writer proceed concurrently and survives crashes mid-write.
`max_executions` bounds disk use on public deployments; `ping()` backs readiness checks.

### D7 — Live model as an adapter, recorded like any other
`AnthropicModel` implements `ModelAdapter`; requests are provider-neutral `ModelRequest`s and
responses keep `usage`, `served_by` and provider-native blocks (echoed back on the next turn).
*Rationale:* a live recording replays offline exactly like a scripted one. Runs derived from a
recording keep its model kind (`Lab._model_for`) so nobody is surprised by API spend or by a
script silently standing in for an LLM.

### D8 — Serving: independent labs, optional gateway, hardened public profile
Each lab is a FastAPI app; `create_gateway` mounts every `ghostreplay.labs` entry point at
`/lab/<name>`, matching the Vite proxy paths so the dashboard build is unchanged. The public
profile is configuration, not a fork: limits live in `ServerSettings` and one middleware.

## Planned design — Requirement 9 (provenance verification)
- New function `ghostreplay.replay.verify.recompute_match_keys(execution, tools=None)` returning
  a list of `(seq, kind, name, expected, actual)` mismatches. For `tool_call` events whose spec
  declares `match_fields`, hash `{k: request.get(k) for k in match_fields}`; otherwise hash the
  stored request (it is already redacted, and redaction is idempotent).
- Tool specs are resolved via `lab.registry.resolve(execution.scenario).build_environment(...)`
  only when needed; if the scenario is not installed, fall back to full-request hashing and
  report that `match_fields` could not be resolved.
- `import_execution(directory, name, *, strict=False)`: when `strict`, raise `TraceFormatError`
  listing the first mismatches. CLI: `ghostreplay verify <files...>` exits 1 on any mismatch.
- Rationale: integrity validation (D5) catches structural tampering; this catches semantic
  tampering (edited request with a stale key).

## Planned design — Requirement 10 (precise result_mismatch)
- In `Session._verify`, build the message from the first `changes[i]["path"]` entries the same
  way `_check` does for inputs: `"... for 'payments.create_refund' (seq 7): response.id, ..."`.
- Test: in the toy-bank scenario, record a run, tamper the recorded response of one tool call
  (and recompute nothing else), branch-replay it, and assert `divergence.type ==
  "result_mismatch"` and the path appears in the message.

## Test coverage map

| Requirement | Tests (file :: function) |
|---|---|
| 1.1–1.3 | `packages/ghostreplay/tests/test_replay.py` :: `test_recording_has_ordered_complete_events` |
| 1.4 | `test_security_storage.py` :: `test_redactor_scrubs_keys_and_values_but_keeps_benign_fields`, `test_recorder_persists_only_redacted_payloads` |
| 2.1, 2.3–2.5 | `test_replay.py` :: `test_replay_is_structurally_identical_to_recording`, `test_replay_twice_is_reproducible`, `test_recorded_errors_are_replayed_with_their_type`, `test_nondeterminism_is_recorded_and_replayed` |
| 2.2 | `test_replay.py` :: `test_replay_never_invokes_tool_handlers_or_model`, `test_offline_guard_blocks_sockets_only_in_guarded_thread`, `test_agent_network_access_during_replay_fails_loudly`; `apps/devops-agent/tests/test_unsafe_infra_action.py` :: `test_offline_tool_registry_refuses_destructive_handlers`, `test_destructive_action_replays_without_touching_the_cloud`; `apps/support-agent/tests/test_duplicate_refund.py` :: `test_replaying_the_duplicate_refund_never_touches_the_gateway` |
| 2.6 | `test_replay.py` :: `test_replay_requires_reference` |
| 3.1–3.2 | `test_replay.py` :: `test_changed_arguments_are_reported_as_divergence`, `test_changed_execution_path_is_reported`; `test_edge_cases.py` :: `test_reordered_interactions_diverge_at_the_first_swapped_call` |
| 3.3 | `test_replay.py` :: `test_missing_recording_raises`; `test_edge_cases.py` :: `test_replay_of_truncated_recording_reports_missing_recording`, `test_unexpected_extra_tool_call_during_replay_is_not_executed` |
| 3.4 | `test_replay.py` :: `test_incomplete_replay_is_reported` |
| 3.6 | `test_mutation.py` :: `test_branch_without_faults_stays_on_track_and_verifies_tools` (on-track path only — no dedicated `result_mismatch` test yet, see task 11) |
| 4.1–4.3 | `test_edge_cases.py` :: `test_recording_with_out_of_order_events_is_rejected`, `test_malformed_execution_documents_fail_with_useful_errors`, `test_malformed_case_file_is_rejected`, `test_exported_trace_roundtrips_and_tampering_is_detected`; `test_security_storage.py` :: `test_trace_export_import_roundtrip_validates` |
| 4.4 | `test_security_storage.py` :: `test_safe_join_rejects_traversal` |
| 5.1–5.5 | `test_security_storage.py` :: `test_executions_persist_across_store_instances`; `test_edge_cases.py` :: `test_file_store_uses_wal_and_survives_reopen`, `test_store_prunes_oldest_executions_beyond_the_cap`, `test_corrupt_store_row_is_reported_on_get_and_skipped_in_list` |
| 6.1–6.3 | `test_diff_regression_server.py` :: `test_diff_identifies_first_divergence_and_changes`, `test_diff_added_and_removed_calls` |
| 7.1–7.5 | `test_live_model.py` :: `test_live_mode_is_off_unless_explicitly_enabled`, `test_scripted_lab_refuses_live_runs`, `test_tool_names_are_encoded_reversibly`, `test_tool_results_are_grouped_into_one_user_turn`, `test_provider_blocks_are_echoed_and_fallback_boundary_respected`, `test_refusal_is_an_error_not_a_silent_success`, `test_call_budget_is_enforced`, `test_live_run_is_recorded_with_provenance_and_native_requests`, `test_live_recording_replays_offline_without_calling_the_api`, `test_branching_a_live_recording_requires_live_mode`, `test_budget_exhaustion_fails_the_run_loudly` |
| 7.6, 8.3–8.6 | `tests/test_deployment.py` :: `test_both_labs_are_discoverable_as_independent_apps`, `test_gateway_serves_both_labs_health_and_dashboard`, `test_gateway_runs_the_full_demo_through_the_mounted_api`, `test_public_profile_disables_live_mode_and_clearing`, `test_public_profile_rate_limits_and_caps_bodies`, `test_public_store_keeps_a_bounded_number_of_executions`, `test_rate_limiter_window_slides`, `test_local_profile_is_unrestricted_by_default` |
| 8.1–8.2 | `test_diff_regression_server.py` :: `test_http_api_end_to_end`, `test_replay_stream_emits_engine_events` |

## Verification

```bash
uv run pytest packages/ghostreplay/tests -q
uv run pytest tests/test_deployment.py -q
uv run pytest packages/ghostreplay/tests/test_live_model.py -q
uv run ruff check . && uv run ruff format --check .
```

Manual: `uv run support-agent-lab run --incident` records a run; the dashboard's Replay Studio
replays it and shows every row as `recorded` / `matched`.
