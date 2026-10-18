import { expect, test } from "./fixtures";

test("the System / Light / Dark switch applies, persists and follows the OS", async ({ page, errors }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  const html = page.locator("html");
  await expect(html).toHaveAttribute("data-theme", "light");
  const bgLight = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  await expect(page.getByTestId("theme-system")).toHaveAttribute("aria-pressed", "true");

  await page.getByTestId("theme-light").click();
  await expect(page.getByTestId("theme-light")).toHaveAttribute("aria-pressed", "true");
  await page.getByTestId("theme-dark").click();
  await expect(html).toHaveAttribute("data-theme", "dark");
  const bgDark = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(bgDark).not.toBe(bgLight);

  await page.reload();
  await expect(html).toHaveAttribute("data-theme", "dark"); // persisted, applied before paint
  await expect(page.getByTestId("theme-dark")).toHaveAttribute("aria-pressed", "true");

  await page.getByTestId("theme-system").click();
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(html).toHaveAttribute("data-theme", "dark"); // follows the OS in system mode
  expect(errors).toEqual([]);
});
