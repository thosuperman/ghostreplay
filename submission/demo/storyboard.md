# Storyboard

One row per shot. Follows [`docs/demo-script.md`](../../docs/demo-script.md).

| # | Time | Screen | What is visible | Emphasis |
|---|---|---|---|---|
| 1 | 0:00–0:20 | Home | Hero "Your AI Agent Made a Mistake. Now What?", the two scenario cards | The problem |
| 2 | 0:20–0:30 | `/demo/refund` step 1 | Customer chat, tools "Find Order", "Check Refund Eligibility", "Issue Refund" | Agents take actions |
| 3 | 0:30–0:50 | Step 2 | Facts: $129.00 expected, $258.00 refunded, 2 committed, FAIL; three highlighted story lines | The failure |
| 4 | 0:50–1:15 | Step 3 | Plain-English timeline; inspector on the first `payments.create_refund` (state before/after) | Root cause |
| 5 | 1:15–1:35 | Step 4 | 9 recorded responses reused, 0 tool executions, Identical | Safe replay |
| 6 | 1:35–1:50 | Step 5 | Comparison table Buggy vs Fixed | The fix |
| 7 | 1:50–2:00 | Step 6 | "Before: FAILED", "After: PASSED" | Proof |
| 8 | 2:00–2:20 | `/demo/devops` | "terminated 3 healthy servers"; fixed agent probes, guard, approval request | Second app |
| 9 | 2:20–2:45 | Terminal | `invoice-agent-demo` steps 2, 4, 7 | Your own agent (SDK) |
| 10 | 2:45–3:00 | Home | Record → Replay → Investigate → Fix → Verify | Conclusion |
