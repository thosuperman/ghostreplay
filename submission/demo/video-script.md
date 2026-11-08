# Demo video script

A finished cut, recorded from the live site with a synthetic male voiceover, is produced by
`submission/demo/video/` (see its README). Its narration is in `submission/demo/video/narration.json`.

The script is maintained in one place: [`docs/demo-script.md`](../../docs/demo-script.md).
It runs under 3:00 and follows this order:

| Time | Segment | Screen |
|---|---|---|
| 0:00–0:20 | The problem | Home: "Your AI Agent Made a Mistake. Now What?" |
| 0:20–0:50 | The failure: $129 becomes $258 | `/demo/refund`, steps 1–2 |
| 0:50–1:15 | Investigation: the exact tool call | Step 3, technical details |
| 1:15–1:35 | Safe replay: 0 payment calls | Step 4 |
| 1:35–2:00 | Verify the fix: $129 once, regression PASS | Steps 5–6 |
| 2:00–2:20 | Second application | `/demo/devops` |
| 2:20–2:45 | Developer integration | Terminal: `examples/invoice-agent` (`invoice-agent-demo`) |
| 2:45–3:00 | Conclusion | Home: Record → Replay → Investigate → Fix → Verify |

Record against https://ghostreplay.hayaix.tech (see `recording-guide.md`, Option C). Every
number on screen comes from a real run; narrate what is shown.
