# Design — Dashboard

Written after the implementation; it records the decisions in the current code and the design
of the planned tasks.

## Structure (`apps/dashboard/src/`)

| Path | Responsibility |
|---|---|
| `api/client.ts` | `LABS` (support/devops: base path, demo label, tagline), `request` with actionable errors, `api.*` for every endpoint, `replayStreamUrl` |
| `api/types.ts` | TypeScript mirror of the Pydantic schema and API payloads |
| `lib/router.ts` | hash router: `#/<lab>/<section>/<id>?…` (`story`, `executions`, `replay`, `failure-lab`, `diff`, `regression`) |
| `lib/format.ts`, `lib/jsondiff.ts`, `lib/useAsync.ts` | formatting, client-side JSON diff, async state hook |
| `components/ui.tsx` | Badge, Button, Card, Select, JsonView, ModeBadge, SourceBadge, VerdictChip, InvariantBadge, Stat, … |
| `components/execution.tsx` | `Timeline`, `Inspector`, `InvariantList`, `ExecutionPicker`, `verdictOf` |
| `components/FaultSummary.tsx` | before/after view of an injected fault |
| `views/` | `Home`, `Story`, `Explorer`, `ExecutionView`, `ReplayStudio`, `FailureLab`, `DiffView`, `Regression` |
| `App.tsx` | shell: header, lab switcher with health dots, navigation |
| `e2e/` (outside `src`) | Playwright specs `demos.spec.ts`, `flows.spec.ts`, shared `fixtures.ts`; `playwright.config.ts` starts `ghostreplay serve` on port 8199 with a fresh store |

## Decisions and rationale

### D1 — One client, two labs, same paths everywhere
The lab id is part of the route; requests go to `/lab/<id>/api/...`. Vite proxies those paths
in development and the gateway mounts the same paths in production. *Rationale:* the build is
identical in both environments, and each lab remains an independent server.

### D2 — Show only stored, real executions
Views render what the lab API returns; there is no canned demo data. The guided story calls
`/api/demo/prepare`, which runs the engine. *Rationale:* the product's credibility depends on
every row being a real execution (the e2e demo test checks the stored modes).

### D3 — SSE paced by the engine
Replay Studio opens an `EventSource`; `delay_ms` makes the replay thread sleep per event.
*Rationale:* the animation reflects real engine progress rather than a scripted animation.

### D4 — The catalog drives the Failure Lab
Fault kinds come from `/api/faults` (strategy, `requires_branch`, params); only default JSON
params live in the UI (`DEFAULT_PARAMS`). *Rationale:* a new fault kind needs at most one line
of UI code.

### D5 — Labels over polish
Mode, source and provenance badges appear wherever events or executions do; the Story shows a
warning when the demo did not meet its expectations instead of hiding it.

### D6 — Visual language
Background `#07080d`, surfaces `#0d0f17`/`#121522`, hairline borders, Inter + JetBrains Mono
(fontsource). Accent violet, replay cyan, success emerald, warning amber, failure rose,
injected fuchsia. Motion 150–250 ms.

## Planned design — Requirement 8 (Inspector model-call details)
- In `components/execution.tsx` `Inspector`, when `event.kind === "model_call"` and
  `event.response` is an object, read `usage` (record of numbers) and `served_by` (string |
  undefined) with narrowing (no `any`); render a compact `Stat` row above the response JSON.
- "Copy as JSON" button: `navigator.clipboard.writeText(JSON.stringify(event, null, 2))` with a
  transient "Copied" state (same pattern as `Regression.tsx`). Add an accessible name.
- e2e: in `flows.spec.ts`, open a recorded execution, click the first model-call row, assert
  `usage` text and the copy button.

## Planned design — Requirement 9 (Explorer provenance badge)
- `ExecutionSummary.model_provider` already exists in `types.ts`; render
  `<Badge tone={live ? "amber" : "neutral"}>{live ? "live" : "scripted"}</Badge>` in each row.
- e2e: extend "explorer records a run and opens its timeline" to assert the badge in the list.

## Test coverage map

| Requirement | Tests |
|---|---|
| 1.1–1.2 | `apps/dashboard/e2e/demos.spec.ts` :: "home page offers both one-click demos", "<lab>: one click runs the full story on real executions" |
| 1.3 | `demos.spec.ts` asserts no alert when the story is `ok`; backend `ok` logic: `packages/ghostreplay/tests/test_edge_cases.py` :: `test_demo_story_reports_whether_every_step_met_expectations` |
| 2.1 | `flows.spec.ts` :: "explorer records a run and opens its timeline" |
| 2.3 | `flows.spec.ts` :: "replay studio streams an offline replay that matches the recording" |
| 2.4 | `flows.spec.ts` :: "failure lab injects the headline fault and the fixed agent passes" |
| 2.5 | `flows.spec.ts` :: "diff view shows the first divergence between vulnerable and fixed runs" |
| 2.6 | `flows.spec.ts` :: "regression view runs the case for every variant with opposite verdicts" |
| 2.x | `flows.spec.ts` :: "every route renders without browser errors" |
| 3.1 | `flows.spec.ts` (scripted label visible in the timeline) |
| 4.1–4.2 | no automated test yet (e2e starts the gateway without `GHOSTREPLAY_LIVE`, so only 4.2 is exercised implicitly) |
| 5.x | `flows.spec.ts` :: "health endpoints report both labs" |
| 7.1 | CI `dashboard` job (`typecheck`, `build`) |

## Verification

```bash
corepack pnpm --dir apps/dashboard typecheck
corepack pnpm --dir apps/dashboard build
corepack pnpm --dir apps/dashboard exec playwright install chromium   # once
corepack pnpm --dir apps/dashboard e2e
```

Manual: `./scripts/dev.sh`, open http://127.0.0.1:5173, click both demo cards; with
`GHOSTREPLAY_LIVE=1` set for the lab servers the Explorer shows the "Model" selector.
