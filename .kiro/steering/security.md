---
inclusion: always
---

# Security requirements

1. **No real side effects, ever.** Every tool in the demo apps is backed by an in-memory
   simulated service (`ghostreplay.mocking`). Never import boto3, payment SDKs or HTTP clients
   aimed at production services. No real AWS credentials are needed or read. Live AI mode
   changes only the model; tools stay simulated.
2. **Offline replay is enforced, not assumed.** In `replay` / `counterfactual-replay` no model
   adapter exists, tool handlers are replaced by stubs that raise (`ToolRegistry.offline_copy`),
   and `offline_guard()` blocks `socket.connect`, `connect_ex`, `create_connection` and
   `getaddrinfo` on the replaying thread (other server threads are unaffected).
3. **Allowlisted tools only.** Agents may call only tools registered in their `ToolRegistry`;
   arguments are validated with the tool's Pydantic model. Unknown tools are recorded as
   errors, never executed.
4. **Traces and cases are data.** Everything loaded from files, SQLite rows or HTTP bodies goes
   through Pydantic (`parse_document` → `TraceFormatError` on failure). `Execution` rejects
   out-of-order or duplicate events and unknown schema versions. Nothing in a trace is executed,
   imported or evaluated; recorded error types are rebuilt through an allowlist
   (`ToolError.from_info`); scenarios are resolved by id from entry points, never by import path.
5. **Redaction before persistence.** `Redactor` scrubs secret-looking keys (api_key,
   authorization, password, token, secret, card_number, ...) and values (AWS access key ids,
   bearer tokens, `sk-` keys, GitHub tokens, private keys, Luhn-valid card numbers) before an
   event is stored. Replay matching hashes the redacted request.
6. **Path safety.** Import/export only inside a base directory (`safe_join`): no separators,
   no `..`, resolved path must stay inside. Size caps: 20 MiB per trace or case file.
7. **Useful, loud errors.** Missing recordings, unexpected calls and divergence raise explicit
   errors and are recorded; nothing silently succeeds. A live-model refusal or exhausted call
   budget fails the run (`LiveModelError`), it is never recorded as success.
8. **Local by default.** Lab servers and the gateway bind to 127.0.0.1 unless told otherwise;
   CORS allows only local dev origins unless `GHOSTREPLAY_CORS_ORIGINS` is set.
9. **Public deployment profile** (`GHOSTREPLAY_PUBLIC=1`): per-client rate limit on mutating
   requests and replay streams, bounded concurrent engine runs (HTTP 503 beyond), request body
   cap (Content-Length required), clearing disabled, live mode forced off, retention cap on
   stored executions, per-visitor session isolation (an HttpOnly cookie scopes every read and
   write through `OwnedStore`; owned rows expire after 24 h; an upsert never overwrites another
   owner's row), capped replay-stream delay, no OpenAPI docs. Keep these defaults when
   touching `server/settings.py`, `server/app.py` or `storage/sqlite.py`.
   Production (AWS Lightsail) also runs each lab as a systemd service with no network access
   beyond loopback. See #[[file:docs/deployment/SECURITY.md]].
10. **Live credentials.** Provider keys are read by the provider SDK from the environment; they
    are never part of a recorded request. Never commit `.env`; `.env.example` lists variables
    without values.
11. **Secret scanning.** `scripts/secret_scan.py` (hook: `secret-scan`) must exit 0. A test
    fixture that deliberately contains a fake secret carries `# secret-scan: allow` on that
    exact line — never on real code.
