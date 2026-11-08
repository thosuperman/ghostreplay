# Implementation plan — Replay engine

> Tasks marked `[x]` predate this spec; open `[ ]` tasks are carried out in Kiro (prompts:
> `docs/kiro-demo-prompts.md`).

- [x] 1. Versioned schema and core utilities
  - `models/`: `Event`, `Execution`, `ExecutionSummary`, `Divergence`, `Provenance`, enums
  - `core/canonical.py` (stable hash, deep diff, JSON paths), `core/clock.py`, `core/errors.py`
  - _Requirements: 1.1, 1.3_

- [x] 2. Recording with redaction
  - `Recorder.emit` with sequencing and listeners; `Redactor` (keys, AWS keys, bearer tokens,
    `sk-` keys, GitHub tokens, private keys, Luhn-valid cards)
  - `AgentRuntime` (`complete`, `call_tool`, `now`, `new_id`, `random`, `log`, `guard`)
  - Tests: `test_recording_has_ordered_complete_events`, `test_redactor_scrubs_keys_and_values_but_keeps_benign_fields`, `test_recorder_persists_only_redacted_payloads`
  - _Requirements: 1.1, 1.2, 1.4, 1.5, 1.6_

- [x] 3. Allowlisted tools and simulated backends
  - `ToolRegistry` + `ToolSpec` (Pydantic args, `destructive`, `observe`, `match_fields`,
    `offline_copy`); simulated HTTP service, database and AWS-like cloud; `ScriptedModel`
  - Tests: `test_tool_registry_is_an_allowlist_with_validation`, `test_unknown_tool_call_is_recorded_as_error_not_executed`
  - _Requirements: 2.2_

- [x] 4. Deterministic offline replay
  - `Session.interact` record/replay policies, recorded errors via allowlist, virtual clock
    advanced by recorded durations; `offline_guard` (thread-local socket block)
  - Tests: `test_replay_is_structurally_identical_to_recording`, `test_replay_twice_is_reproducible`, `test_replay_never_invokes_tool_handlers_or_model`, `test_recorded_errors_are_replayed_with_their_type`, `test_nondeterminism_is_recorded_and_replayed`, `test_offline_guard_blocks_sockets_only_in_guarded_thread`, `test_agent_network_access_during_replay_fails_loudly`, `test_replay_requires_reference`
  - _Requirements: 2.1–2.6_

- [x] 5. Divergence detection
  - `mismatch` (path or inputs), `unexpected_call` (`MissingRecordingError`), `incomplete`
    (`Session.finish`), `result_mismatch` (branch verification)
  - Tests: `test_changed_arguments_are_reported_as_divergence`, `test_changed_execution_path_is_reported`, `test_missing_recording_raises`, `test_incomplete_replay_is_reported`, `test_replay_of_truncated_recording_reports_missing_recording`, `test_reordered_interactions_diverge_at_the_first_swapped_call`, `test_unexpected_extra_tool_call_during_replay_is_not_executed`
  - _Requirements: 3.1–3.6_

- [x] 6. Execution integrity and safe loading
  - `Execution._check_integrity` (seq order, unique event ids, schema version);
    `parse_document` → `TraceFormatError`; `safe_join`; 20 MiB size caps
  - Tests: `test_recording_with_out_of_order_events_is_rejected`, `test_malformed_execution_documents_fail_with_useful_errors`, `test_malformed_case_file_is_rejected`, `test_exported_trace_roundtrips_and_tampering_is_detected`, `test_trace_export_import_roundtrip_validates`, `test_safe_join_rejects_traversal`
  - _Requirements: 4.1–4.5_

- [x] 7. SQLite persistence
  - WAL + `synchronous=NORMAL`, per-app retention cap pruned in the insert transaction,
    `ping()`, `count()`, unreadable rows skipped in `list()`
  - Tests: `test_executions_persist_across_store_instances`, `test_file_store_uses_wal_and_survives_reopen`, `test_store_prunes_oldest_executions_beyond_the_cap`, `test_corrupt_store_row_is_reported_on_get_and_skipped_in_list`
  - _Requirements: 5.1–5.5_

- [x] 8. Structural diff
  - `diff_executions`: SequenceMatcher alignment, typed entries, first divergence, behaviour
  - Tests: `test_diff_identifies_first_divergence_and_changes`, `test_diff_added_and_removed_calls`
  - _Requirements: 6.1–6.3_

- [x] 9. Optional live LLM mode
  - `LiveModelConfig.from_env` (`GHOSTREPLAY_LIVE*`), `AnthropicModel` (tool-name encoding,
    grouped tool results, block echo, refusal → error, call budget), `Lab._model_for`
  - Tests: all 11 tests in `packages/ghostreplay/tests/test_live_model.py`
  - _Requirements: 7.1–7.6_

- [x] 10. HTTP API, SSE replay stream, gateway and public profile
  - `create_app` endpoints + `/healthz` + `/api/health`; SSE stream paced by `delay_ms`;
    `create_gateway` over `ghostreplay.labs`; `ServerSettings.from_env`, `RateLimiter`,
    concurrency semaphore, body cap; Dockerfile, `compose.yaml`, `render.yaml`
  - Tests: `test_http_api_end_to_end`, `test_replay_stream_emits_engine_events`, all 8 tests in `tests/test_deployment.py`
  - _Requirements: 8.1–8.6_

- [ ] 11. Report the exact field for `result_mismatch` and test it
  - In `Session._verify`, include the first differing `changes[*].path` values in the
    divergence message (mirror `_check`)
  - Add `test_branch_reports_the_first_differing_result_field` to
    `packages/ghostreplay/tests/test_edge_cases.py`: tamper one recorded tool response in a
    toy-bank recording, run `lab.counterfactual(..., [], mode="branch")`, assert
    `divergence.type == "result_mismatch"` and the path is named
  - Verify: `uv run pytest packages/ghostreplay/tests -q -x`
  - _Requirements: 3.6, 10.1, 10.2_

- [ ] 12. Provenance verification: recompute match keys on load
  - 12.1 Add `recompute_match_keys(execution, tools=None)` in a new
    `packages/ghostreplay/src/ghostreplay/replay/verify.py` (respect `ToolSpec.match_fields`)
  - 12.2 Add `strict: bool = False` to `storage.files.import_execution`; raise
    `TraceFormatError` listing mismatches when strict
  - 12.3 Add `ghostreplay verify <files...>` to `cli.py` (exit 1 on mismatch)
  - 12.4 Tests in `test_edge_cases.py`: untouched export verifies clean; editing a recorded
    request without updating `match_key` is reported with its `seq`; duplicate `event_id` with
    increasing `seq` is rejected (no dedicated test exists for that path today)
  - Verify: `uv run pytest packages/ghostreplay/tests -q -x` and
    `uv run ghostreplay verify <exported trace>`
  - _Requirements: 4.3, 9.1, 9.2, 9.3_
