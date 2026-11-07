---
inclusion: always
---

# Security requirements

1. **No real side effects, ever.** Every tool in the demo apps is backed by an in-memory
   simulated service. The repository never imports boto3, payment SDKs or HTTP clients for
   production services. No real AWS credentials are needed or read.
2. **Offline replay is enforced, not assumed.** In `replay` mode tool handlers are never
   invoked and an offline guard blocks socket connections from the replaying thread.
3. **Allowlisted tools only.** Agents may call only tools registered in their `ToolRegistry`;
   arguments are validated with Pydantic models where declared.
4. **Traces are data.** Trace and regression-case files are parsed with Pydantic. Nothing in
   a trace is executed, imported or evaluated. Error types are rebuilt through an allowlist.
   Scenarios are resolved by id from an explicit registry, never by import path from a file.
5. **Redaction before persistence.** The `Redactor` scrubs secret-looking keys (api_key,
   authorization, password, token, secret, card_number, ...) and values (AWS access keys,
   bearer tokens, `sk-` keys, Luhn-valid card numbers) before an event is stored.
6. **Path safety.** Import/export only inside configured directories; file names are
   sanitised and resolved paths are checked against the base directory.
7. **Useful errors.** Missing recordings, unexpected calls and divergence raise explicit errors
   and are recorded; nothing silently succeeds.
8. **Local only.** Servers bind to 127.0.0.1 by default; CORS allows only local dev origins.
