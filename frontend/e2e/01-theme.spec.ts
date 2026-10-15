import { expect, test } from "./fixtures";

test("theme toggle cycles System → Light → Dark, renders both, and persists", async ({ page, errors }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  const html = page.locator("html");
  await expect(html).toHaveAttribute("data-theme", "light");
  const bgLight = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  const toggle = page.getByTestId("theme-toggle");
  await expect(toggle).toContainText("system");
  await toggle.click(); // -> light
  await expect(toggle).toContainText("light");
  await toggle.click(); // -> dark
  await expect(html).toHaveAttribute("data-theme", "dark");
  const bgDark = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(bgDark).not.toBe(bgLight);
  await page.reload();
  await expect(html).toHaveAttribute("data-theme", "dark"); // persisted, applied before paint
  await expect(page.getByTestId("theme-toggle")).toContainText("dark");
  await page.getByTestId("theme-toggle").click(); // -> system
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(html).toHaveAttribute("data-theme", "dark"); // follows the OS in system mode
  expect(errors).toEqual([]);
});
