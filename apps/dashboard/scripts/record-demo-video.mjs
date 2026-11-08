// Records the demo video's picture: drives the live site through the narration, segment by
// segment, in a fresh browser session (real requests, real results; nothing is staged).
//
//   node apps/dashboard/scripts/record-demo-video.mjs [base-url]
//
// Reads submission/demo/video/out/durations.json (from make_video.py) and writes
// out/raw/*.webm plus out/marks.json (when each segment actually started in the recording),
// which make_video.py uses to place each voice segment exactly in sync.
import { chromium } from "@playwright/test";
import { mkdirSync, readFileSync, readdirSync, renameSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const out = resolve(root, "submission/demo/video/out");
const base = process.argv[2] ?? "https://ghostreplay.hayaix.tech";
const durations = JSON.parse(readFileSync(resolve(out, "durations.json"), "utf8"));
const GAP = 0.9; // breathing room after each spoken segment (s)
const rawDir = resolve(out, "raw", String(Date.now()));
mkdirSync(rawDir, { recursive: true });

// Playwright only ever scales the page *down* into the video frame, never up: a video size larger
// than the viewport leaves the page in the top-left corner with a grey border. So the video is
// recorded at exactly the viewport size and make_video.py scales it to 1920x1080.
const VIEWPORT = { width: 1440, height: 810 };
const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: VIEWPORT,
  deviceScaleFactor: 1.5,
  colorScheme: "dark",
  recordVideo: { dir: rawDir, size: VIEWPORT },
});
// A visible cursor (headless video has none) with a click highlight.
await context.addInitScript(() => {
  const install = () => {
    if (document.getElementById("__cursor")) return;
    const c = document.createElement("div");
    c.id = "__cursor";
    Object.assign(c.style, {
      position: "fixed", left: "0", top: "0", width: "22px", height: "22px", borderRadius: "50%",
      background: "rgba(255,255,255,0.92)", border: "2px solid #8b5cf6", boxShadow: "0 0 14px rgba(139,92,246,.85)",
      zIndex: "2147483647", pointerEvents: "none", transform: "translate(720px, 600px)",
    });
    document.documentElement.appendChild(c);
    const pos = window.__cursorPos;
    if (pos) c.style.transform = `translate(${pos.x - 11}px, ${pos.y - 11}px)`;
    document.addEventListener("mousemove", (e) => {
      window.__cursorPos = { x: e.clientX, y: e.clientY };
      c.style.transform = `translate(${e.clientX - 11}px, ${e.clientY - 11}px)`;
    }, true);
    document.addEventListener("mousedown", () => { c.style.background = "rgba(139,92,246,0.95)"; c.style.scale = "1.35"; }, true);
    document.addEventListener("mouseup", () => { c.style.background = "rgba(255,255,255,0.92)"; c.style.scale = "1"; }, true);
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", install);
  else install();
});

const page = await context.newPage();
const t0 = Date.now();
const now = () => (Date.now() - t0) / 1000;
const marks = {};
let segStart = 0;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const at = async (s) => { const w = segStart + s - now(); if (w > 0) await sleep(w * 1000); };
let mouse = { x: 720, y: 600 };

async function moveTo(locator) {
  await locator.scrollIntoViewIfNeeded();
  const b = await locator.boundingBox();
  const x = b.x + b.width / 2, y = b.y + b.height / 2;
  await page.mouse.move(x, y, { steps: 28 });
  mouse = { x, y };
  await sleep(250);
}
async function click(locator) {
  await moveTo(locator);
  await page.mouse.down(); await sleep(90); await page.mouse.up();
}
async function show(locator, block = "center") {
  await locator.evaluate((el, block) => el.scrollIntoView({ behavior: "smooth", block }), block);
  await sleep(1100);
}
async function goto(path) {
  await page.goto(base + path, { waitUntil: "networkidle" });
  await page.mouse.move(mouse.x, mouse.y);
}
async function segment(id, fn) {
  segStart = now();
  marks[id] = segStart;
  await fn();
  await at(durations[id] + GAP);
  console.log(`${id.padEnd(12)} start ${segStart.toFixed(2)}s  took ${(now() - segStart).toFixed(2)}s (voice ${durations[id]}s)`);
}

// -- opening shot ------------------------------------------------------------------------------
await goto("/");
await sleep(1800);

await segment("problem", async () => {
  await at(5.5);
  await show(page.getByText("The $129 Refund That Became $258"), "center");
  await at(11);
  await show(page.getByRole("heading", { name: "How it works" }), "start");
});

await segment("failure", async () => {
  await goto("/demo/refund");
  await at(4);
  await show(page.getByText("Find Order").first(), "center");
  await at(8.5);
  await show(page.getByTestId("what-is-real"), "center");
  await at(15.5);
  await click(page.getByTestId("run-agent"));
  await page.getByTestId("failure-headline").waitFor();
  await at(19.5);
  await show(page.getByTestId("failure-headline"), "start");
});

await segment("investigate", async () => {
  await show(page.getByTestId("failure-story"), "center");
  await moveTo(page.getByTestId("failure-story").locator("li").nth(1));
  await at(8);
  await moveTo(page.getByTestId("failure-story").locator("li").nth(2));
  await at(12.5);
  await click(page.getByTestId("tech-details"));
  await sleep(700);
  // The timeline event in step 3 (not the tool card in step 1).
  const ev = page.getByTestId("step-3").getByText("payments.create_refund").first();
  await show(ev, "center");
  await click(ev);
  await at(14.5);
  await page.evaluate(() => window.scrollBy({ top: 160, behavior: "smooth" }));
});

await segment("replay", async () => {
  await click(page.getByTestId("replay"));
  await page.getByTestId("replay-facts").waitFor();
  await show(page.getByTestId("replay-facts"), "center");
  await at(9);
  await moveTo(page.getByTestId("replay-facts").locator("dd").nth(3));
});

await segment("fix", async () => {
  await click(page.getByTestId("test-fix"));
  await page.getByTestId("compare-table").waitFor();
  await show(page.getByTestId("compare-table"), "center");
  await moveTo(page.getByTestId("compare-table").getByRole("row", { name: /Refunded/ }));
  await at(12.5);
  await click(page.getByTestId("verify"));
  await page.getByTestId("verify-after").waitFor();
  await show(page.getByTestId("verify-before"), "center");
  await at(18.5);
  await moveTo(page.getByTestId("verify-after"));
});

await segment("devops", async () => {
  await goto("/demo/devops");
  await at(1.5);
  await click(page.getByTestId("run-agent"));
  await page.getByTestId("natural-summary").waitFor();
  await show(page.getByTestId("natural-summary"), "center");
  await at(10.5);
  await click(page.getByTestId("inject"));
  await page.getByTestId("failure-headline").waitFor();
  await show(page.getByTestId("failure-headline"), "start");
  await at(15.5);
  await click(page.getByTestId("replay"));
  await page.getByTestId("replay-facts").waitFor();
  await click(page.getByTestId("test-fix"));
  await page.getByTestId("compare-table").waitFor();
  await show(page.getByTestId("compare-table"), "center");
  await moveTo(page.getByTestId("compare-table").getByRole("row", { name: /Destructive call blocked/ }));
});

await segment("sdk", async () => {
  await goto("/connect");
  await at(3);
  await show(page.locator("#instrument"), "start");
  await at(7);
  await page.evaluate(() => window.scrollBy({ top: 520, behavior: "smooth" }));
  await at(11.5);
  await page.evaluate(() => window.scrollBy({ top: 520, behavior: "smooth" }));
});

await segment("close", async () => {
  await goto("/");
  await at(5.5);
  await show(page.getByRole("heading", { name: "How it works" }), "start");
  await at(9.5);
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
});
await sleep(1500);
marks.__end = now();

await context.close(); // finalises the video file
await browser.close();
const vids = readdirSync(rawDir).filter((f) => f.endsWith(".webm"));
renameSync(resolve(rawDir, vids[0]), resolve(out, "screen.webm"));
writeFileSync(resolve(out, "marks.json"), JSON.stringify(marks, null, 1));
console.log("recorded", marks.__end.toFixed(1), "s ->", resolve(out, "screen.webm"));
