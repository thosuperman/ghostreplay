# Release checklist (v0.1.0)

Steps to publish the first release and get the public demo online. Items marked **(owner)**
need the repository owner. Nothing below has been done yet unless it is checked.

## Done in the repository

- [x] Version `0.1.0` in `pyproject.toml` (root, framework, both labs) and
      `apps/dashboard/package.json`.
- [x] `CHANGELOG.md` with a `[0.1.0]` section.
- [x] `LICENSE` (MIT) and `THIRD_PARTY_NOTICES.md`.
- [x] CI workflow, Dockerfile, `compose.yaml`, `render.yaml`.

## 1. Verify locally

Run the same checks as CI from a clean checkout:

```bash
uv sync --locked --all-extras
```

```bash
uv run ruff check . && uv run ruff format --check .
```

```bash
uv run pytest
```

```bash
uv run support-agent-lab --db "$TMPDIR/gr-release" demo && uv run devops-agent-lab --db "$TMPDIR/gr-release" demo
```

```bash
uv run ghostreplay test tests/regression --junit reports/junit.xml --json reports/report.json
```

```bash
corepack pnpm install --frozen-lockfile && corepack pnpm --dir apps/dashboard typecheck && corepack pnpm --dir apps/dashboard build
```

```bash
corepack pnpm --dir apps/dashboard exec playwright install chromium && corepack pnpm --dir apps/dashboard e2e
```

Container smoke test in the public profile:

```bash
docker build -t ghostreplay-lab:release .
```

```bash
docker run -d --name gr-release -p 8100:8100 -e GHOSTREPLAY_PUBLIC=1 ghostreplay-lab:release
```

```bash
curl -fsS http://127.0.0.1:8100/api/health && docker rm -f gr-release
```

- [ ] All of the above pass.
- [ ] `git status` shows no stray files (`.env`, `.ghostreplay/`, `reports/` are ignored).
- [ ] No secrets: `git grep -nE "sk-ant-|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}"` finds only
      intentional, clearly fake test fixtures.

## 2. Push and confirm CI **(owner)**

```bash
git push origin main
```

```bash
gh run watch
```

- [ ] All four CI jobs are green: "Python — lint, tests, demos, regressions",
      "Dashboard — typecheck and build", "End-to-end (Playwright)",
      "Container — build and smoke test".
- [ ] If a job fails, fix it and push again; do not tag a release on a red build.

## 3. Repository visibility and presentation **(owner)**

- [ ] Decide whether the repository should be public (it reported `PUBLIC` on 2026-11-07;
      re-check with `gh repo view --json visibility`). If it must be changed:

  ```bash
  gh repo edit thosuperman/ghost-replay --visibility public --accept-visibility-change-consequences
  ```

- [ ] Description, topics and homepage (see `submission/devpost/submission-checklist.md`).
- [ ] Social preview image: `docs/assets/social-preview.png` (1280×640) uploaded in
      **Settings → General → Social preview**.
- [ ] Enable private vulnerability reporting: **Settings → Code security → Private
      vulnerability reporting** (referenced by `SECURITY.md`).
- [ ] Replace `<CONTACT_EMAIL>` in `CODE_OF_CONDUCT.md` and `SECURITY.md`.

## 4. Deploy the public demo **(owner)**

1. Render: **New → Blueprint**, select the repository, confirm (uses `render.yaml`: Docker
   web service, public profile, 1 GB disk on a paid `starter` plan; on a free instance remove
   the `disk` block and accept that executions are lost on restart).
2. Wait for the `/api/health` check to pass.
3. Verify:

   ```bash
   curl -fsS https://ghostreplay.hayaix.tech/lab/support/api/health && curl -fsS https://ghostreplay.hayaix.tech/lab/devops/api/health
   ```

   ```bash
   E2E_BASE_URL=https://ghostreplay.hayaix.tech corepack pnpm --dir apps/dashboard e2e:only
   ```

4. Click both demo buttons on the home page.
5. The deployed URL (https://ghostreplay.hayaix.tech) is filled in across README and the submission files.

- [x] Deployed and verified (2026-11-07, AWS Lightsail; `docs/deployment/AWS_LIGHTSAIL.md`).

## 5. Tag the release **(owner)**

Only after CI is green on the commit you tag:

```bash
git tag -a v0.1.0 -m "GhostReplay Lab 0.1.0"
git push origin v0.1.0
```

```bash
gh release create v0.1.0 --title "GhostReplay Lab 0.1.0" --notes-file <(sed -n '/^## \[0.1.0\]/,/^\[Unreleased\]:/p' CHANGELOG.md | sed '$d')
```

- [ ] Release published; the notes contain no AI attribution.
- [ ] Update the compare links at the bottom of `CHANGELOG.md` if the repository URL changes.

## 6. After the release

- [ ] Move new entries under `[Unreleased]` in `CHANGELOG.md`.
- [ ] Keep `THIRD_PARTY_NOTICES.md` in sync when dependencies change.
