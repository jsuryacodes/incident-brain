import { defineConfig, devices } from "@playwright/test";

// The server is started by scripts/e2e.sh (fresh seed, ACCESS_CODE=E2E_CODE). Files run in order, one at a time:
// they share one server and the fresh-run spec rewrites the hero graph, so it goes last.
export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: [["list"]],
  use: {
    ...devices["Desktop Chrome"],
    baseURL: process.env.E2E_BASE_URL || "http://localhost:8000",
    viewport: { width: 1440, height: 900 },
  },
});
