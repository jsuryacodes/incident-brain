import { create } from "zustand";
import { api } from "../../lib/api";
import { initialPlayer, playerReducer, type Player, type PlayerAction } from "../../lib/replay";
import type { Beat, Compare, Elements, NodeEl, Run, RunGraph, StepEvent, Story } from "../../lib/types";
import { edgeKey } from "../../lib/types";

export type DrawerTab = "step" | "node" | "report" | "board";

/** Beats that share one layout (a beat with memory:false runs on a fresh copy of the company, so it gets its own). */
export const groupOf = (b: Beat) => (b.memory === false ? `nomem:${b.id}` : "story");

type StoryState = {
  tenant: string;
  story: Story | null;
  error: string | null;
  runGraphs: Record<string, RunGraph>; // beatId -> recorded run graph (layout universe + base)
  universe: Record<string, Elements>; // group -> every element that may appear (layout computed once)
  runs: Record<string, Run>;
  done: Record<string, boolean>;
  beat: string | null;
  loading: string | null;
  player: Player;
  compare: Compare | null;
  showCompare: boolean;
  selected: string | null;
  tab: DrawerTab;
  init: (tenant: string) => Promise<void>;
  fire: (beatId: string, fresh: boolean) => Promise<void>;
  show: (beatId: string) => void;
  dispatch: (a: PlayerAction) => void;
  select: (id: string | null) => void;
  setTab: (t: DrawerTab) => void;
  loadCompare: () => Promise<void>;
  setShowCompare: (v: boolean) => void;
  restart: () => void;
};

function merge(into: Elements, add: Elements): Elements {
  const nodes = new Map(into.nodes.map((n) => [n.id, n]));
  add.nodes.forEach((n) => nodes.set(n.id, { ...(nodes.get(n.id) || {}), ...n }));
  const edges = new Map(into.edges.map((e) => [edgeKey(e), e]));
  add.edges.forEach((e) => edges.set(edgeKey(e), { ...(edges.get(edgeKey(e)) || {}), ...e }));
  return { nodes: [...nodes.values()], edges: [...edges.values()] };
}

function runFromReplay(beat: Beat, r: any): Run {
  return {
    runId: r.run_id, beatId: beat.id, mode: "replay",
    steps: r.events.filter((e: any) => e.event === "step").map((e: any) => e.data as StepEvent),
    report: r.report, incidentKey: r.incident_key, status: r.status, totals: r.totals, alert: r.alert,
  };
}

/** A fresh run: start it (needs the code), then watch its events over EventSource until it says which run it was. */
function runFresh(tenant: string, beat: Beat): Promise<Run> {
  return api.startBeat(tenant, beat.id).then(
    (start) =>
      new Promise<Run>((resolve, reject) => {
        const steps: StepEvent[] = [];
        const run: Run = { runId: "", beatId: beat.id, mode: start.mode === "live" ? "live" : "mock", steps, report: null };
        const es = new EventSource(start.stream);
        const fail = (msg: string) => (es.close(), reject(new Error(msg)));
        es.addEventListener("start", (e) => (run.alert = JSON.parse((e as MessageEvent).data).alert));
        es.addEventListener("step", (e) => steps.push(JSON.parse((e as MessageEvent).data)));
        es.addEventListener("report", (e) => {
          const d = JSON.parse((e as MessageEvent).data);
          run.report = d.report;
        });
        es.addEventListener("done", (e) => {
          const d = JSON.parse((e as MessageEvent).data);
          run.status = d.status;
          run.totals = d.totals;
          if (!run.report && beat.kind === "resolve") run.report = steps.at(-1)?.args ?? null;
        });
        es.addEventListener("run", (e) => {
          const d = JSON.parse((e as MessageEvent).data);
          run.runId = d.run_id;
          es.close();
          resolve(run);
        });
        es.addEventListener("error", (e) => {
          const data = (e as MessageEvent).data;
          if (data) return fail(JSON.parse(data).error || "the run failed");
          if (es.readyState !== EventSource.OPEN) fail("the run stream closed early");
        });
      }),
  );
}

export const useStory = create<StoryState>((set, get) => ({
  tenant: "",
  story: null,
  error: null,
  runGraphs: {},
  universe: {},
  runs: {},
  done: {},
  beat: null,
  loading: null,
  player: initialPlayer,
  compare: null,
  showCompare: false,
  selected: null,
  tab: "step",

  init: async (tenant) => {
    if (get().tenant === tenant && get().story) return;
    set({ tenant, story: null, error: null, runGraphs: {}, universe: {}, runs: {}, done: {}, beat: null, player: initialPlayer,
      compare: null, showCompare: false, selected: null, tab: "step" });
    try {
      const story = await api.story(tenant);
      const graphs = await Promise.all(story.beats.map((b) => api.runGraph(b.replay)));
      const runGraphs: Record<string, RunGraph> = {};
      const universe: Record<string, Elements> = {};
      story.beats.forEach((b, i) => {
        runGraphs[b.id] = graphs[i];
        universe[groupOf(b)] = merge(universe[groupOf(b)] || { nodes: [], edges: [] }, graphs[i]);
      });
      if (get().tenant === tenant) set({ story, runGraphs, universe });
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  fire: async (beatId, fresh) => {
    const { story, tenant } = get();
    const beat = story?.beats.find((b) => b.id === beatId);
    if (!beat || get().loading) return;
    set({ loading: beatId });
    try {
      const run = fresh ? await runFresh(tenant, beat) : runFromReplay(beat, await api.replay(beat.replay));
      const g = groupOf(beat);
      const extra = run.steps.reduce<Elements>((acc, s) => merge(acc, s.elements), { nodes: [], edges: [] });
      const universe = { ...get().universe, [g]: merge(get().universe[g] || { nodes: [], edges: [] }, extra) };
      // a fresh Session 1 starts the story again: later beats' runs are from the old story
      const order = story!.beats.map((b) => b.id);
      const keep = Object.fromEntries(Object.entries(get().runs).filter(([k]) => order.indexOf(k) < order.indexOf(beatId)));
      const doneKeep = Object.fromEntries(Object.entries(get().done).filter(([k]) => order.indexOf(k) < order.indexOf(beatId)));
      set({
        runs: { ...keep, [beatId]: run }, done: doneKeep, universe, beat: beatId, loading: null, selected: null, tab: "step",
        showCompare: false, compare: null, player: playerReducer(get().player, { type: "load", total: run.steps.length, autoplay: true }),
      });
    } catch (e) {
      set({ loading: null });
      throw e;
    }
  },

  show: (beatId) => {
    const run = get().runs[beatId];
    if (!run) return;
    set({ beat: beatId, selected: null, tab: "step", showCompare: false,
      player: { ...playerReducer(get().player, { type: "load", total: run.steps.length }), idx: run.steps.length - 1 } });
  },

  dispatch: (a) => {
    const player = playerReducer(get().player, a);
    const { beat, runs } = get();
    const run = beat ? runs[beat] : null;
    const atEnd = !!run && player.total > 0 && player.idx === player.total - 1;
    const patch: Partial<StoryState> = { player };
    if (atEnd && beat && !get().done[beat]) {
      patch.done = { ...get().done, [beat]: true };
      if (run?.report) patch.tab = "report";
    }
    if (!atEnd && get().tab === "report" && a.type !== "tick") patch.tab = "step";
    set(patch);
    const last = get().story?.beats.at(-1)?.id; // the story ends on the before/after panel
    if (atEnd && beat === last && !get().compare) void get().loadCompare().then(() => set({ showCompare: true }));
  },

  select: (id) => set({ selected: id, tab: id ? "node" : "step" }),
  setTab: (tab) => set({ tab }),
  loadCompare: async () => set({ compare: await api.compare(get().tenant) }),
  setShowCompare: (showCompare) => set({ showCompare }),
  restart: () => set({ runs: {}, done: {}, beat: null, player: initialPlayer, compare: null, showCompare: false, selected: null, tab: "step" }),
}));

export const nodeIndex = (els: Elements | undefined) => new Map<string, NodeEl>((els?.nodes || []).map((n) => [n.id, n]));
