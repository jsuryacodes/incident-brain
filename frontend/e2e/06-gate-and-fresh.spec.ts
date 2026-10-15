import { CODE, expect, fire, seekEnd, test, unlock } from "./fixtures";

test("the access-code gate: no code, no writes", async ({ page, request }) => {
  for (const beat of ["session1", "resolve", "session2", "compare"]) {
    expect((await request.post(`/api/story/${beat}/run`, { data: { tenant: "kestrel_pay" } })).status()).toBe(403);
  }
  expect((await request.post("/api/team/run", { data: { service_id: "svc:x", symptom: "x" } })).status()).toBe(403);
  await page.goto("/");
  await page.getByRole("button", { name: "Enter access code" }).click();
  await page.getByTestId("code-input").fill("wrong-code");
  await page.getByRole("button", { name: "Unlock" }).click();
  await expect(page.getByText("That code didn't work.")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("mode-badge")).toHaveText("Replay"); // falls back to the recorded runs
});

test("with the access code the story runs fresh (mock) and writes memory", async ({ page, request }) => {
  const story = await (await request.get("/api/story?tenant=kestrel_pay")).json();
  const posts: string[] = [];
  page.on("request", (r) => r.method() === "POST" && r.url().includes("/api/story/") && posts.push(r.headers()["x-access-code"] || "none"));
  await page.goto("/");
  await unlock(page);
  for (const beat of story.beats) {
    await fire(page, beat.id);
    await seekEnd(page);
    await expect(page.getByTestId("report")).toBeVisible();
  }
  expect(posts).toEqual(story.beats.map(() => CODE));
  const panel = page.getByTestId("compare");
  await expect(panel).toBeVisible();
  await expect(panel).toContainText("Numbers from your fresh runs.");
  const c = await (await request.get("/api/compare/latest?tenant=kestrel_pay")).json();
  expect(c.source).toBe("fresh");
  expect(c.columns.map((x: any) => x.investigator_tool_calls_until_cause)).toEqual([8, 3, null]);
  // Brain with the code: persisted in the graph
  await page.goto("/brain");
  await page.getByTestId("suggestion").first().click();
  await expect(page.getByTestId("answer").first()).toContainText("saved in ses:");
});
