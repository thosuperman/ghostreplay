# Devpost submission checklist

Status legend: **[x]** done in the repository, **[ ]** still to do. Items marked **(owner)**
need the project owner: an account, a decision, or work that cannot be done from the code.

Status as of 2026-11-07. Before submitting, check every requirement against the official
Kiroween rules page; this checklist does not replace it.

## 1. Code and repository

- [x] Open-source license at the repository root (`LICENSE`, MIT).
- [x] README with quick start, architecture, honest limitations and Kiro artifacts section.
- [x] Community files: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CHANGELOG.md`,
      `THIRD_PARTY_NOTICES.md`, issue forms and pull request template.
- [x] `.kiro/` directory (steering, specs, hooks) at the root and **not** listed in
      `.gitignore`. Re-check before the final push:
      `git check-ignore -v .kiro/steering/product.md || echo "not ignored"`.
- [x] Two applications on one shared framework (Skeleton Crew): `apps/support-agent` and
      `apps/devops-agent` on `packages/ghostreplay`.
- [x] CI workflow in `.github/workflows/ci.yml` (Python, Dashboard, End-to-end, Container).
- [ ] **(owner)** Commit and push the current work. At the time of writing, `origin/main`
      only contains the initial commit; the CI workflow, deployment files and these
      documents are not on GitHub yet. See [Publish](#publish-commands).
- [ ] **(owner)** Confirm CI is green on GitHub. CI has never run on GitHub so far.
- [ ] **(owner)** Confirm the repository is public. `gh repo view` reported `PUBLIC` on
      2026-11-07; re-check before submitting.
- [ ] **(owner)** Set the repository description, website and topics.
- [ ] **(owner)** Upload a social preview image (see [Repository presentation](#repository-presentation)).

## 2. Hosted demo

- [x] One-container deployment (`Dockerfile`, `compose.yaml`) and Render Blueprint (`render.yaml`).
- [x] Public deployment profile (`GHOSTREPLAY_PUBLIC=1`) with rate limits; live AI mode is
      forced off in that profile.
- [ ] **(owner)** Deploy (Render: New → Blueprint → select the repository; see
      `docs/deployment.md`). Nothing is deployed yet.
- [ ] **(owner)** Verify the deployment:

      curl -fsS <DEPLOYED_URL>/api/health
      E2E_BASE_URL=<DEPLOYED_URL> corepack pnpm --dir apps/dashboard e2e:only

- [ ] **(owner)** Click both "Try the Duplicate Refund Demo" and "Try the Unsafe AWS
      Operation Demo" on the deployment and confirm both stories show "bug reproduced" and
      "fix proven".
- [ ] Replace every `<DEPLOYED_URL — add after deployment>` placeholder (README, description).
      Find them with: `grep -rn "DEPLOYED_URL" --include='*.md' .`

## 3. Video

- [x] Script, storyboard, recording guide and screenshot list in `submission/demo/`.
- [ ] **(owner)** Run real Kiro sessions first (section 4) so the Kiro segment shows real work.
- [ ] **(owner)** Record the video (under 3:00) following `submission/demo/recording-guide.md`.
- [ ] **(owner)** Upload it (YouTube or Vimeo, public or unlisted as the rules allow) and
      replace `<VIDEO_URL>`.
- [ ] Check the video: no API keys, no personal notifications, no private browser tabs,
      readable text, audio levels consistent.

## 4. Kiro usage (must be genuine)

- [x] `.kiro/steering/`, `.kiro/specs/` and `.kiro/hooks/` committed. They document the
      implementation and were written after it.
- [ ] **(owner)** Do real work in Kiro: pick open (unchecked) tasks from `.kiro/specs/*/tasks.md`,
      execute them in Kiro, let the hooks run, and commit the results with honest commit
      messages. Follow `docs/kiro-workflow.md` for the capture procedure.
- [ ] **(owner)** Capture evidence while working: screenshots of the spec view, a task being
      executed, a hook firing and its output (see `submission/demo/screenshots-checklist.md`).
- [ ] **(owner)** Fill in the `TO BE COMPLETED BY THE AUTHOR` block in
      `submission/devpost/description.md` with what actually happened, then delete the comment
      markers. Do not add numbers, timelines or logs you did not capture.

## 5. Devpost form

- [ ] **(owner)** Project name: `submission/devpost/title.md`.
- [ ] **(owner)** Elevator pitch / tagline: `submission/devpost/tagline.md`.
- [ ] **(owner)** Story / description: paste `submission/devpost/description.md` (after
      completing the Kiro section and replacing placeholders).
- [ ] **(owner)** Built with: tags from `submission/devpost/technologies.md`.
- [ ] **(owner)** Category: Skeleton Crew. Explain the shared framework and the two apps
      (the "Skeleton Crew" section of the description does this).
- [ ] **(owner)** Links: repository URL, `<DEPLOYED_URL>`, `<VIDEO_URL>`.
- [ ] **(owner)** Image gallery: real screenshots from `submission/demo/screenshots-checklist.md`
      plus the banner from `docs/assets/`.
- [ ] **(owner)** Team members and any additional questions the form asks.
- [ ] **(owner)** Submit before the deadline and keep a copy of the confirmation.

## 6. Final consistency pass

- [ ] Every claim in README, description and video matches the code (fault count, invariant
      names, dollar amounts, button labels).
- [ ] No text claims the app is deployed, the video exists or CI passed before that is true.
- [ ] No AI attribution in commits, PR text or committed docs.
- [ ] Both terminal demos pass locally:

      uv run support-agent-lab --db "$TMPDIR/gr-final" demo
      uv run devops-agent-lab --db "$TMPDIR/gr-final" demo

## Publish commands

Review what will be committed first:

```bash
git status
git diff --stat
```

Commit with a Conventional Commit message, then push:

```bash
git add -A
git commit -m "docs: add community files and submission package"
git push origin main
```

Watch CI:

```bash
gh run list --limit 5
```

```bash
gh run watch
```

Making the repository public is the owner's decision and has consequences (the code,
history and issues become visible to everyone). Only if it is not already public:

```bash
gh repo edit thosuperman/ghost-replay --visibility public --accept-visibility-change-consequences
```

Repository metadata (adjust the website once deployed):

```bash
gh repo edit thosuperman/ghost-replay \
  --description "Break AI agents safely. Replay failures. Prove the fix. Deterministic replay and failure injection for tool-using AI agents." \
  --add-topic ai-agents --add-topic llm --add-topic testing --add-topic deterministic-replay \
  --add-topic fault-injection --add-topic regression-testing --add-topic kiro
```

```bash
gh repo edit thosuperman/ghost-replay --homepage "<DEPLOYED_URL>"
```

## Repository presentation

- Social preview: GitHub only accepts PNG, JPG or GIF (recommended 1280×640) and only through
  the web UI: **Settings → General → Social preview → Edit → Upload an image**. Upload
  `docs/assets/social-preview.png` (1280×640 on 2026-11-07). Open it first to check that the
  text renders correctly. If you change the SVG, re-export it, for example:

  ```bash
  rsvg-convert -w 1280 -h 640 docs/assets/social-preview.svg -o docs/assets/social-preview.png
  ```
