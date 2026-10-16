import type { Page } from "@playwright/test";
import { expect, test, unlock } from "./fixtures";

// 08: the Firefighter (scenarios, alert storm, hypotheses, actions + approval), the eval page, the Story hooks.
const OUT = "../docs/screenshots";

async function openScenario(page: Page, id: string, tenant = "kestrel_pay") {
  await page.goto(`/firefighter?tenant=${tenant}`);
  await page.getByTestId(`scenario-${id}`).click();
  await expect(page.getByTestId("ff-step").first()).toBeVisible({ timeout: 20_000 });
  await page.getByTestId("ff-play").click(); // pause the autoplay
}

async function seekFF(page: Page, idx: number | "end") {
  const s = page.getByTestId("ff-scrubber");
  await s.fill(idx === "end" ? (await s.getAttribute("max"))! : String(idx));
}

async function toolIndex(page: Page, replay: string, tool: string) {
  return page.evaluate(async ([name, t]) => {
    const r = await (await fetch(`/api/replay/${name}`)).json();
    return r.events.filter((e: any) => e.event === "step").findIndex((e: any) => e.data.tool === t);
  }, [replay, tool]);
}

async function shot(page: Page, name: string, theme: string, ms = 1300) {
  await page.waitForTimeout(ms);
  await page.mouse.move(2, 890);
  await page.screenshot({ path: `${OUT}/${name}-${theme}.png` });
}

test("alert storm: six alerts collapse into two incidents, pages suppressed with reasons", async ({ page }) => {
  await openScenario(page, "k-storm");
  await expect(page.getByTestId("ff-caption")).toContainText("6 alerts");
  await seekFF(page, "end");
  await expect(page.getByTestId("outcome")).toContainText("6 alerts → 2 incidents · 2 pages");
  await page.getByTestId("tab-report").click();
  await expect(page.getByTestId("suppressed").locator("li")).toHaveCount(5);
  await page.getByTestId("tab-actions").click();
  await expect(page.getByTestId("action-suppress_page")).toHaveCount(5);
  await expect(page.getByTestId("verification")).toContainText("Cleared");
  await expect(page.getByTestId("approve")).toHaveCount(0); // recordings can't be approved
});

test("hypotheses: the false lead is rejected with the evidence that killed it; why on every step", async ({ page }) => {
  await openScenario(page, "k-falselead");
  await expect(page.getByTestId("ff-step").first()).toContainText("why:");
  await seekFF(page, "end");
  await page.getByTestId("tab-board").click();
  await expect(page.getByTestId("hyp-confirmed")).toHaveCount(1);
  await expect(page.getByTestId("hyp-rejected")).toHaveCount(2);
  await expect(page.getByTestId("board")).toContainText("merchant-dashboard");
});

test("a risky rollback becomes 'hold' with the safety check's reason", async ({ page }) => {
  await openScenario(page, "n-falselead", "northwind_health");
  await seekFF(page, "end");
  await page.getByTestId("tab-actions").click();
  await expect(page.getByTestId("action-hold")).toBeVisible();
  await expect(page.getByTestId("safety")).toContainText("risky");
});

test("eval page and the story's buttons", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("go-why").click();
  await expect(page.getByTestId("why-graph")).toContainText("Full Incident Brain");
  await expect(page.getByTestId("scoreboard")).toContainText("passed");
  await page.goto("/");
  await page.getByTestId("go-storm").click();
  await expect(page.getByTestId("ff-caption")).toContainText("6 alerts", { timeout: 20_000 });
});

test("with the access code: a fresh run, approve, verification", async ({ page }) => {
  test.skip(!process.env.E2E_CODE, "needs the server's access code");
  await page.goto("/firefighter");
  await unlock(page);
  await page.getByTestId("scenario-k-falselead").click();
  await expect(page.getByTestId("ff-caption")).toContainText("fresh mock run", { timeout: 30_000 });
  await seekFF(page, "end");
  await page.getByTestId("tab-actions").click();
  await page.getByTestId("approve").click();
  await expect(page.getByTestId("verification")).toContainText("Cleared", { timeout: 20_000 });
});

for (const theme of ["light", "dark"] as const) {
  test(`firefighter, hypotheses and eval screenshots (${theme})`, async ({ page }) => {
    test.setTimeout(120_000);
    await page.addInitScript((t) => localStorage.setItem("ib.theme", t), theme);
    await openScenario(page, "k-storm");
    await seekFF(page, await toolIndex(page, "ff-k-storm", "connected_impact"));
    await shot(page, "ff-storm-correlate", theme);
    await seekFF(page, "end");
    await page.getByTestId("tab-report").click();
    await shot(page, "ff-storm-outcome", theme);
    await page.getByTestId("tab-actions").click();
    await shot(page, "ff-storm-actions", theme, 500);
    await openScenario(page, "k-falselead");
    await seekFF(page, "end");
    await page.getByTestId("tab-board").click();
    await shot(page, "ff-hypotheses", theme);
    await openScenario(page, "n-falselead", "northwind_health");
    await seekFF(page, "end");
    await page.getByTestId("tab-actions").click();
    await shot(page, "ff-safety-hold", theme);
    await page.goto("/eval");
    await expect(page.getByTestId("why-graph")).toBeVisible();
    await shot(page, "eval-why-a-graph", theme, 500);
  });
}

test("storm hero 1920×1080", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await openScenario(page, "k-storm");
  await seekFF(page, "end");
  await page.getByTestId("tab-actions").click();
  await page.waitForTimeout(1500);
  await page.mouse.move(2, 1070);
  await page.screenshot({ path: `${OUT}/ff-storm-1920.png` });
});
