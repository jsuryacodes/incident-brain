import { expect, test as base, type Page } from "@playwright/test";

export const CODE = process.env.E2E_CODE || "e2e-code";

/** Every test fails on any console error or uncaught page error. */
export const test = base.extend<{ errors: string[] }>({
  errors: [
    async ({ page }, use) => {
      const errors: string[] = [];
      page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
      page.on("pageerror", (e) => errors.push(String(e)));
      await use(errors);
      expect(errors, "console errors").toEqual([]);
    },
    { auto: true },
  ],
});
export { expect };

export async function seekEnd(page: Page) {
  const s = page.getByTestId("scrubber");
  await s.fill((await s.getAttribute("max"))!);
}

export async function seek(page: Page, idx: number) {
  await page.getByTestId("scrubber").fill(String(idx));
}

/** Fire a story beat and wait until its first step is on screen; then pause. */
export async function fire(page: Page, beat: string) {
  const btn = page.getByTestId(`beat-${beat}`);
  await btn.click();
  await expect(btn).toHaveAttribute("aria-current", "true", { timeout: 20_000 });
  await expect(btn).toHaveAttribute("aria-busy", "false");
  await page.getByTestId("scrubber").fill("-1");
}

export async function unlock(page: Page) {
  await page.getByRole("button", { name: "Enter access code" }).click();
  await page.getByTestId("code-input").fill(CODE);
  await page.getByRole("button", { name: "Unlock" }).click();
  await expect(page.getByTestId("mode-badge")).toHaveText(/Mock/);
}
