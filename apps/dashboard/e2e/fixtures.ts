import { expect, test as base, type Page } from "@playwright/test";

/** Fails a test on any uncaught page error or console error.
 *  A test that provokes an HTTP error on purpose lists the status in `expectedHttpErrors`;
 *  the browser's matching "Failed to load resource" console line is then not a problem. */
export const test = base.extend<{ page: Page; expectedHttpErrors: number[] }>({
  expectedHttpErrors: [[], { option: true }],
  page: async ({ page, expectedHttpErrors }, use) => {
    const problems: string[] = [];
    page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
    page.on("console", (m) => {
      if (m.type() !== "error") return;
      const expected = expectedHttpErrors.some((code) => m.text().includes(`status of ${code}`));
      if (!expected) problems.push(`console: ${m.text()}`);
    });
    await use(page);
    expect(problems, "browser errors").toEqual([]);
  },
});

export { expect };
