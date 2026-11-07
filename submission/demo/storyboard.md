# Storyboard (shot list)

Companion to `video-script.md`. One row per shot. "Route" is the dashboard hash route
(`apps/dashboard/src/lib/router.ts`); lab ids are `support` and `devops`.

| # | Time | Route / app | Shot | Key on-screen element | Transition |
|---|---|---|---|---|---|
| 1 | 0:00 to 0:12 | Home (`#/`) | Static wide shot of the hero | Headline "Break AI agents safely. / Replay failures. Prove the fix." | Hard cut in |
| 2 | 0:12 to 0:22 | Home → Guided demo (support) | Cursor glides over both demo cards, clicks the primary one | Button card "Try the Duplicate Refund Demo"; then "Preparing the demo with real executions…" checklist | Live click |
| 3 | 0:22 to 0:38 | Guided demo (support), step 1 | Slow zoom (in editing) on the failed invariants | "✓ bug reproduced", "✓ fix proven", step 1 "The incident" FAIL, `refund.no_duplicate` | Live scroll |
| 4 | 0:38 to 0:46 | Guided demo, step 2 | Hold on the four metrics | "tool handlers invoked 0", "network blocked", "identical" | Live scroll |
| 5 | 0:46 to 0:58 | Replay Studio (support) | Click start, rows stream in | "▶ Start offline replay", "Replay engine", "✓ matched" | Live click |
| 6 | 0:58 to 1:08 | Guided demo, step 3 | Highlight (in editing) the evidence card | Timeout error on `payments.create_refund`, "observable state after" | Browser back |
| 7 | 1:08 to 1:20 | Failure Lab (support) | Click preset, point at branch badge | "Counterfactual Failure Lab", "★ Refund times out after commit", "requires branch execution" | Live click |
| 8 | 1:20 to 1:33 | Failure Lab | Run, result appears | "⚡ Inject failure and run", "3 · Result" FAIL | Live click |
| 9 | 1:33 to 1:46 | Failure Lab | Switch variant, run again | "Agent variant under test" → "Idempotent harness (fixed)", result PASS | Live click |
| 10 | 1:46 to 1:56 | Guided demo step 5 → Diff | Table flips FAIL → PASS, then diff view | "First divergence between vulnerable and fixed", "Open side-by-side diff →", "first divergence" badge | Browser back, live click |
| 11 | 1:56 to 2:10 | Regression Results (support) | Run cases, generate pytest | "▶ Run against every agent variant", "expected FAIL ✓", "expected PASS ✓", "Generate" | Live click |
| 11b | (optional, 2 s) | Terminal | `uv run pytest tests/regression -q` output | green dots / passed summary | Cut |
| 12 | 2:10 to 2:20 | Guided demo (devops) | Switch labs, incident loads | Header switch "DevOps Agent Lab" or "Try the Unsafe Infrastructure Demo"; `infra.capacity_preserved` FAIL | Live click |
| 13 | 2:20 to 2:33 | Guided demo (devops), step 5 | Hold on vulnerable vs fixed | Invariant table, "Vulnerable agent told the user" / "Fixed agent told the user" | Live scroll |
| 14 | 2:33 to 2:50 | Kiro (real session only) | Spec task, hook run, result | `.kiro/specs/...`, `.kiro/hooks/...` output | Cut |
| 15 | 2:50 to 2:57 | Home | Logo and tagline, lower-third with repository URL and `<DEPLOYED_URL>` | Hero | Fade out |

## Visual conventions

- Dark theme as shipped; do not restyle for the video.
- Keep the header badges "offline · simulated backends" and "scripted models" visible in at
  least shots 3 and 12 (window width of 1280 px or more).
- Cursor: enlarged pointer, highlight clicks with a subtle ring (configure in the recorder).
- Zooms and highlights are added in editing only; never edit numbers or verdicts.
- Lower-thirds: plain text, no logos of third-party products.

## Audio

- Narration only, recorded separately from the screen capture (see `recording-guide.md`).
- Optional quiet background track with a license that allows use in a public video; credit
  it in the video description if required.
