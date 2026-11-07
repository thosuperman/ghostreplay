import { expect, test } from "./fixtures";

test("home page offers both one-click demos", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Break AI agents safely");
  await expect(page.getByRole("link", { name: /Try the Duplicate Refund Demo/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /Try the Unsafe AWS Operation Demo/ })).toBeVisible();
});

for (const demo of [
  { cta: /Try the Duplicate Refund Demo/, lab: "support" },
  { cta: /Try the Unsafe AWS Operation Demo/, lab: "devops" },
]) {
  test(`${demo.lab}: one click runs the full story on real executions`, async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: demo.cta }).click();
    await expect(page).toHaveURL(new RegExp(`#/${demo.lab}/story`));
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
