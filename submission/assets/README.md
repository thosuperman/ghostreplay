# Submission assets

What visual material exists in the repository, and what the author still has to produce.

## Already in the repository

| Asset | Location | Notes |
|---|---|---|
| Logo, app icon, banner, social preview | `docs/assets/` | SVG sources with PNG exports (for example `banner.png`, `social-preview.png`). Check the folder for the current set. |
| Architecture and record/replay diagrams | `docs/assets/` | SVG with PNG exports, usable in the Devpost gallery. |
| Dashboard screenshots | `docs/assets/screenshots/` | Used by the README. Before submitting, confirm they match the final build (labels, numbers) and recapture any that are out of date. |
| Dashboard favicon / ghost mark | `apps/dashboard/public/ghost.svg` | |
| Video script, storyboard, recording guide, screenshot list | `submission/demo/` | Plans only; no video has been recorded. |
| Devpost texts | `submission/devpost/` | Title, tagline, description, technologies, challenges, checklist. |

### Format notes

- GitHub's social preview needs a PNG, JPG or GIF (1280 × 640 recommended) and can only be
  set in the web UI: **Settings → General → Social preview → Edit → Upload an image**. Use the
  PNG export in `docs/assets/` (check that it is 1280 × 640 and that the text renders
  correctly).
- Devpost gallery images: PNG or JPG; 3:2 works best. Crop rather than shrink small text.

## To be produced by the author

| Asset | How | Status |
|---|---|---|
| Demo video (under 3:00) | `submission/demo/recording-guide.md` and `video-script.md` | Not recorded. Replace `<VIDEO_URL>` once uploaded. |
| Kiro screenshots | Capture during real Kiro sessions (`docs/kiro-workflow.md`; items 15 to 18 in `submission/demo/screenshots-checklist.md`) | Not captured. Must be genuine. |
| Terminal screenshots | Items 11 and 12 in the screenshots checklist | Not captured. |
| CI screenshot | After CI has run green on GitHub | CI has not run on GitHub yet. |
| Deployed app screenshot and URL | After deployment (`docs/deployment.md`) | Not deployed. Replace `<DEPLOYED_URL — add after deployment>`. |
| Social preview upload | Upload the PNG from `docs/assets/` in repository settings | Not uploaded. |
| Video thumbnail (optional) | From the banner in `docs/assets/` or a frame of the video | Not produced. |

## Rules for all assets

- Show only real output from the current build. Never edit numbers, verdicts or labels.
- Never show API keys, `.env` contents, personal accounts or notifications.
- Scripted decisions stay labelled as scripted; simulated tools stay labelled as simulated.
- Do not use third-party logos or trademarks beyond what is needed to name a technology.
