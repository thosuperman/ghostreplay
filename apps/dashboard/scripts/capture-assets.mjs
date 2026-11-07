// Renders the SVG brand assets to PNG and captures README screenshots from a running
// GhostReplay gateway. Screenshots show the real UI on real executions.
//
//   uv run ghostreplay serve --port 8188 --db .ghostreplay/screens   (from the repo root)
//   node apps/dashboard/scripts/capture-assets.mjs http://127.0.0.1:8188
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const assets = resolve(root, "docs/assets");
const shots = resolve(assets, "screenshots");
mkdirSync(shots, { recursive: true });
const base = process.argv[2] ?? "http://127.0.0.1:8188";

const browser = await chromium.launch();

// 1. SVG -> PNG
for (const [name, w, h] of [
  ["social-preview", 1280, 640],
  ["banner", 1280, 460],
  ["app-icon", 512, 512],
  ["architecture", 1100, 700],
  ["record-replay-sequence", 1100, 620],
]) {
  const page = await browser.newPage({ viewport: { width: w, height: h } });
  await page.goto(pathToFileURL(resolve(assets, `${name}.svg`)).href);
  await page.screenshot({ path: resolve(assets, `${name}.png`) });
  await page.close();
}

// 2. Real UI screenshots
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, colorScheme: "dark" });
const post = async (path, data) => {
  const res = await page.request.post(`${base}${path}`, { data });
  if (!res.ok()) throw new Error(`${path}: ${res.status()} ${await res.text()}`);
  return res.json();
};
const story = await post("/lab/support/api/demo/prepare", { scenario: "duplicate-refund" });
const ids = (step) => story.steps.find((s) => s.id === step).execution_ids;
const [incident] = ids("incident");
const [baseline, cfVuln] = ids("counterfactual");
const [, cfFixed] = ids("fix");

async function shot(name, path, ready) {
  await page.goto(`${base}/${path}`);
  if (ready) await ready();
  await page.waitForTimeout(500);
  await page.screenshot({ path: resolve(shots, `${name}.png`) });
  console.log("captured", name);
}

await shot("home", "");
await shot("story-duplicate-refund", "#/support/story", () =>
  page.getByText("✓ fix proven").waitFor({ timeout: 30000 }));
await shot("story-unsafe-aws-operation", "#/devops/story", () =>
  page.getByText("✓ fix proven").waitFor({ timeout: 30000 }));
await shot("timeline", `#/support/executions/${incident}`, () =>
  page.getByText("payments.create_refund").first().waitFor());
await shot("diff", `#/support/diff?a=${cfVuln}&b=${cfFixed}`, () =>
  page.getByText("idempotency_key").first().waitFor());
await shot("failure-lab", `#/support/failure-lab/${baseline}`, async () => {
  await page.getByText(/Refund times out after commit/i).first().click();
  await page.getByRole("button", { name: /Run|Inject/ }).first().click();
  await page.getByRole("link", { name: /Make it a regression test/ }).waitFor({ timeout: 30000 });
});
await shot("regression", `#/support/regression/${cfVuln}`, async () => {
  await page.getByRole("button", { name: /Run/ }).first().click();
  await page.getByText("PASS").first().waitFor({ timeout: 30000 });
});
await shot("replay-studio", `#/support/replay/${incident}`, async () => {
  await page.getByRole("button", { name: /replay/i }).first().click();
  await page.getByRole("link", { name: /Diff recording ↔ replay/ }).waitFor({ timeout: 30000 });
});

await browser.close();
