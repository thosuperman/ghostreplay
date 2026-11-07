import { expect, test as base, type Page } from "@playwright/test";

/** Fails a test on any uncaught page error or console error. */
export const test = base.extend<{ page: Page }>({
  page: async ({ page }, use) => {
    const problems: string[] = [];
    page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
    page.on("console", (m) => {
      if (m.type() === "error") problems.push(`console: ${m.text()}`);
    });
    await use(page);
    expect(problems, "browser errors").toEqual([]);
  },
});

export { expect };
