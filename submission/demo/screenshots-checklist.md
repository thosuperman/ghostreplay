# Screenshots checklist

Real screenshots for the Devpost gallery and the README. Capture them from a running
instance (see `recording-guide.md` for setup), at a browser window of 1440 × 900 or larger so
the header badges are visible. Do not edit numbers, verdicts or labels in any image.

Screenshots live in `docs/assets/screenshots/` and are used by the README; upload the same
files to Devpost. Several already exist (marked "exists" below). Before submitting, open each
existing file and confirm it matches the final build (labels, numbers, both demo buttons);
recapture it under the same name if not. Devpost shows images at 3:2; leave some margin.

## Dashboard (both labs)

| # | File name | Status | Screen | Must show |
|---|---|---|---|---|
| 1 | `home.png` | exists, verify | Home (`#/`) | Headline, both demo cards ("Try the Duplicate Refund Demo", "Try the Unsafe Infrastructure Demo"), header badges "offline · simulated backends" and "scripted models" |
| 2 | `story-duplicate-refund.png` | exists, verify | Guided demo, Support Agent Lab | "✓ bug reproduced", "✓ fix proven", failed refund invariants with $129 vs $258 |
| 3 | `replay-studio.png` | exists, verify | Replay Studio after a replay | Streamed rows with "✓ matched", recording vs replay engine |
| 4 | `failure-lab.png` | exists, verify | Counterfactual Failure Lab | Preset "★ Refund times out after commit", "requires branch execution", a result verdict |
| 5 | `failure-lab-fixed.png` | to capture (optional) | Counterfactual Failure Lab | Same preset, "Idempotent harness (fixed)", result PASS |
| 6 | `diff.png` | exists, verify | Structural Diff | "first divergence" row, behavioural differences table |
| 7 | `regression.png` | exists, verify | Regression Results | Vulnerable FAIL with "expected FAIL ✓", fixed PASS with "expected PASS ✓" |
| 8 | `story-unsafe-aws-operation.png` | exists, verify | Guided demo, DevOps Agent Lab | `infra.capacity_preserved` FAIL ("0 … left running (minimum 2)") and the fixed run passing |
| 9 | `timeline.png` | exists, verify | Execution view (Timeline and Inspector) | Source badges, an event with its request, response and state |
| 10 | `live-ai-option.png` | to capture (optional) | Execution Explorer with live mode enabled locally | The "Model" select with "Scripted (offline, reproducible)" and the "Live AI: …" option. Only if you actually ran live mode; never in the public profile |

## Terminal

| # | File name | Command | Must show |
|---|---|---|---|
| 11 | `terminal-demo.png` | `uv run support-agent-lab --db "$TMPDIR/gr-shot" demo` | Six steps with verdicts and "Demo check passed" |
| 12 | `terminal-regression.png` | `uv run pytest tests/regression -q` or `uv run ghostreplay test tests/regression` | Regression cases passing |

## GitHub (only once true)

| # | File name | Screen | Condition |
|---|---|---|---|
| 13 | `ci-green.png` | GitHub Actions run summary | Only after CI has actually run green on GitHub |
| 14 | `deployed.png` | The deployed home page with the browser address bar | Only after the app is actually deployed |

## Kiro (only from real sessions)

Capture these while doing the real Kiro work described in `docs/kiro-workflow.md`. Do not
stage or mock them.

| # | File name | Screen |
|---|---|---|
| 15 | `kiro-steering.png` | Kiro showing the steering documents in `.kiro/steering/` |
| 16 | `kiro-spec.png` | A spec in `.kiro/specs/<component>/` (requirements, design or tasks view) |
| 17 | `kiro-task-run.png` | Kiro executing an open task from a `tasks.md` |
| 18 | `kiro-hook.png` | A hook from `.kiro/hooks/` firing, with its output |

## Before uploading

- [ ] No personal data, API keys, other tabs, notifications or account avatars visible.
- [ ] Text is readable at the Devpost gallery size (crop rather than shrink).
- [ ] Every image comes from the current build (labels match the dashboard).
- [ ] GitHub and Kiro images show things that really happened.
