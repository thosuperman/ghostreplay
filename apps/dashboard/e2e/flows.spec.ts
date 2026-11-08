import { expect, test } from "./fixtures";

const LAB = "support";

// Runs are created through page.request so they belong to the page's own session: on a public
// deployment each browser session only sees the executions it created.

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

  const id = new URL(page.url()).hash.split("/").pop()?.split("?")[0] ?? "";
  expect(id).toMatch(/^rec_/);
  await page.goto(`/#/${LAB}/executions`);
  const row = page.locator("tbody tr").filter({ hasText: id });
  await expect(row.getByTestId("model-provenance")).toHaveText("scripted");
});

test("inspector shows model usage and offers copy as JSON", async ({ page }) => {
  const { incident } = await prepareDemo(page.request);
  const res = await page.request.get(`/lab/${LAB}/api/executions/${incident}`);
  expect(res.ok()).toBeTruthy();
  const execution = (await res.json()) as { events: { kind: string; name: string }[] };
  const modelCall = execution.events.find((e) => e.kind === "model_call");
  expect(modelCall).toBeDefined();
  await page.goto(`/#/${LAB}/executions/${incident}`);
  await page.locator("ol > li").filter({ hasText: modelCall!.name }).first().click();
  const usage = page.getByTestId("model-usage");
  await expect(usage).toBeVisible();
  await expect(usage).toContainText(/scripted model/i);
  await expect(page.getByRole("button", { name: "Copy as JSON" })).toBeVisible();
});

test("replay studio streams an offline replay that matches the recording", async ({ page }) => {
  const { incident } = await prepareDemo(page.request);
  await page.goto(`/#/${LAB}/replay/${incident}`);
  await page.getByRole("button", { name: /replay/i }).first().click();
  await expect(page.getByRole("link", { name: /Diff recording ↔ replay/ })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/identical/i).first()).toBeVisible();
});

test("failure lab injects the headline fault and the fixed agent passes", async ({ page }) => {
  const { baseline } = await prepareDemo(page.request);
  await page.goto(`/#/${LAB}/failure-lab/${baseline}`);
  await page.getByText(/Refund times out after commit/i).first().click();
  await page.getByRole("button", { name: /Run|Inject/ }).first().click();
  await expect(page.getByRole("link", { name: /Make it a regression test/ })).toBeVisible({ timeout: 30_000 });
});

test("diff view shows the first divergence between vulnerable and fixed runs", async ({ page }) => {
  const { cfVuln, cfFixed } = await prepareDemo(page.request);
  await page.goto(`/#/${LAB}/diff?a=${cfVuln}&b=${cfFixed}`);
  await expect(page.getByText(/first divergence/i).first()).toBeVisible();
  await expect(page.getByText("idempotency_key").first()).toBeVisible();
});

test("regression view runs the case for every variant with opposite verdicts", async ({ page }) => {
  const { cfVuln } = await prepareDemo(page.request);
  await page.goto(`/#/${LAB}/regression/${cfVuln}`);
  await page.getByRole("button", { name: /Run/ }).first().click();
  await expect(page.getByText("FAIL").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("PASS").first()).toBeVisible();
});

test("every route renders without browser errors", async ({ page }) => {
  const { incident, cfVuln, cfFixed } = await prepareDemo(page.request);
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
  for (const lab of ["support", "devops"]) {
    const health = await request.get(`/lab/${lab}/api/health`);
    expect(health.ok()).toBeTruthy();
    expect((await health.json()).status).toBe("ok");
  }
});

test("a different browser session cannot see another session's runs", async ({ page, browser }) => {
  const info = await (await page.request.get(`/lab/${LAB}/api/info`)).json();
  test.skip(!info.isolated_sessions, "session isolation is only enabled on public deployments");
  const { incident } = await prepareDemo(page.request);
  const other = await browser.newContext();
  try {
    const res = await other.request.get(`/lab/${LAB}/api/executions/${incident}`);
    expect(res.status()).toBe(404);
    // Every session also sees the shared, read-only capture library, but nothing of another session.
    const library = (await (await other.request.get(`/lab/${LAB}/api/library`)).json()) as { captures: { id: string }[] };
    const shared = new Set(library.captures.map((c) => c.id));
    const visible = (await (await other.request.get(`/lab/${LAB}/api/executions`)).json()) as { id: string }[];
    expect(visible.filter((r) => !shared.has(r.id))).toEqual([]);
  } finally {
    await other.close();
  }
  expect((await page.request.get(`/lab/${LAB}/api/executions/${incident}`)).ok()).toBeTruthy();
});
