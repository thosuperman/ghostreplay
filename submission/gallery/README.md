# Devpost gallery

Ten screenshots of the live site (https://ghostreplay.hayaix.tech), captured by
`node apps/dashboard/scripts/capture-gallery.mjs`: a fresh browser session clicks through both
guided demos and the Connect page. Each image is 2160 × 1440 (3:2) and unedited: every number,
verdict and label is what the site really returned.

Upload them in this order. The captions can be pasted into Devpost.

| # | File | Caption |
|---|---|---|
| 1 | `01-home.png` | GhostReplay Lab: a flight recorder and crash-test lab for AI agents. |
| 2 | `02-refund-failure.png` | The support agent asked for one $129 refund. The app's retry after a timeout refunded $258. Every step is labelled with who did it. |
| 3 | `03-refund-timeline.png` | The recorded timeline. The retried `payments.create_refund` call is open in the inspector. |
| 4 | `04-refund-replay.png` | Strict offline replay: 4 model calls and 6 tool calls served from the recording, 0 executed, identical result. |
| 5 | `05-refund-fix-proven.png` | The fixed app runs for real against the same fault: one refund, safety invariant PASS. |
| 6 | `06-devops-model-decision.png` | The DevOps agent's real recorded decision: the model refused to terminate instances. |
| 7 | `07-devops-injected-failure.png` | A labelled, injected unsafe decision shows the workflow has no safeguard: 3 healthy servers terminated. |
| 8 | `08-devops-fix-blocks-terminate.png` | Runbook v2 plus a safety gate in code: the destructive call is blocked and all 3 servers stay up. |
| 9 | `09-connect-sdk.png` | Bring your own agent: the public Python SDK. |
| 10 | `10-sdk-quickstart.png` | The quickstart: instrument, record, replay and prove a fix in about 90 lines. It is tested in CI. |

The video thumbnail (1280 × 720) is `../thumbnail/thumbnail.png`. Its panel is a real crop of
`02-refund-failure.png`. Render it again with
`node apps/dashboard/scripts/render-thumbnail.mjs`.
