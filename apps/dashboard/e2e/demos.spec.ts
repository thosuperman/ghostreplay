import { expect, test } from "./fixtures";

test("home page explains the product and offers both demos", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Your AI Agent Made a Mistake. Now What?");
  await expect(page.getByTestId("cta-watch-fail")).toHaveAttribute("href", "#/demo/refund");
  await expect(page.getByTestId("cta-connect")).toHaveAttribute("href", "#/connect");
  await expect(page.getByText("The $129 Refund That Became $258")).toBeVisible();
  await expect(page.getByText("The AI Agent That Tried to Delete Healthy Servers")).toBeVisible();
  await expect(page.getByText("Catch the bug. Replay the failure. Prove the fix.")).toBeVisible();
  // The SDK snippet on the home page is the tested example file.
  await expect(page.locator("pre").first()).toContainText('GhostReplay("my-agent"');
});

for (const demo of [{ lab: "support" }, { lab: "devops" }]) {
  test(`${demo.lab}: the developer demo story runs on real executions`, async ({ page }) => {
    await page.goto(`/#/${demo.lab}/story`);
    await expect(page.getByText("bug reproduced")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("✓ bug reproduced")).toBeVisible();
    await expect(page.getByText("✓ fix proven")).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
    const steps = page.getByTestId("story-step");
    await expect(steps).toHaveCount(6);
    const verdicts = await steps.evaluateAll((els) => els.map((e) => e.getAttribute("data-verdict")));
    expect(verdicts).toEqual(["fail", "pass", "info", "fail", "pass", "pass"]);

    // The story is backed by executions the lab actually stored.
    const stored = await page.request.get(`/lab/${demo.lab}/api/executions`);
    expect(stored.ok()).toBeTruthy();
    const rows = (await stored.json()) as { mode: string; invariants_failed: number }[];
    expect(rows.some((r) => r.mode === "record" && r.invariants_failed > 0)).toBeTruthy();
    expect(rows.some((r) => r.mode === "replay")).toBeTruthy();
    expect(rows.some((r) => r.mode === "branch" && r.invariants_failed === 0)).toBeTruthy();
  });
}
