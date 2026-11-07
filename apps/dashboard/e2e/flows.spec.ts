import { expect, test } from "./fixtures";

const LAB = "support";

async function prepareDemo(request: import("@playwright/test").APIRequestContext) {
  const res = await request.post(`/lab/${LAB}/api/demo/prepare`, { data: { scenario: "duplicate-refund" } });
  expect(res.ok()).toBeTruthy();
  const story = (await res.json()) as { ok: boolean; steps: { id: string; execution_ids: string[] }[] };
  expect(story.ok).toBe(true);
  const ids = (step: string) => story.steps.find((s) => s.id === step)!.execution_ids;
  return { incident: ids("incident")[0]!, baseline: ids("counterfactual")[0]!, cfVuln: ids("counterfactual")[1]!, cfFixed: ids("fix")[1]! };
}

test("explorer records a run and opens its timeline", async ({ page }) => {
  await page.goto(`/#/${LAB}/executions`);
  await expect(page.getByRole("heading", { name: "Execution Explorer" })).toBeVisible();
  await page.getByRole("button", { name: /Record run/ }).click();
  await expect(page).toHaveURL(new RegExp(`#/${LAB}/executions/rec_`));
  await expect(page.getByText("payments.create_refund").first()).toBeVisible();
  await expect(page.getByText(/scripted/i).first()).toBeVisible();
});

test("replay studio streams an offline replay that matches the recording", async ({ page, request }) => {
  const { incident } = await prepareDemo(request);
  await page.goto(`/#/${LAB}/replay/${incident}`);
  await page.getByRole("button", { name: /replay/i }).first().click();
  await expect(page.getByRole("link", { name: /Diff recording ↔ replay/ })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/identical/i).first()).toBeVisible();
});

test("failure lab injects the headline fault and the fixed agent passes", async ({ page, request }) => {
  const { baseline } = await prepareDemo(request);
  await page.goto(`/#/${LAB}/failure-lab/${baseline}`);
  await page.getByText(/Refund times out after commit/i).first().click();
  await page.getByRole("button", { name: /Run|Inject/ }).first().click();
  await expect(page.getByRole("link", { name: /Make it a regression test/ })).toBeVisible({ timeout: 30_000 });
});

test("diff view shows the first divergence between vulnerable and fixed runs", async ({ page, request }) => {
  const { cfVuln, cfFixed } = await prepareDemo(request);
  await page.goto(`/#/${LAB}/diff?a=${cfVuln}&b=${cfFixed}`);
  await expect(page.getByText(/first divergence/i).first()).toBeVisible();
  await expect(page.getByText("idempotency_key").first()).toBeVisible();
});

test("regression view runs the case for every variant with opposite verdicts", async ({ page, request }) => {
  const { cfVuln } = await prepareDemo(request);
  await page.goto(`/#/${LAB}/regression/${cfVuln}`);
  await page.getByRole("button", { name: /Run/ }).first().click();
  await expect(page.getByText("FAIL").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("PASS").first()).toBeVisible();
});

test("every route renders without browser errors", async ({ page, request }) => {
  const { incident, cfVuln, cfFixed } = await prepareDemo(request);
  for (const path of [
    "/",
    `/#/${LAB}/executions`,
    `/#/${LAB}/executions/${incident}`,
    `/#/${LAB}/replay/${incident}`,
    `/#/${LAB}/failure-lab/${incident}`,
    `/#/${LAB}/diff?a=${cfVuln}&b=${cfFixed}`,
    `/#/${LAB}/regression/${cfVuln}`,
    "/#/devops/executions",
  ]) {
    await page.goto(path);
    await expect(page.locator("main, #root").first()).not.toBeEmpty();
  }
});

test("health endpoints report both labs", async ({ request }) => {
  const health = await request.get("/api/health");
  expect(health.ok()).toBeTruthy();
  expect((await health.json()).labs).toEqual({ devops: "ok", support: "ok" });
});
