import { expect, test } from "vitest";
import { viewFromPath } from "./store";

test("the console keeps / and the landing page lives at /welcome", () => {
  expect(viewFromPath("/")).toBe("story");
  expect(viewFromPath("/welcome")).toBe("landing");
  expect(viewFromPath("/firefighter")).toBe("firefighter");
  expect(viewFromPath("/eval")).toBe("eval");
  expect(viewFromPath("/brain")).toBe("brain");
  expect(viewFromPath("/explorer")).toBe("explorer");
});
