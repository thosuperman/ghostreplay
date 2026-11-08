// Renders submission/thumbnail/thumbnail.html to thumbnail.png (1280x720, the YouTube size)
// and a 3:2 cover (1500x1000) for Devpost.
//
//   node apps/dashboard/scripts/render-thumbnail.mjs
import { chromium } from "@playwright/test";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const dir = resolve(dirname(fileURLToPath(import.meta.url)), "../../../submission/thumbnail");
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
await page.goto(pathToFileURL(resolve(dir, "thumbnail.html")).href, { waitUntil: "networkidle" });
await page.evaluate(() => document.fonts.ready);
await page.screenshot({ path: resolve(dir, "thumbnail.png") });
console.log("rendered", resolve(dir, "thumbnail.png"));
await browser.close();
