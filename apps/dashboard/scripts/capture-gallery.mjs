// Captures the Devpost gallery screenshots from the live site: real runs, real results,
// nothing edited. 3:2 viewport (1440x960) at 1.5x, so each image is 2160x1440.
//
//   node apps/dashboard/scripts/capture-gallery.mjs [base-url]
//
// Writes submission/gallery/NN-name.png.
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const out = resolve(root, "submission/gallery");
const base = process.argv[2] ?? "https://ghostreplay.hayaix.tech";
mkdirSync(out, { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1440, height: 960 },
  deviceScaleFactor: 1.5,
  colorScheme: "dark",
});
const page = await context.newPage();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function goto(path) {
  await page.goto(base + path, { waitUntil: "networkidle" });
  await sleep(600);
}
/**
 * Scroll the element into place under the sticky header, then capture the viewport.
 * align "top": element starts just under the header. "bottom": a short card ends near the
 * bottom of the screen, so the steps before it fill the space above (a tall one starts at top).
 */
async function shot(name, locator, { align = "bottom", offset = 72 } = {}) {
  if (locator) {
    // New step cards fade/slide in, so let the layout settle and scroll twice.
    await sleep(900);
    // The newest card is at the bottom of the page; give the page room to scroll it to the top.
    await page.evaluate(() => { document.body.style.paddingBottom = "1200px"; });
    for (let i = 0; i < 2; i++) {
      await locator.first().evaluate((el, { align, offset }) => {
        const r = el.getBoundingClientRect();
        const fits = r.height < window.innerHeight - offset - 24;
        const top = align === "bottom" && fits ? window.innerHeight - 24 - r.height : offset;
        window.scrollTo({ top: r.top + window.scrollY - top });
      }, { align, offset });
      await sleep(400);
    }
  } else {
    await page.evaluate(() => window.scrollTo({ top: 0 }));
  }
  await sleep(700);
  await page.mouse.move(1430, 950);
  await page.screenshot({ path: resolve(out, `${name}.png`) });
  console.log("captured", name);
}
const id = (t) => page.getByTestId(t);
/** The guided-demo step card that contains the given test id. */
const step = (t) => page.locator('section[data-testid^="step-"]').filter({ has: id(t) });

// -- home ---------------------------------------------------------------------------------------
await goto("/");
await shot("01-home", null);

// -- refund demo --------------------------------------------------------------------------------
await goto("/demo/refund");
await id("run-agent").click();
await id("failure-headline").waitFor();
await shot("02-refund-failure", step("failure-headline"));
await id("tech-details").click();
await sleep(500);
// Select the second (retried) refund call in the timeline to open it in the inspector.
await page.getByTestId("step-3").getByText("payments.create_refund", { exact: true }).nth(1).click();
await shot("03-refund-timeline", id("tech-details"), { align: "top", offset: 96 });
await id("replay").click();
await id("replay-facts").waitFor();
await shot("04-refund-replay", step("replay-facts"));
await id("test-fix").click();
await id("compare-table").waitFor();
await id("verify").click();
await id("verify-after").waitFor();
await shot("05-refund-fix-proven", step("compare-table"));

// -- devops demo --------------------------------------------------------------------------------
await goto("/demo/devops");
await id("run-agent").click();
await id("natural-summary").waitFor();
await shot("06-devops-model-decision", step("natural-summary"));
await id("inject").click();
await id("failure-headline").waitFor();
await shot("07-devops-injected-failure", step("failure-headline"));
await id("replay").click();
await id("replay-facts").waitFor();
await id("test-fix").click();
await id("compare-table").waitFor();
await shot("08-devops-fix-blocks-terminate", step("compare-table"));

// -- bring your own agent -----------------------------------------------------------------------
await goto("/connect");
await shot("09-connect-sdk", null);
await shot("10-sdk-quickstart", page.locator("#instrument"));

await browser.close();
