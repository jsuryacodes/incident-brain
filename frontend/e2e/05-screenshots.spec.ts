import type { Page } from "@playwright/test";
import { expect, fire, seek, seekEnd, test } from "./fixtures";

// Screenshots for the README and for review: docs/screenshots/<name>-<theme>.png at 1440×900, both themes,
// plus a 1920×1080 hero and a 390×844 phone shot. Recorded runs only (no code), so they are identical every time.
const OUT = "../docs/screenshots";

async function stepIndex(page: Page, replay: string, tool: string) {
  return page.evaluate(async ([name, t]) => {
    const r = await (await fetch(`/api/replay/${name}`)).json();
    return r.events.filter((e: any) => e.event === "step").findIndex((e: any) => e.data.tool === t);
  }, [replay, tool]);
}

async function settle(page: Page, ms = 1400) {
  await page.waitForTimeout(ms); // camera pan + fade-ins
}

async function shot(page: Page, name: string, theme: string) {
  await page.mouse.move(2, 890); // no hover labels
  await page.screenshot({ path: `${OUT}/${name}-${theme}.png` });
}

for (const theme of ["light", "dark"] as const) {
  test(`story, brain and explorer screenshots (${theme})`, async ({ page }) => {
    test.setTimeout(120_000);
    await page.addInitScript((t) => localStorage.setItem("ib.theme", t), theme);
    await page.goto("/");
    const story = await (await page.request.get("/api/story?tenant=kestrel_pay")).json();
    const [s1, resolve, s2, compare] = story.beats;
    await expect(page.getByTestId("graph")).toHaveAttribute("data-visible-nodes", /^[1-9]/);
    await settle(page);
    await shot(page, "story-start", theme);

    await fire(page, s1.id);
    await seek(page, await stepIndex(page, s1.replay, "recent_changes_downstream"));
    await settle(page);
    await shot(page, "story-path-mid-investigation", theme);
    await seek(page, await stepIndex(page, s1.replay, "record_learned_dependency"));
    await settle(page, 2200);
    await shot(page, "story-learned-edge", theme);
    await seekEnd(page);

    await fire(page, resolve.id);
    await seekEnd(page);
    await settle(page);
    await shot(page, "story-resolved-memory", theme);
    await fire(page, s2.id);
    await seek(page, await stepIndex(page, s2.replay, "memory_recall"));
    await settle(page);
    await shot(page, "story-session2-recall", theme);
    await seekEnd(page);
    await fire(page, compare.id);
    await seekEnd(page);
    await expect(page.getByTestId("compare")).toBeVisible();
    await settle(page, 600);
    await shot(page, "story-before-after", theme);

    await page.goto("/brain");
    await page.getByTestId("suggestion").first().click();
    const a = page.getByTestId("answer").first();
    await expect(a).toBeVisible();
    await a.getByText("Cited nodes as a graph").click();
    await settle(page, 900);
    await shot(page, "brain-answer", theme);

    await page.goto("/explorer");
    await page.getByTestId("hubs").check();
    await expect(page.getByTestId("graph")).toHaveAttribute("data-visible-nodes", /^[1-9]/);
    await settle(page, 900);
    await shot(page, "explorer-overview", theme);
    const meta = await (await page.request.get("/api/meta")).json();
    await page.getByTestId("tenant").selectOption(meta.tenants.find((t: any) => !t.has_story).id);
    await page.getByTestId("agent-only").check();
    await expect(page.getByText(/No agent memory in/)).toBeVisible();
    await shot(page, "explorer-second-tenant", theme);
  });
}

test("hero 1920×1080 and phone 390×844", async ({ browser }) => {
  const hero = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  await hero.addInitScript(() => localStorage.setItem("ib.theme", "light"));
  await hero.goto("/");
  const story = await (await hero.request.get("/api/story?tenant=kestrel_pay")).json();
  await fire(hero, story.beats[0].id);
  await seek(hero, await stepIndex(hero, story.beats[0].replay, "record_learned_dependency"));
  await settle(hero, 2200);
  await hero.mouse.move(2, 1070);
  await hero.screenshot({ path: `${OUT}/story-learned-edge-1920.png` });
  await hero.close();

  const phone = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  await phone.addInitScript(() => localStorage.setItem("ib.theme", "light"));
  await phone.goto("/");
  await fire(phone, story.beats[0].id);
  await seek(phone, await stepIndex(phone, story.beats[0].replay, "recent_changes_downstream"));
  await settle(phone);
  await phone.screenshot({ path: `${OUT}/mobile-story.png` });
  const width = await phone.evaluate(() => document.documentElement.scrollWidth);
  expect(width).toBeLessThanOrEqual(390); // no horizontal scroll
  await phone.close();
});
