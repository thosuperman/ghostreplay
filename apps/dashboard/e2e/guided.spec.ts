import { expect, test } from "./fixtures";

test("guided refund demo: failure, offline replay, fix and regression from real runs", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("cta-watch-fail").click();
  await expect(page).toHaveURL(/#\/demo\/refund$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("The Double Refund Incident");

  await page.getByTestId("run-agent").click();
  await expect(page.getByTestId("failure-headline")).toHaveText("The customer was refunded $258.00 instead of $129.00.");
  const facts = page.getByTestId("step-2").getByTestId("facts");
  await expect(facts).toContainText("$129.00");
  await expect(facts).toContainText("$258.00");
  await expect(facts).toContainText("FAIL");
  await expect(page.getByTestId("failure-story")).toContainText("timed out");

  // The plain-English story matches the recorded events: every line links to a real seq.
  await page.getByTestId("tech-details").click();
  await expect(page.getByText("payments.create_refund").first()).toBeVisible();

  await page.getByTestId("replay").click();
  const replay = page.getByTestId("replay-facts");
  await expect(replay).toContainText("External tool executions");
  await expect(replay.getByText("Identical")).toBeVisible();
  await expect(replay).toContainText("0 were executed");

  await page.getByTestId("test-fix").click();
  const table = page.getByTestId("compare-table");
  await expect(table.getByRole("row", { name: /Actually refunded/ })).toContainText("$258.00");
  await expect(table.getByRole("row", { name: /Actually refunded/ })).toContainText("$129.00");
  await expect(table.getByRole("row", { name: /Duplicate refund/ })).toContainText("Yes");
  await expect(page.getByTestId("fixed-story")).toContainText("Recovered the committed refund");

  await page.getByTestId("verify").click();
  await expect(page.getByTestId("verify-before")).toHaveAttribute("data-passed", "false");
  await expect(page.getByTestId("verify-after")).toHaveAttribute("data-passed", "true");
  await expect(page.getByTestId("verify-after")).toContainText("as expected");

  // Guided → developer mode keeps the execution context.
  await page.getByRole("link", { name: "Explore Full Execution" }).click();
  await expect(page).toHaveURL(/#\/support\/executions\/rec_/);
  await expect(page.getByText("payments.create_refund").first()).toBeVisible();
});

test("guided DevOps demo: the fixed agent verifies health and asks for approval", async ({ page }) => {
  await page.goto("/demo/devops"); // pretty path served by the proxy
  await expect(page).toHaveURL(/#\/demo\/devops$/);
  await page.getByTestId("run-agent").click();
  await expect(page.getByTestId("failure-headline")).toContainText("terminated 3 healthy servers");
  await page.getByTestId("replay").click();
  await expect(page.getByTestId("replay-facts").getByText("Identical")).toBeVisible();
  await page.getByTestId("test-fix").click();
  const table = page.getByTestId("compare-table");
  await expect(table.getByRole("row", { name: /Human approval requested/ })).toContainText("Yes");
  await expect(table.getByRole("row", { name: /^Servers terminated/ })).toContainText("0");
  await expect(page.getByTestId("fixed-story")).toContainText("waiting for human approval");
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
