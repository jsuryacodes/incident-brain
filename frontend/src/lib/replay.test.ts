import { describe, expect, it } from "vitest";
import { callNumbers, carryOf, dwellMs, graphAt, initialPlayer, playerReducer, type Player } from "./replay";
import type { StepEvent } from "./types";

const step = (seq: number, agent: string, o: Partial<StepEvent> = {}): StepEvent => ({
  seq, agent, action: "tool_call", tool: "t", summary: "", args: {}, cypher: "", params: [], queries: [], result_preview: null,
  highlight: { nodes: [], edges: [] }, cited: [], writes: { nodes: [], edges: [] }, elements: { nodes: [], edges: [] }, mode: "replay", ...o,
});
const learned = { source: "svc:a", target: "svc:b", type: "DEPENDS_ON", origin: "agent", props: { source: "learned" } };
const steps: StepEvent[] = [
  step(1, "triage", { highlight: { nodes: ["svc:x"], edges: [] } }),
  step(2, "triage", { action: "write", highlight: { nodes: ["inc:1", "svc:x"], edges: [{ source: "inc:1", target: "svc:x", type: "AFFECTED" }] },
    writes: { nodes: [{ id: "inc:1", label: "Incident", name: "INC-1", origin: "agent", props: {} }], edges: [] } }),
  step(3, "investigator", { highlight: { nodes: ["svc:x", "svc:a"], edges: [{ source: "svc:x", target: "svc:a", type: "DEPENDS_ON" }] } }),
  step(4, "investigator", { action: "write", highlight: { nodes: ["svc:a", "svc:b"], edges: [learned] }, writes: { nodes: [], edges: [learned] } }),
];

describe("player reducer", () => {
  const loaded = playerReducer(initialPlayer, { type: "load", total: 4, autoplay: true });

  it("loads before the first step and autoplays", () => {
    expect(loaded).toEqual({ idx: -1, playing: true, speed: 1, total: 4 });
  });

  it("ticks to the end and stops there", () => {
    let s: Player = loaded;
    for (let i = 0; i < 10; i++) s = playerReducer(s, { type: "tick" });
    expect(s.idx).toBe(3);
    expect(s.playing).toBe(false);
  });

  it("steps and seeks within bounds and pauses", () => {
    expect(playerReducer(loaded, { type: "step", by: -1 })).toMatchObject({ idx: -1, playing: false });
    expect(playerReducer(loaded, { type: "seek", idx: 99 }).idx).toBe(3);
    expect(playerReducer({ ...loaded, idx: 1 }, { type: "step", by: 1 }).idx).toBe(2);
  });

  it("play at the end restarts from the beginning", () => {
    expect(playerReducer({ ...loaded, idx: 3, playing: false }, { type: "play" })).toMatchObject({ idx: -1, playing: true });
  });

  it("only accepts the offered speeds; a tick while paused does nothing", () => {
    expect(playerReducer(loaded, { type: "speed", speed: 2 }).speed).toBe(2);
    expect(playerReducer(loaded, { type: "speed", speed: 3 }).speed).toBe(1);
    const paused = { ...loaded, playing: false, idx: 1 };
    expect(playerReducer(paused, { type: "tick" })).toBe(paused);
  });

  it("dwell is deterministic, longest on the learned edge, scaled by speed", () => {
    expect(dwellMs(steps[3], 1)).toBeGreaterThan(dwellMs(steps[1], 1));
    expect(dwellMs(steps[0], 2)).toBe(dwellMs(steps[0], 1) / 2);
  });
});

describe("graphAt", () => {
  it("shows only the base before the first step", () => {
    const g = graphAt(steps, -1, ["svc:x", "svc:y"]);
    expect([...g.nodes]).toEqual(["svc:x", "svc:y"]);
    expect(g.current.nodes.size).toBe(0);
  });

  it("grows step by step; the current step is the path", () => {
    const g = graphAt(steps, 2, ["svc:x"]);
    expect(g.nodes).toEqual(new Set(["svc:x", "inc:1", "svc:a"]));
    expect(g.current.nodes).toEqual(new Set(["svc:x", "svc:a"]));
    expect(g.current.edges).toEqual(new Set(["svc:x|DEPENDS_ON|svc:a"]));
    expect(g.written).toEqual(new Set(["inc:1"]));
    expect(g.fresh.nodes.size).toBe(0);
  });

  it("marks writes as fresh only on their own step and flags the learned edge", () => {
    expect(graphAt(steps, 1, []).fresh.nodes).toEqual(new Set(["inc:1"]));
    const g = graphAt(steps, 3, []);
    expect(g.justLearned).toEqual(["svc:a|DEPENDS_ON|svc:b"]);
    expect(g.learned.has("svc:a|DEPENDS_ON|svc:b")).toBe(true);
    expect(g.nodes.has("svc:b")).toBe(true);
  });

  it("scrubbing back removes what came later", () => {
    const g = graphAt(steps, 1, []);
    expect(g.nodes.has("svc:b")).toBe(false);
    expect(g.learned.size).toBe(0);
  });

  it("a continued beat starts from the earlier beat's end state", () => {
    const end = carryOf(graphAt(steps, 3, ["svc:x"]));
    const next = graphAt([step(1, "communicator", { highlight: { nodes: ["res:1"], edges: [] } })], -1, [], end);
    expect(next.nodes.has("svc:b") && next.learned.size === 1).toBe(true);
    expect(next.justLearned).toEqual([]);
  });

  it("numbers tool calls per agent", () => {
    expect(callNumbers(steps)).toEqual([1, 2, 1, 2]);
  });
});
