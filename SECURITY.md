# Security Policy

## Supported versions

GhostReplay Lab is young. Security fixes are made on the `main` branch and included in the
next release.

| Version | Supported |
|---|---|
| `main` | yes |
| 0.1.x | yes |
| older | no |

## Reporting a vulnerability

Please **do not open a public issue** for a security problem.

Report it privately through GitHub Security Advisories: open the repository on GitHub, go to
**Security → Advisories → Report a vulnerability**, and describe:

- what is affected (component, file, endpoint, version or commit),
- how to reproduce it (a minimal trace file, request or test is ideal),
- the impact you expect, and
- any suggested fix.

If private vulnerability reporting is not available, contact the maintainers at
`<CONTACT_EMAIL>` and include "SECURITY" in the subject.

We aim to acknowledge reports within a few days, agree a fix and disclosure timeline with
you, and credit you in the advisory unless you prefer not to be named.

## Scope and threat model

GhostReplay is a testing framework. Understanding what it does and does not do helps decide
whether something is a vulnerability.

**By design:**

- Every tool in the demo labs is an **in-memory simulation**. There are no real payment,
  cloud or infrastructure clients, and no real side effects. A "refund" or "terminated
  instance" only changes simulated state.
- Offline replay never invokes tool handlers or model adapters, and blocks socket access on
  the replaying thread.
- Secrets matching known patterns (keys, bearer tokens, `sk-` keys, AWS access keys,
  Luhn-valid card numbers, sensitive field names) are redacted before an event is stored.
- Trace and regression case files are validated data (Pydantic). Nothing in them is
  evaluated or executed; scenarios are resolved by id from installed entry points.
- File import and export are confined to a base directory.
- Local servers bind to 127.0.0.1. The container binds to 0.0.0.0 inside the container.

**Public deployment profile (`GHOSTREPLAY_PUBLIC=1`):**

- per-client rate limit on POST/DELETE requests and replay streams (default 30/min),
- a cap on concurrent engine runs (default 2; others receive HTTP 503),
- a request body cap (default 512 KiB),
- a cap on stored executions per lab (default 400; the oldest are pruned),
- clearing all executions is disabled,
- live LLM mode is disabled even if `GHOSTREPLAY_LIVE=1`.

See [docs/deployment.md](docs/deployment.md) for details.

**In scope**, for example:

- a way to make offline replay invoke a tool handler, a model adapter or the network,
- secrets that survive redaction and are persisted,
- path traversal or arbitrary file read or write through import, export or the API,
- code execution through trace files, case files or API requests,
- bypassing the public profile's limits or enabling live mode in the public profile,
- leaking the `ANTHROPIC_API_KEY` (or other credentials) into recordings, logs or API responses.

**Out of scope**, for example:

- the behaviour of the simulated agents themselves (the vulnerable variants are
  intentionally unsafe; that is the point of the demo),
- denial of service against a local development server, or volumetric attacks beyond the
  documented public-profile limits,
- vulnerabilities in third-party dependencies that do not affect GhostReplay (please report
  those upstream),
- code that integrators add outside `AgentRuntime`, which GhostReplay cannot replay or guard.

## Handling secrets

Never commit `.env` files, API keys or real customer data. The optional live LLM mode reads
credentials from the environment through the provider SDK; GhostReplay does not record them.
