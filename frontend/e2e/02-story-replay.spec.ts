import { expect, fire, seek, seekEnd, test } from "./fixtures";

test("the whole story replays: four beats, the learned edge, and the before/after numbers", async ({ page, request }) => {
  const posts: string[] = [];
  page.on("request", (r) => r.method() === "POST" && r.url().includes("/api/story/") && posts.push(r.url()));
  await page.goto("/");
  await expect(page.getByTestId("mode-badge")).toHaveText("Replay");
  const story = await (await request.get("/api/story?tenant=kestrel_pay")).json();
  const [s1, resolve, s2, compare] = story.beats;
  await expect(page.getByTestId(`beat-${s1.id}`)).toHaveText(s1.label);
  await expect(page.getByTestId(`beat-${resolve.id}`)).toBeDisabled();
  await expect(page.getByTestId("graph")).toHaveAttribute("data-visible-nodes", /^[1-9]/); // the alert's neighbourhood

  // Session 1
  await fire(page, s1.id);
  await expect(page.getByTestId("graph")).toHaveAttribute("data-learned-edges", "0");
  const learnedIdx = await page.evaluate(async () => {
    const r = await (await fetch("/api/replay/team-session1")).json();
    const steps = r.events.filter((e: any) => e.event === "step").map((e: any) => e.data);
    return steps.findIndex((s: any) => s.writes.edges.some((e: any) => e.type === "DEPENDS_ON"));
  });
  await seek(page, learnedIdx);
  await expect(page.getByTestId("receipt")).toContainText("record_learned_dependency");
  await expect(page.getByTestId("receipt").getByTestId("source-card").first()).toBeVisible();
  await expect(page.getByTestId("graph")).toHaveAttribute("data-learned-edges", "1");
  await seek(page, learnedIdx - 1);
  await expect(page.getByTestId("graph")).toHaveAttribute("data-learned-edges", "0"); // scrubbing back hides it again
  await seekEnd(page);
  await expect(page.getByTestId("report")).toContainText("Final report");
  await expect(page.getByTestId("report")).toContainText("Maintainer left");

  // keyboard
  await page.keyboard.press("ArrowLeft");
  await expect(page.getByTestId("step-count")).toHaveText(/step 23 \//);
  await page.keyboard.press("ArrowRight");

  // Resolve, Session 2, Compare
  await fire(page, resolve.id);
  await seekEnd(page);
  await expect(page.getByTestId("report")).toContainText("Resolved");
  await fire(page, s2.id);
  await seek(page, 6);
  await expect(page.getByTestId("receipt")).toContainText("memory_recall");
  await seekEnd(page);
  await expect(page.getByTestId("report")).toContainText("Seen before");
  await fire(page, compare.id);
  await seekEnd(page);

  const panel = page.getByTestId("compare");
  await expect(panel).toBeVisible();
  const numbers = await (await request.get("/api/compare/latest?tenant=kestrel_pay")).json();
  for (const col of numbers.columns) {
    const want = col.cause_found ? String(col.investigator_tool_calls_until_cause) : "not found";
    await expect(panel.getByTestId(`compare-${col.key}`).getByTestId("calls")).toHaveText(want);
  }
  expect(numbers.columns.map((c: any) => c.investigator_tool_calls_until_cause)).toEqual([8, 3, null]);
  expect(posts).toEqual([]); // no code: nothing but recorded runs
});

test("autoplay is deterministic and pausable", async ({ page }) => {
  await page.goto("/");
  const story = await (await page.request.get("/api/story?tenant=kestrel_pay")).json();
  await page.getByTestId(`beat-${story.beats[0].id}`).click();
  await expect(page.getByTestId("step-count")).toHaveText(/step 2 \//, { timeout: 8000 });
  await page.keyboard.press("Space");
  const at = await page.getByTestId("step-count").textContent();
  await page.waitForTimeout(2500);
  await expect(page.getByTestId("step-count")).toHaveText(at!);
});
