import { expect, test } from "./fixtures";

test("guided refund demo: real re-execution, offline replay, fix and regression", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("cta-watch-fail").click();
  await expect(page).toHaveURL(/#\/demo\/refund$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("The Double Refund Incident");
  await expect(page.getByTestId("what-is-real")).toContainText("SQLite");

  await page.getByTestId("run-agent").click();
  await expect(page.getByTestId("failure-headline")).toHaveText("The customer was refunded $258.00 instead of $129.00.");
  const failure = page.getByTestId("step-2");
  await expect(failure.getByTestId("exec-type")).toContainText("Re-execution · recorded decisions");
  await expect(failure.getByTestId("exec-type")).toContainText("Controlled fault");
  await expect(failure.getByTestId("facts")).toContainText("$258.00");
  // Who did what: the model asked for the refund, the application retried.
  await expect(page.locator('[data-testid="full-story"] [data-actor="model"]').first()).toContainText("decided to call");
  await expect(page.getByTestId("failure-story")).toContainText("retry policy (not the model)");

  await page.getByTestId("tech-details").click();
  await expect(page.getByText("payments.create_refund").first()).toBeVisible();

  await page.getByTestId("replay").click();
  const replay = page.getByTestId("replay-facts");
  await expect(replay).toContainText("Model calls avoided");
  await expect(replay.locator("dd").nth(3)).toHaveText("0"); // executed during replay
  await expect(replay).toContainText("identical");

  await page.getByTestId("test-fix").click();
  const table = page.getByTestId("compare-table");
  await expect(table.getByRole("row", { name: /Refunded \(SQL ledger\)/ })).toContainText("$258.00");
  await expect(table.getByRole("row", { name: /Refunded \(SQL ledger\)/ })).toContainText("$129.00");
  await expect(page.getByTestId("step-5").getByTestId("exec-type")).toContainText("Corrected re-execution");
  await expect(page.getByTestId("fixed-story")).toContainText("did not refund again");

  await page.getByTestId("verify").click();
  await expect(page.getByTestId("verify-before")).toHaveAttribute("data-passed", "false");
  await expect(page.getByTestId("verify-after")).toHaveAttribute("data-passed", "true");
  await expect(page.getByTestId("verify-after")).toContainText("as expected");

  await page.getByRole("link", { name: "Explore Full Execution" }).click();
  await expect(page).toHaveURL(/#\/support\/executions\/brn_/);
  await expect(page.getByText("payments.create_refund").first()).toBeVisible();
});

test("guided DevOps demo: Claude declined, the injected decision fails v1 and is blocked by v2", async ({ page }) => {
  await page.goto("/demo/devops");
  await expect(page).toHaveURL(/#\/demo\/devops$/);
  await page.getByTestId("run-agent").click();
  await expect(page.getByTestId("natural-summary")).toContainText("declined");
  await page.getByTestId("inject").click();
  await expect(page.getByTestId("failure-headline")).toContainText("terminated 3 healthy servers");
  await expect(page.getByTestId("failure-story")).toContainText("Injected model decision");
  await page.getByTestId("replay").click();
  await expect(page.getByTestId("replay-facts")).toContainText("identical");
  await page.getByTestId("test-fix").click();
  const table = page.getByTestId("compare-table");
  await expect(table.getByRole("row", { name: /^Servers terminated/ })).toContainText("0");
  await expect(table.getByRole("row", { name: /Destructive call blocked/ })).toContainText("Yes");
  await page.getByTestId("verify").click();
  await expect(page.getByTestId("verify-after")).toHaveAttribute("data-passed", "true");
  await expect(page.getByTestId("verify-before")).toHaveAttribute("data-passed", "false");
});

test("connect page shows the tested SDK quickstart and the CI example", async ({ page }) => {
  await page.goto("/#/connect");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Connect your own AI agent");
  await expect(page.getByText('ghost = GhostReplay("shop-agent", storage="./ghostreplay-data")')).toBeVisible();
  await expect(page.getByText("ghostreplay test tests/regression --import invoice_agent.agent").first()).toBeVisible();
  await expect(page.getByText("Not recorded:")).toBeVisible();
});

test.describe("trace import", () => {
  test.use({ expectedHttpErrors: [422] }); // the malformed upload is rejected on purpose

  test("a downloaded trace can be imported and inspected; malformed ones are rejected", async ({ page }) => {
  await page.goto("/#/import");
  const rec = await page.request.post("/lab/support/api/runs/record", { data: { scenario: "duplicate-refund", variant: "vulnerable" } });
  const id = (await rec.json()).id as string;
  const trace = await page.request.get(`/lab/support/api/executions/${id}/trace`);
  expect(trace.ok()).toBeTruthy();
  await page.getByTestId("trace-file").setInputFiles({ name: `${id}.trace.json`, mimeType: "application/json", buffer: await trace.body() });
  await expect(page.getByTestId("import-result")).toContainText(id);
  await expect(page.getByTestId("import-result")).toContainText("can be replayed here");

  await page.getByTestId("trace-file").setInputFiles({ name: "bad.trace.json", mimeType: "application/json", buffer: Buffer.from('{"id": 1}') });
  await expect(page.getByRole("alert")).toContainText("uploaded trace");
});
});
