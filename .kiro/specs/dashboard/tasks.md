# Implementation plan — Dashboard

> **Provenance.** Tasks marked `[x]` were implemented before this repository was opened in
> Kiro; this spec was written afterwards to document them, and each one was checked against
> the current code. Unchecked `[ ]` tasks are real, not-yet-done improvements intended to be
> executed in Kiro (prompts: `docs/kiro-demo-prompts.md`).

- [x] 1. Vite + React + TypeScript strict + Tailwind v4 scaffold; dev proxy to both labs
  - _Requirements: 7.1_

- [x] 2. Typed API client and schema mirror (`src/api/client.ts`, `src/api/types.ts`)
  - _Requirements: 5.2, 6.1_

- [x] 3. Shell: header, lab switcher with health polling, navigation, hash router
  - _Requirements: 5.1_

- [x] 4. Home with two one-click demos ("Try the Duplicate Refund Demo", "Try the Unsafe AWS
  Operation Demo") and the guided Story, including the alert when `DemoStory.ok` is false
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 5. Execution Explorer (record under healthy/incident conditions)
  - _Requirements: 2.1_

- [x] 6. Timeline + Inspector with source, mode and provenance badges
  - _Requirements: 2.2, 3.1_

- [x] 7. Replay Studio over SSE with engine pacing
  - _Requirements: 2.3_

- [x] 8. Failure Lab driven by the fault catalog and scenario presets
  - _Requirements: 2.4_

- [x] 9. Diff view
  - _Requirements: 2.5_

- [x] 10. Regression view with pytest export
  - _Requirements: 2.6_

- [x] 11. "Live AI" model option in the Explorer, shown only when `/api/info` reports
  `live_model`
  - _Requirements: 4.1, 4.2_

- [x] 12. Playwright e2e suite (`apps/dashboard/e2e/`, `playwright.config.ts`, `e2e` script)
  against the gateway, plus the CI `e2e` job
  - Specs: `demos.spec.ts` (both demos), `flows.spec.ts` (explorer, replay studio, failure lab,
    diff, regression, route smoke test, health endpoints)
  - Note: this suite landed while these specs were being written; it was not executed as part
    of writing them
  - _Requirements: 7.2_

- [x] 13. Production build (`tsc --noEmit` + `vite build`) in CI
  - _Requirements: 7.1_

- [ ] 14. Inspector: token usage, `served_by` and "Copy as JSON" for model calls
  - 14.1 Render `response.usage` and `response.served_by` for `model_call` events in
    `components/execution.tsx` (`Inspector`), narrowing from `Json` without `any`
  - 14.2 Add a "Copy as JSON" button for the selected event
  - 14.3 e2e assertion in `apps/dashboard/e2e/flows.spec.ts`
  - Verify: `corepack pnpm --dir apps/dashboard typecheck && corepack pnpm --dir apps/dashboard e2e`
  - _Requirements: 8.1, 8.2, 8.3_

- [ ] 15. Explorer list: `live` / `scripted` provenance badge per execution
  - 15.1 Render the badge from `ExecutionSummary.model_provider` in `views/Explorer.tsx`
  - 15.2 Extend the explorer e2e test to assert `scripted` on a fresh run
  - Verify: `corepack pnpm --dir apps/dashboard typecheck && corepack pnpm --dir apps/dashboard e2e`
  - _Requirements: 9.1, 9.2_

- [ ] 16. Show default params for new fault kinds (`reordered_response`, `clock_skew`) in the
  Failure Lab once `.kiro/specs/failure-injection` tasks 8–9 land
  - _Requirements: 2.4_
