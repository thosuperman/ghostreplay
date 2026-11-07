# Design — Dashboard

## Structure (`apps/dashboard/src/`)
- `api/` — typed client (`client.ts`), types mirroring Pydantic models (`types.ts`), lab list.
- `lib/` — tiny hash router, formatting helpers.
- `components/` — Badge, Button, Card, JsonView, EventRow, InvariantList, StatusPill, Empty.
- `views/` — Home, Story (guided demo), Explorer, ExecutionView (timeline + inspector),
  ReplayStudio, FailureLab, DiffView, Regression.

## Lab routing
`/lab/support/*` → `127.0.0.1:8101`, `/lab/devops/*` → `127.0.0.1:8102` (Vite proxy). The lab
is part of the hash route: `#/support/executions/<id>`.

## Visual language
Background `#07080d`, surfaces `#0d0f17`/`#121522`, hairline borders, Inter + JetBrains Mono.
Accent violet `#8b5cf6`, replay cyan `#22d3ee`, success emerald, warning amber, failure rose,
injected fuchsia. Motion: 150–250 ms fades/slides; replay stream rows animate in as the SSE
events arrive.
