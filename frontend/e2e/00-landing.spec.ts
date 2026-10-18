import { expect, test } from "./fixtures";
import type { Page } from "@playwright/test";

// The landing page at /welcome: renders in both themes, no console errors, and leads into the console.
// Screenshots land in docs/screenshots/landing-*.png (1920, 1440 both themes, 390 phone).
const OUT = "../docs/screenshots";

/** Walk the page to the bottom so every scroll reveal fires, then back to the top. */
async function revealAll(page: Page) {
  for (let i = 0; i < 28; i++) {
    await page.evaluate(() => scrollBy(0, innerHeight * 0.75));
    await page.waitForTimeout(110);
  }
  await page.evaluate(() => scrollTo(0, 0));
  await page.waitForTimeout(900);
}

for (const theme of ["light", "dark"] as const) {
  test(`landing renders and reaches the console (${theme})`, async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
    page.on("pageerror", (e) => errors.push(e.message));
    await page.addInitScript((t) => localStorage.setItem("ib.theme", t), theme);
    await page.goto("/welcome");

    await expect(page.getByTestId("landing")).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toContainText("3 a.m.");
    await expect(page.getByText("not by a language model").first()).toBeVisible();
    await revealAll(page);
    await expect(page.getByText("Open the console.", { exact: true })).toBeVisible();
    await page.screenshot({ path: `${OUT}/landing-${theme}-1440.png` });
    await page.screenshot({ path: `${OUT}/landing-full-${theme}.png`, fullPage: true });
    expect(errors, errors.join("\n")).toEqual([]);

    // Served by FastAPI, every "Open the console" button goes straight into the console.
    await page.getByTestId("open-console").click();
    await expect(page).toHaveURL(/\/firefighter$/);
    await expect(page.getByRole("navigation", { name: "Views" })).toBeVisible();
  });
}

test("the copy has no em or en dashes", async ({ page }) => {
  await page.goto("/welcome");
  await revealAll(page);
  const text = await page.evaluate(() => document.body.innerText);
  expect(text.match(/[—–]/g) || []).toEqual([]);
});

test("the hero animation has captions and controls", async ({ page }) => {
  await page.goto("/welcome");
  const caption = page.getByTestId("hero-caption");
  const first = await caption.textContent();
  await expect(caption).not.toHaveText(first!, { timeout: 6000 }); // it plays on its own
  const hero = page.locator("div").filter({ has: page.getByTestId("hero-caption") }).last();
  await hero.getByTestId("play").click(); // pause
  const held = await caption.textContent();
  await page.waitForTimeout(1200);
  await expect(caption).toHaveText(held!);
  await hero.getByTestId("next").click();
  await expect(caption).not.toHaveText(held!);
  await hero.getByTestId("prev").click();
  await expect(caption).toHaveText(held!);
  await hero.getByTestId("speed-2").click();
  await expect(hero.getByTestId("speed-2")).toHaveAttribute("aria-pressed", "true");
});

test("the how-it-works stepper runs one step at a time and takes orders", async ({ page }) => {
  await page.goto("/welcome");
  const stepper = page.getByTestId("stepper");
  await stepper.scrollIntoViewIfNeeded();
  const title = page.getByTestId("step-title");
  await expect(title).toHaveText("An alarm goes off");
  // Exactly one step is current at any moment.
  const current = page.locator('[data-testid^="step-"][aria-current="step"]');
  await expect(current).toHaveCount(1);
  // It starts playing when it scrolls into view, and changing the speed does not stop it.
  await expect(stepper.getByTestId("play")).toHaveAttribute("aria-label", "Pause");
  await stepper.getByTestId("speed-2").click();
  await expect(title).not.toHaveText("An alarm goes off", { timeout: 8000 });
  await expect(current).toHaveCount(1);

  await page.getByTestId("step-5").click(); // jumping pauses
  await expect(title).toHaveText("Remember it");
  await expect(stepper.getByTestId("play")).toHaveAttribute("aria-label", "Play");
  await stepper.getByTestId("next").click(); // it stops at the last step
  await expect(title).toHaveText("Remember it");
  await stepper.getByTestId("prev").click();
  await expect(title).toHaveText("Act, but safely");
  await stepper.getByTestId("restart").click();
  await expect(title).toHaveText("An alarm goes off");

  await page.getByTestId("step-2").click();
  await stepper.press("ArrowRight");
  await expect(title).toHaveText("Line up the suspects");
  await stepper.press("ArrowLeft");
  await expect(title).toHaveText("Walk the map");
});

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
