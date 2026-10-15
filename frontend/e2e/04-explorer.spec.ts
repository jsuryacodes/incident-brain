import { expect, test } from "./fixtures";

test("Explorer: filters, agent-memory toggle, critical hubs, and the second company has zero memory", async ({ page }) => {
  await page.goto("/explorer");
  const graph = page.getByTestId("graph");
  await expect(graph).toHaveAttribute("data-visible-nodes", /^[1-9]\d+/);
  const before = Number(await graph.getAttribute("data-visible-nodes"));
  await page.getByTestId("label-Decision").check();
  await expect.poll(async () => Number(await graph.getAttribute("data-visible-nodes"))).toBeGreaterThan(before);
  await page.getByTestId("hubs").check();
  await expect(page.getByText("Service size = PageRank")).toBeVisible();

  await page.getByTestId("explorer-search").fill("config");
  await expect(page.getByText(/\d+ match/)).toBeVisible();
  await page.getByTestId("explorer-search").fill("");

  await page.getByTestId("agent-only").check();
  await expect(graph).toHaveAttribute("data-agent-nodes", /^[1-9]/); // the story's memory on the hero company
  await expect(page.getByTestId("explorer-counts")).toContainText(/Agent memory in .*: [1-9]/);

  const tenants = await (await page.request.get("/api/meta")).json();
  const other = tenants.tenants.find((t: any) => !t.has_story);
  await page.getByTestId("tenant").selectOption(other.id);
  await page.getByTestId("agent-only").check();
  await expect(page.getByText(`No agent memory in ${other.name}`)).toBeVisible();
  await expect(page.getByTestId("explorer-counts")).toContainText(": 0 nodes, 0 edges");
});
