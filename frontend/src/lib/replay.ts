import { edgeKey, type StepEvent } from "./types";

// ───────────── player ─────────────
export type Player = { idx: number; playing: boolean; speed: number; total: number };
export type PlayerAction =
  | { type: "load"; total: number; autoplay?: boolean }
  | { type: "play" }
  | { type: "pause" }
  | { type: "toggle" }
  | { type: "step"; by: number }
  | { type: "seek"; idx: number }
  | { type: "speed"; speed: number }
  | { type: "tick" };

export const SPEEDS = [0.5, 1, 2];
export const initialPlayer: Player = { idx: -1, playing: false, speed: 1, total: 0 };
const clampIdx = (i: number, total: number) => Math.max(-1, Math.min(total - 1, i));

/** idx -1 = before the first step (only the alert and its neighbourhood are on screen). */
export function playerReducer(s: Player, a: PlayerAction): Player {
  switch (a.type) {
    case "load":
      return { ...s, total: a.total, idx: -1, playing: !!a.autoplay && a.total > 0 };
    case "play":
      return s.total === 0 ? s : { ...s, playing: true, idx: s.idx >= s.total - 1 ? -1 : s.idx };
    case "pause":
      return { ...s, playing: false };
    case "toggle":
      return playerReducer(s, { type: s.playing ? "pause" : "play" });
    case "step":
      return { ...s, playing: false, idx: clampIdx(s.idx + a.by, s.total) };
    case "seek":
      return { ...s, playing: false, idx: clampIdx(a.idx, s.total) };
    case "speed":
      return SPEEDS.includes(a.speed) ? { ...s, speed: a.speed } : s;
    case "tick": {
      if (!s.playing) return s;
      const idx = clampIdx(s.idx + 1, s.total);
      return { ...s, idx, playing: idx < s.total - 1 };
    }
  }
}

export const isLearned = (st: StepEvent) => st.writes.edges.some((e) => e.type === "DEPENDS_ON");

/** How long a step stays on screen at 1×. Deterministic, so a recording is identical every take. */
export function dwellMs(st: StepEvent | undefined, speed: number): number {
  const base = !st ? 1200 : isLearned(st) ? 3600 : st.action === "handoff" ? 2800 : st.action === "write" ? 2300 : st.action === "page" ? 2100 : 1800;
  return base / speed;
}

// ───────────── graph at step idx ─────────────
export type GraphState = {
  nodes: Set<string>;
  edges: Set<string>;
  current: { nodes: Set<string>; edges: Set<string> };
  written: Set<string>; // agent-written node ids + edge keys so far
  fresh: { nodes: Set<string>; edges: Set<string> }; // written at this very step (pulse)
  learned: Set<string>; // learned DEPENDS_ON edge keys so far
  justLearned: string[]; // learned at this step (the draw-in animation)
};

export type Carry = { nodes: Set<string>; edges: Set<string>; written: Set<string>; learned: Set<string> };

const empty = (): GraphState => ({
  nodes: new Set(), edges: new Set(), current: { nodes: new Set(), edges: new Set() }, written: new Set(),
  fresh: { nodes: new Set(), edges: new Set() }, learned: new Set(), justLearned: [],
});

/** Visible graph after step idx: base ∪ carry (a continued beat) ∪ every highlight of steps 0..idx. */
export function graphAt(steps: StepEvent[], idx: number, base: string[], carry?: Carry): GraphState {
  const g = empty();
  base.forEach((n) => g.nodes.add(n));
  if (carry) {
    carry.nodes.forEach((n) => g.nodes.add(n));
    carry.edges.forEach((e) => g.edges.add(e));
    carry.written.forEach((w) => g.written.add(w));
    carry.learned.forEach((l) => g.learned.add(l));
  }
  for (let i = 0; i <= idx && i < steps.length; i++) {
    const st = steps[i];
    const now = i === idx;
    st.highlight.nodes.forEach((n) => {
      g.nodes.add(n);
      if (now) g.current.nodes.add(n);
    });
    st.highlight.edges.forEach((e) => {
      const k = edgeKey(e);
      g.nodes.add(e.source);
      g.nodes.add(e.target);
      g.edges.add(k);
      if (now) g.current.edges.add(k);
    });
    st.writes.nodes.forEach((n) => {
      g.written.add(n.id);
      if (now) g.fresh.nodes.add(n.id);
    });
    st.writes.edges.forEach((e) => {
      const k = edgeKey(e);
      g.written.add(k);
      g.edges.add(k);
      if (now) g.fresh.edges.add(k);
      if (e.type === "DEPENDS_ON") {
        g.learned.add(k);
        if (now) g.justLearned.push(k);
      }
    });
  }
  return g;
}

export const carryOf = (g: GraphState): Carry => ({ nodes: g.nodes, edges: g.edges, written: g.written, learned: g.learned });

/** Investigator tool-call counter per agent: "tool call n" on each card. */
export function callNumbers(steps: StepEvent[]): number[] {
  const seen: Record<string, number> = {};
  return steps.map((s) => (seen[s.agent] = (seen[s.agent] || 0) + 1));
}
