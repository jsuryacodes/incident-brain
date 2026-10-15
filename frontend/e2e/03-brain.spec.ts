import { expect, test } from "./fixtures";

test("Ask the Brain: suggestion → sourced answer, follow-up pronoun, honest don't-know", async ({ page }) => {
  await page.goto("/brain");
  const first = page.getByTestId("suggestion").first();
  await expect(first).toBeVisible();
  await first.click();
  const a1 = page.getByTestId("answer").nth(0);
  await expect(a1).toBeVisible();
  expect(await a1.getByTestId("source-card").count()).toBeGreaterThan(0);
  await expect(a1.getByTestId("source-card").first()).toContainText("“");
  await expect(page.getByText("Not saved: without an access code nothing is written")).toBeVisible();

  await page.getByTestId("brain-input").fill("Who should I call about it?");
  await page.getByTestId("brain-input").press("Enter");
  const a2 = page.getByTestId("answer").nth(1);
  await expect(a2).toBeVisible();
  await expect(a2).toContainText(/Talk to|call/i);
  await expect(a2).toContainText("turn 2");

  await page.getByTestId("brain-input").fill("What is our policy for Kubernetes cluster upgrades?");
  await page.getByTestId("brain-input").press("Enter");
  const a3 = page.getByTestId("answer").nth(2);
  await expect(a3.getByTestId("dont-know")).toBeVisible();
  await expect(a3.getByTestId("source-card")).toHaveCount(0);
  await expect(a3.locator("[role=alert]")).toHaveCount(0); // honest, not an error

  await a1.getByText("How I got this").click();
  await expect(a1.locator(".cy-code").first()).toBeVisible();
});
