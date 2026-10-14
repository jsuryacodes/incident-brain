import { create } from "zustand";

export type ThemePref = "system" | "light" | "dark";
export type Theme = "light" | "dark";
const KEY = "ib.theme";
const ORDER: ThemePref[] = ["system", "light", "dark"];

export const nextPref = (p: ThemePref): ThemePref => ORDER[(ORDER.indexOf(p) + 1) % ORDER.length];
export const resolveTheme = (p: ThemePref, systemDark: boolean): Theme =>
  p === "system" ? (systemDark ? "dark" : "light") : p;

export function readPref(): ThemePref {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" || v === "system" ? v : "system";
  } catch {
    return "system"; // storage blocked: still works, just not remembered
  }
}

function writePref(p: ThemePref) {
  try {
    localStorage.setItem(KEY, p);
  } catch {
    /* not persisted */
  }
}

const systemDark = () => typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: dark)").matches;

type ThemeState = { pref: ThemePref; theme: Theme; cycle: () => void; set: (p: ThemePref) => void; syncSystem: () => void };

export const useTheme = create<ThemeState>((set, get) => {
  const apply = (pref: ThemePref) => {
    const theme = resolveTheme(pref, systemDark());
    document.documentElement.setAttribute("data-theme", theme);
    set({ pref, theme });
  };
  const pref = readPref();
  return {
    pref,
    theme: resolveTheme(pref, systemDark()),
    cycle: () => {
      const p = nextPref(get().pref);
      writePref(p);
      apply(p);
    },
    set: (p) => {
      writePref(p);
      apply(p);
    },
    syncSystem: () => get().pref === "system" && apply("system"),
  };
});

if (typeof matchMedia === "function") {
  matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", () => useTheme.getState().syncSystem());
}
