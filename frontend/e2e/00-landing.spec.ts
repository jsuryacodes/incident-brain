import { expect, test } from "./fixtures";
import type { Page } from "@playwright/test";

/** Walk the page to the bottom so every scroll reveal fires, then back to the top. */
async function revealAll(page: Page) {
  for (let i = 0; i < 28; i++) {
    await page.evaluate(() => scrollBy(0, innerHeight * 0.75));
    await page.waitForTimeout(110);
  }
  await page.evaluate(() => scrollTo(0, 0));
  await page.waitForTimeout(900);
}

// The landing page at /welcome: renders in both themes, no console errors, and leads into the console at "/".
// Screenshots land in docs/screenshots/landing-*.png (1920, 1440 both themes, 390 phone).
const OUT = "../docs/screenshots";

for (const theme of ["light", "dark"] as const) {
  test(`landing renders and reaches the console (${theme})`, async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
    page.on("pageerror", (e) => errors.push(e.message));
    await page.addInitScript((t) => localStorage.setItem("ib.theme", t), theme);
    await page.goto("/welcome");

    await expect(page.getByTestId("landing")).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toContainText("3 a.m.");
    await expect(page.getByText("deterministic rule planner").first()).toBeVisible();
    // Walk the whole page so every scroll reveal fires, then come back to the top for the screenshot.
    await revealAll(page);
    await expect(page.getByText("Open the console.", { exact: true })).toBeVisible();
    await page.screenshot({ path: `${OUT}/landing-${theme}-1440.png` });
    await page.screenshot({ path: `${OUT}/landing-full-${theme}.png`, fullPage: true });
    expect(errors, errors.join("\n")).toEqual([]);

    await page.getByTestId("open-console").click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("navigation", { name: "Views" })).toBeVisible();
  });
}

test("landing at 1920 and on a phone", async ({ browser }) => {
  for (const [name, size, theme] of [
    ["landing-light-1920", { width: 1920, height: 1080 }, "light"],
    ["landing-dark-1920", { width: 1920, height: 1080 }, "dark"],
    ["landing-mobile-390", { width: 390, height: 844 }, "light"],
  ] as const) {
    const ctx = await browser.newContext({ viewport: size });
    const page = await ctx.newPage();
    await page.addInitScript((t) => localStorage.setItem("ib.theme", t), theme);
    await page.goto("/welcome");
    await expect(page.getByTestId("landing")).toBeVisible();
    // No horizontal page scroll at any width.
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await revealAll(page);
    await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: false });
    if (name === "landing-mobile-390") await page.screenshot({ path: `${OUT}/landing-full-mobile.png`, fullPage: true });
    await ctx.close();
  }
});
