# Working on GhostReplay Lab in Kiro

A step-by-step rehearsal guide for doing real work on this repository in the Kiro IDE and
capturing honest evidence of it.

**Provenance, stated plainly.** GhostReplay Lab (framework, both labs, dashboard) was
implemented before the repository was opened in Kiro. The `.kiro/` steering, specs and hooks
were written afterwards to document that implementation and to set up further work. In every
`tasks.md`, `[x]` marks work that already existed; `[ ]` marks real improvements that have not
been done yet and are meant to be executed in Kiro. Only work you actually do in Kiro counts as
Kiro evidence.

Kiro's UI changes between versions. Where this guide names a button or panel, treat it as a
pointer and check the current documentation at https://kiro.dev/docs if something looks
different.

---

## 0. Prerequisites

```bash
uv sync
corepack pnpm install
uv run pytest -q                                   # baseline must be green
corepack pnpm --dir apps/dashboard typecheck
uv run python scripts/secret_scan.py               # exit 0
```

Create a working branch so every task becomes its own reviewable commit:

```bash
git switch -c kiro/<short-topic>
```

## 1. Open the repository in Kiro

Open the repository root (the folder that contains `.kiro/`). Kiro reads:

| Path | What it is |
|---|---|
| `.kiro/steering/*.md` | project knowledge loaded into agent context |
| `.kiro/specs/<feature>/{requirements,design,tasks}.md` | specs |
| `.kiro/hooks/*.json` | agent hooks (`version: "v1"`) |
| `.kiro/settings/mcp.json` | MCP servers (intentionally empty: `{"mcpServers": {}}`) |

## 2. Confirm steering loads

| File | Inclusion | When it is in context |
|---|---|---|
| `product.md` | `always` | every interaction |
| `tech.md` | `always` | every interaction |
| `structure.md` | `always` | every interaction |
| `security.md` | `always` | every interaction |
| `architecture.md` | `fileMatch` (`packages/ghostreplay/**/*.py`, `apps/support-agent/**/*.py`, `apps/devops-agent/**/*.py`) | when a matching file is involved |
| `conventions.md` | `fileMatch` (`**/*.py`, `**/*.ts`, `**/*.tsx`) | when a matching file is involved |
| `competition.md` | `manual` | only when you reference it in chat as `#competition` |

Steering files also pull in docs with `#[[file:...]]` references (`docs/architecture.md`,
`docs/live-ai.md`, `docs/deployment.md`, `.env.example`, the two Kiro docs).

Check it:

1. Open the Kiro panel and find the steering section; all seven files should be listed.
2. In a new chat, ask: *"Which execution modes and event sources does this project use?"* — the
   answer should come from `product.md` (record / replay / counterfactual-replay / branch;
   live / recorded / injected / simulated).
3. Open `packages/ghostreplay/src/ghostreplay/replay/session.py` and ask about
   `Session.interact`; the answer should reflect `architecture.md`.
4. Type `#competition` in chat and ask what P0 means for this project.

Screenshot the steering list (evidence item E1).

## 3. Review the specs

| Spec | Open tasks |
|---|---|
| `replay-engine` | 11 precise `result_mismatch` path; 12 match-key verification on load (`ghostreplay verify`) |
| `failure-injection` | 8 `reordered_response` fault; 9 `clock_skew` fault (schema change); 10 `export-cases --preset` + demo exit-code test |
| `support-agent-lab` | 10 `refund.within_line_total` + `eligibility-inflated-amount`; 11 partial-refund variant |
| `devops-agent-lab` | 10 `infra.approval_chain_valid`; 11 `probe-timeout` preset + honest recovery in the SafetyGate |
| `dashboard` | 14 Inspector usage / `served_by` / copy JSON; 15 Explorer provenance badge; 16 defaults for new fault kinds |

For each spec, read `requirements.md` (EARS acceptance criteria), then `design.md` (decisions,
test coverage map, verification commands), then `tasks.md`. Two open tasks describe gaps that
were reproduced before writing them down: inflated eligibility goes unnoticed by every support
invariant (support task 10), and the fixed DevOps agent fails `errors.surfaced` when its direct
probes time out (devops task 11). Starting with one of those gives a visible
failing-then-passing result.

## 4. Pick one open task and execute it from the spec

1. Open the spec's `tasks.md` in Kiro. Kiro shows an action next to each task to start it
   (labelled "Start task" in current versions).
2. Optionally paste the matching prompt from `docs/kiro-demo-prompts.md` into the chat to give
   the agent the acceptance criteria and verification commands in one place.
3. Let the agent work. Review every diff before accepting it. The spec says what "done" means;
   do not accept a change that edits a test to make it pass unless the test was wrong.
4. When the verification commands pass, mark the task `[x]` (Kiro may do this itself when the
   task completes; check the file).

Screenshot the task in progress and the completed task (E2, E3).

## 5. Run the tests yourself

The hooks run subsets automatically; always finish with the full checks:

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run python scripts/secret_scan.py
corepack pnpm --dir apps/dashboard typecheck
```

Task-specific extras:

```bash
uv run support-agent-lab --db /tmp/gr-demo demo           # exit 0 = every step as expected
uv run devops-agent-lab --db /tmp/gr-demo demo
uv run ghostreplay test tests/regression --junit reports/junit.xml --json reports/report.json
corepack pnpm --dir apps/dashboard e2e                     # dashboard tasks; needs Chromium:
corepack pnpm --dir apps/dashboard exec playwright install chromium
```

Save the terminal output (E4).

## 6. Watch the hooks fire

| Hook file | Trigger | Fires when you save … | Runs |
|---|---|---|---|
| `framework-tests.json` | `PostFileSave` | any `packages/ghostreplay/**.py` | `uv run pytest packages/ghostreplay/tests -q -x` |
| `scenario-regressions.json` | `PostFileSave` | any `apps/support-agent/**.py` or `apps/devops-agent/**.py` | `uv run pytest apps tests/regression -q -x` |
| `dashboard-typecheck.json` | `PostFileSave` | `apps/dashboard/src/**.ts(x)` | `corepack pnpm --dir apps/dashboard typecheck` |
| `schema-sync.json` | `PostFileSave` | `packages/ghostreplay/src/ghostreplay/models/*.py` | agent prompt: mirror the change in `apps/dashboard/src/api/types.ts`, then typecheck |
| `secret-scan.json` | `PostFileSave` | any `.py .json .ts .tsx .md .yml .yaml .toml` | `uv run python scripts/secret_scan.py` |
| `lint-on-stop.json` | `Stop` | the agent finishes a turn | `uv run ruff check . && uv run ruff format --check .` |

Notes:

- File-save hooks also fire when the *agent* edits and saves files, not only when you do. A
  single agent change can therefore trigger several hooks (a schema edit triggers
  `framework-tests`, `schema-sync` and `secret-scan`).
- `matcher` is a regular expression tested against the file path.
- Hooks can be toggled in the Kiro hooks panel or by setting `"enabled": false` in the JSON.
- Quick manual check: add a blank line to `apps/devops-agent/src/devops_agent/invariants.py`,
  save, and look for the scenario-regressions run; then revert the change.

Screenshot a hook run with its output (E5). If a hook fails, keep that screenshot too — a
caught regression is good evidence.

## 7. Commit honestly, one task per commit

```bash
git add -p
git commit -m "feat(devops): add infra.approval_chain_valid invariant"
```

- Use Conventional Commits; describe what changed and why.
- Reference the spec task in the body, e.g. `Spec: .kiro/specs/devops-agent-lab task 10`.
- Include the `tasks.md` checkbox update in the same commit.
- Do not add tool-attribution trailers, and do not describe pre-existing code as new work.

## 8. Evidence log (fill this in yourself)

Copy this table into your notes or a PR description and fill it in as you go. Use real
timestamps from your machine and real commit hashes; leave a row empty rather than guessing.

| # | Date/time (local) | Kiro version | Spec / task | What you did in Kiro | Hooks that fired (result) | Verification commands (result) | Commit | Screenshots |
|---|---|---|---|---|---|---|---|---|
| 1 | | | | | | | | |
| 2 | | | | | | | | |
| 3 | | | | | | | | |

Evidence items referenced above:

- **E1** steering list showing always / fileMatch / manual files
- **E2** spec task started from `tasks.md`
- **E3** completed task with the diff Kiro produced
- **E4** terminal output of the verification commands
- **E5** a hook run (and its output) triggered by a save

## 9. Checklist

- [ ] Baseline green before starting (`uv run pytest -q`, typecheck, secret scan)
- [ ] Working branch created
- [ ] Steering verified, `#competition` referenced once (E1)
- [ ] One open task chosen and read end to end (requirements → design → tasks)
- [ ] Task executed from the spec in Kiro (E2, E3)
- [ ] At least one hook observed firing on a save (E5)
- [ ] Full verification run and saved (E4)
- [ ] Task box ticked in `tasks.md` only after verification passed
- [ ] One honest commit per task, no attribution trailers
- [ ] Evidence log row filled in with real data
- [ ] README/docs updated if the task changed user-visible behaviour (for example the fault
      count in `README.md`)
