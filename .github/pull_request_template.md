## Summary

<!-- What does this change do, and why? Link related issues (Fixes #123). -->

## Type of change

- [ ] Bug fix
- [ ] New feature (fault kind, invariant, scenario, dashboard view, ...)
- [ ] Refactor or performance improvement
- [ ] Documentation
- [ ] Build, CI or deployment

## How was this tested?

<!-- Commands you ran, new or changed tests, screenshots for dashboard changes. -->

## Checklist

- [ ] Tests added or updated, and `uv run pytest` passes
- [ ] `uv run ruff check .` and `uv run ruff format --check .` pass
- [ ] `corepack pnpm --dir apps/dashboard typecheck` and `build` pass (if the dashboard changed)
- [ ] `corepack pnpm --dir apps/dashboard e2e` passes (if user-facing flows changed)
- [ ] Both terminal demos still pass (`uv run support-agent-lab --db "$TMPDIR/gr" demo`, `uv run devops-agent-lab --db "$TMPDIR/gr" demo`)
- [ ] Python schema and `apps/dashboard/src/api/types.ts` are in sync (if `models/` changed)
- [ ] Docs updated (`README.md`, `docs/`) and an entry added to `CHANGELOG.md` under `[Unreleased]`
- [ ] No secrets, `.env` files, credentials or real personal data in code, fixtures or recordings
- [ ] No real side effects: every tool is a simulation, and no real SDK client points at a real service
- [ ] Scripted, simulated and counterfactual results are labelled as such
- [ ] Commit messages follow Conventional Commits
