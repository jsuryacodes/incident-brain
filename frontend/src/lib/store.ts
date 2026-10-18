import { create } from "zustand";
import { api, getCode, setCode } from "./api";
import type { Meta } from "./types";

export type View = "landing" | "story" | "firefighter" | "eval" | "brain" | "explorer";
const PATHS: Record<View, string> = { landing: "/welcome", story: "/", firefighter: "/firefighter", eval: "/eval", brain: "/brain", explorer: "/explorer" };
// Served by FastAPI, "/" is the console (unchanged). In the static build (VITE_STATIC=1, Vercel) there is no API,
// so "/" is the landing page instead.
const STATIC_BUILD = import.meta.env.VITE_STATIC === "1";
export const viewFromPath = (p: string): View =>
  p.startsWith("/welcome") ? "landing"
    : p.startsWith("/brain") ? "brain" : p.startsWith("/explorer") ? "explorer" : p.startsWith("/firefighter") ? "firefighter"
      : p.startsWith("/eval") ? "eval" : STATIC_BUILD ? "landing" : "story";

export type Toast = { id: number; text: string; kind: "error" | "info"; retry?: () => void };

type AppState = {
  view: View;
  tenant: string;
  meta: Meta | null;
  unlocked: boolean; // a valid access code is in sessionStorage
  toasts: Toast[];
  setView: (v: View) => void;
  setTenant: (t: string) => void;
  loadMeta: () => Promise<void>;
  unlock: (code: string) => Promise<boolean>;
  lock: () => void;
  toast: (text: string, kind?: Toast["kind"], retry?: () => void) => void;
  dismiss: (id: number) => void;
};

let nextToast = 1;

export const useApp = create<AppState>((set, get) => ({
  view: viewFromPath(location.pathname),
  tenant: new URLSearchParams(location.search).get("tenant") || "",
  meta: null,
  unlocked: !!getCode(),
  toasts: [],
  setView: (view) => {
    if (view !== get().view) history.pushState({}, "", PATHS[view] + location.search);
    set({ view });
  },
  setTenant: (tenant) => {
    const u = new URL(location.href);
    u.searchParams.set("tenant", tenant);
    history.replaceState({}, "", u);
    set({ tenant });
  },
  loadMeta: async () => {
    try {
      const meta = await api.meta();
      const known = meta.tenants.some((t) => t.id === get().tenant);
      const hero = meta.tenants.find((t) => t.has_story) || meta.tenants[0];
      set({ meta, tenant: known ? get().tenant : hero?.id || "" });
      if (getCode() && !(await api.checkCode(getCode())).ok) get().lock(); // stale code from an earlier server
    } catch (e) {
      get().toast(`Couldn't reach the API: ${(e as Error).message}`, "error", () => get().loadMeta());
    }
  },
  unlock: async (code) => {
    const ok = (await api.checkCode(code)).ok;
    if (ok) {
      setCode(code);
      set({ unlocked: true });
    }
    return ok;
  },
  lock: () => {
    setCode("");
    set({ unlocked: false });
  },
  toast: (text, kind = "info", retry) => {
    const id = nextToast++;
    set({ toasts: [...get().toasts, { id, text, kind, retry }] });
    if (kind === "info") setTimeout(() => get().dismiss(id), 4000);
  },
  dismiss: (id) => set({ toasts: get().toasts.filter((t) => t.id !== id) }),
}));

addEventListener("popstate", () => useApp.setState({ view: viewFromPath(location.pathname) }));
