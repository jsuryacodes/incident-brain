import { create } from "zustand";
import { api } from "../../lib/api";
import { initialPlayer, playerReducer, type Player, type PlayerAction } from "../../lib/replay";
import type { Execution, Report, RunGraph, Scenario, StepEvent } from "../../lib/types";

export type FFTab = "step" | "board" | "actions" | "report" | "node";
export type FFRun = {
  runId: string; mode: "replay" | "mock" | "live"; steps: StepEvent[]; report: Report | null; status?: string;
  execution: Execution | null; alerts: { service_id: string; symptom: string }[]; scenario: string | null;
  totals?: Record<string, number>;
};

type FFState = {
  tenant: string;
  scenarios: Scenario[];
  services: { id: string; name: string }[];
  error: string | null;
  sel: string | null;
  run: FFRun | null;
  graph: RunGraph | null;
  loading: boolean;
  approving: boolean;
  player: Player;
  tab: FFTab;
  selected: string | null;
  init: (tenant: string) => Promise<void>;
  pick: (id: string, fresh: boolean) => Promise<void>;
  runCustom: (alerts: { service_id: string; symptom: string }[]) => Promise<void>;
  approve: (actionIds: string[] | null) => Promise<void>;
  dispatch: (a: PlayerAction) => void;
  setTab: (t: FFTab) => void;
  select: (id: string | null) => void;
};

const asList = (a: any): { service_id: string; symptom: string }[] => (Array.isArray(a) ? a : a ? [a] : []);

/** A fresh run streams over EventSource (one-time token), exactly like the story's fresh beats. */
function streamRun(start: { stream: string; mode: string }, alerts: { service_id: string; symptom: string }[], scenario: string | null): Promise<FFRun> {
  return new Promise((resolve, reject) => {
    const run: FFRun = { runId: "", mode: start.mode === "live" ? "live" : "mock", steps: [], report: null, execution: null, alerts, scenario };
    const es = new EventSource(start.stream);
    const fail = (m: string) => (es.close(), reject(new Error(m)));
    es.addEventListener("step", (e) => run.steps.push(JSON.parse((e as MessageEvent).data)));
    es.addEventListener("report", (e) => (run.report = JSON.parse((e as MessageEvent).data).report));
    es.addEventListener("run", (e) => {
      const d = JSON.parse((e as MessageEvent).data);
      run.runId = d.run_id;
      run.status = d.status;
      es.close();
      resolve(run);
    });
    es.addEventListener("error", (e) => {
      const data = (e as MessageEvent).data;
      if (data) return fail(JSON.parse(data).error || "the run failed");
      if (es.readyState !== EventSource.OPEN) fail("the run stream closed early");
    });
  });
}

export const useFF = create<FFState>((set, get) => ({
  tenant: "", scenarios: [], services: [], error: null, sel: null, run: null, graph: null, loading: false, approving: false,
  player: initialPlayer, tab: "step", selected: null,

  init: async (tenant) => {
    if (get().tenant === tenant && get().scenarios.length) return;
    set({ tenant, scenarios: [], services: [], error: null, sel: null, run: null, graph: null, player: initialPlayer, tab: "step", selected: null });
    try {
      const p = await api.playground(tenant);
      if (get().tenant === tenant) set({ scenarios: p.scenarios, services: p.services });
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  pick: async (id, fresh) => {
    const sc = get().scenarios.find((s) => s.id === id);
    if (!sc || get().loading) return;
    set({ loading: true, sel: id });
    try {
      let run: FFRun;
      let graph: RunGraph;
      if (fresh) {
        run = await streamRun(await api.startFirefighter({ tenant: get().tenant, scenario_id: id }), sc.alerts, id);
        graph = await api.runGraph(run.runId);
      } else {
        if (!sc.replay) throw new Error("no recording for this scenario: enter the access code to run it fresh");
        const r = await api.replay(sc.replay);
        run = { runId: r.run_id, mode: "replay", steps: r.events.filter((e: any) => e.event === "step").map((e: any) => e.data),
          report: r.report, status: r.status, execution: r.execution || null, alerts: asList(r.alert), scenario: id, totals: r.totals };
        graph = await api.runGraph(sc.replay);
      }
      set({ run, graph, loading: false, tab: "step", selected: null,
        player: playerReducer(get().player, { type: "load", total: run.steps.length, autoplay: true }) });
    } catch (e) {
      set({ loading: false });
      throw e;
    }
  },

  runCustom: async (alerts) => {
    if (get().loading) return;
    set({ loading: true, sel: "custom" });
    try {
      const run = await streamRun(await api.startFirefighter({ tenant: get().tenant, alerts }), alerts, null);
      const graph = await api.runGraph(run.runId);
      set({ run, graph, loading: false, tab: "step", selected: null,
        player: playerReducer(get().player, { type: "load", total: run.steps.length, autoplay: true }) });
    } catch (e) {
      set({ loading: false });
      throw e;
    }
  },

  approve: async (actionIds) => {
    const run = get().run;
    if (!run || run.mode === "replay" || get().approving) return;
    set({ approving: true });
    try {
      const execution = await api.execute(run.runId, actionIds);
      set({ run: { ...run, execution }, approving: false });
    } catch (e) {
      set({ approving: false });
      throw e;
    }
  },

  dispatch: (a) => {
    const player = playerReducer(get().player, a);
    const atEnd = player.total > 0 && player.idx === player.total - 1;
    const patch: Partial<FFState> = { player };
    if (atEnd && a.type === "tick" && get().run?.report) patch.tab = "report";
    set(patch);
  },
  setTab: (tab) => set({ tab }),
  select: (id) => set({ selected: id, tab: id ? "node" : "step" }),
}));
