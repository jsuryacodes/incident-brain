import { afterEach, describe, expect, it, vi } from "vitest";
import { nextPref, readPref, resolveTheme, useTheme } from "./theme";

describe("theme", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("cycles System → Light → Dark → System", () => {
    expect(nextPref("system")).toBe("light");
    expect(nextPref("light")).toBe("dark");
    expect(nextPref("dark")).toBe("system");
  });

  it("follows the OS only in system mode", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });

  it("persists the choice and sets data-theme", () => {
    useTheme.getState().set("dark");
    expect(localStorage.getItem("ib.theme")).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    useTheme.getState().cycle(); // dark -> system (jsdom has no dark OS preference)
    expect(useTheme.getState().pref).toBe("system");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(readPref()).toBe("system");
  });

  it("works when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readPref()).toBe("system");
    expect(() => useTheme.getState().set("light")).not.toThrow();
    expect(useTheme.getState().theme).toBe("light");
  });

  it("ignores junk in storage", () => {
    localStorage.setItem("ib.theme", "purple");
    expect(readPref()).toBe("system");
  });
});
