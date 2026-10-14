import { Check, ChevronLeft, ChevronRight, Loader2, Pause, Play, RotateCcw, Siren, Table2 } from "lucide-react";
import { useEffect, useMemo } from "react";
import { GraphCanvas } from "../components/GraphCanvas";
import { Empty, Skeleton } from "../components/ui";
import { carryOf, dwellMs, graphAt, SPEEDS, type Carry } from "../lib/replay";
import { useApp } from "../lib/store";
import { edgeKey, type Beat } from "../lib/types";
import { ComparePanel } from "./story/ComparePanel";
import { Drawer } from "./story/Drawer";
import { groupOf, useStory } from "./story/store";
import { Timeline } from "./story/Timeline";

export function StoryView() {
  const { tenant, unlocked, meta, toast } = useApp();
  const s = useStory();
  const fresh = unlocked && !!meta?.code_configured;

  useEffect(() => void s.init(tenant), [tenant]); // eslint-disable-line react-hooks/exhaustive-deps

  const beats = s.story?.beats || [];
  const beat = beats.find((b) => b.id === s.beat) || null;
  const shown = beat || beats[0] || null; // before anything is fired, show the first alert's neighbourhood
  const run = beat ? s.runs[beat.id] || null : null;
  const idx = s.player.idx;
  const group = shown ? groupOf(shown) : "";
  const universe = s.universe[group];
  const alertOf = (b: Beat | null): string | null =>
    !b ? null : b.alert?.service_id || (b.continues ? alertOf(beats.find((x) => x.id === b.continues) || null) : null);
  const alertId = alertOf(shown);

  const g = useMemo(() => {
    if (!shown) return null;
    const rg = s.runGraphs[shown.id];
    const base = rg?.base || [];
    let carry: Carry | undefined;
    const prev = shown.continues ? s.runs[shown.continues] : undefined;
    if (prev) carry = carryOf(graphAt(prev.steps, prev.steps.length - 1, s.runGraphs[shown.continues!]?.base || []));
    const state = graphAt(run?.steps || [], run ? idx : -1, base, carry);
    const edges = new Set(state.edges);
    (rg?.edges || []).forEach((e) => {
      if ((e.source === alertId || e.target === alertId) && base.includes(e.source) && base.includes(e.target)) edges.add(edgeKey(e));
    });
    return { ...state, edges };
  }, [shown, run, idx, s.runGraphs, s.runs, alertId]);

  // deterministic autoplay
  useEffect(() => {
    if (!s.player.playing || !run) return;
    const t = setTimeout(() => s.dispatch({ type: "tick" }), dwellMs(run.steps[idx + 1], s.player.speed));
    return () => clearTimeout(t);
  }, [s.player.playing, idx, s.player.speed, run]); // eslint-disable-line react-hooks/exhaustive-deps

  // keyboard: space, ← →
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.closest("input, textarea, select, dialog, [contenteditable]") || e.metaKey || e.ctrlKey || e.altKey || !run) return;
      if (e.key === " ") {
        if (t.tagName === "BUTTON") t.blur();
        e.preventDefault();
        s.dispatch({ type: "toggle" });
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        s.dispatch({ type: "step", by: 1 });
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        s.dispatch({ type: "step", by: -1 });
      }
    };
    addEventListener("keydown", on);
    return () => removeEventListener("keydown", on);
  }, [run]); // eslint-disable-line react-hooks/exhaustive-deps

  const fire = (id: string) => {
    const go = () =>
      s.fire(id, fresh).catch((e) => toast(`Couldn't start “${beats.find((b) => b.id === id)?.label}”: ${e.message}`, "error", go));
    void go();
  };

  if (s.error) return <Empty title="The story didn't load">{s.error} <button className="text-accent underline" onClick={() => (useStory.setState({ tenant: "" }), s.init(tenant))}>Retry</button></Empty>;
  if (!s.story) {
    return (
      <div className="grid h-full grid-cols-1 gap-3 p-3 lg:grid-cols-[300px_1fr_400px]">
        <Skeleton className="min-h-40" /><Skeleton className="min-h-80" /><Skeleton className="min-h-40" />
      </div>
    );
  }
  if (!s.story.has_story) {
    return (
      <Empty title={`${s.story.name} has no scripted story`}>
        The demo story runs on the first company. Here you can still explore this company's graph and ask its Brain; it has
        its own memory, separate from every other company.
      </Empty>
    );
  }

  const enabled = (i: number) => i === 0 || !!s.done[beats[i - 1].id];
  const last = beats.at(-1)!;
  return (
    <div className="grid h-full min-h-0 grid-cols-1 lg:grid-cols-[300px_minmax(0,1fr)_400px]">
      <aside className="order-2 max-h-[38vh] min-h-0 border-border bg-surface lg:order-1 lg:max-h-none lg:border-r">
        <Timeline run={run} beat={beat} idx={idx} onSeek={(i) => s.dispatch({ type: "seek", idx: i })} />
      </aside>

      <section className="relative order-1 flex min-h-[62vh] flex-col lg:order-2 lg:min-h-0" aria-label="Story">
        <div className="flex flex-wrap items-center gap-1.5 border-b border-border bg-surface px-3 py-2" role="toolbar" aria-label="Story steps">
          {beats.map((b, i) => {
            const cur = s.beat === b.id;
            const isDone = !!s.done[b.id];
            return (
              <button key={b.id} disabled={!enabled(i) || !!s.loading} data-testid={`beat-${b.id}`}
                onClick={() => (s.runs[b.id] && isDone && !cur ? s.show(b.id) : fire(b.id))}
                className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[13px] font-medium ring-1 disabled:opacity-40 ${
                  cur ? "bg-text text-bg ring-text" : isDone ? "bg-surface-2 ring-border" : enabled(i) ? "bg-accent text-white ring-accent" : "bg-surface ring-border"}`}>
                {s.loading === b.id ? <Loader2 size={14} className="animate-spin" /> : isDone ? <Check size={14} /> : i === 0 ? <Siren size={14} /> : null}
                {b.label}
              </button>
            );
          })}
          {s.compare && (
            <button onClick={() => s.setShowCompare(!s.showCompare)} data-testid="show-compare"
              className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[13px] font-medium ring-1 ring-border hover:bg-surface-2">
              <Table2 size={14} /> Before / after
            </button>
          )}
          {s.beat && (
            <button onClick={s.restart} className="ml-auto flex items-center gap-1 rounded-md px-2 py-1 text-sm text-muted hover:text-text" aria-label="Restart the story">
              <RotateCcw size={14} /> <span className="hidden 2xl:inline">Restart</span>
            </button>
          )}
        </div>

        <div className="relative min-h-0 flex-1">
          {universe && g && (
            <GraphCanvas elements={universe} layoutKey={`${tenant}:${group}`} visible={g.nodes} visibleEdges={g.edges}
              current={g.current} fresh={g.fresh} justLearned={g.justLearned} alertId={alertId} selected={s.selected}
              onSelect={s.select} ariaLabel="Incident graph: the alerting service and every node the agents touched" />
          )}
          {!beat && (
            <div className="card fade-in absolute left-3 top-3 max-w-md p-4" data-testid="intro">
              <p className="text-xs font-semibold uppercase tracking-wide text-alert">Alert · {s.story.name}</p>
              <p className="mt-1 font-medium">{beats[0].alert?.symptom}</p>
              <p className="mt-2 text-[13px] text-muted">{s.story.intro}</p>
              <p className="mt-2 text-[12px] text-muted">{fresh ? "Fresh mock runs: they write to the graph." : "Recorded runs (replay). Enter the access code for fresh runs."}</p>
            </div>
          )}
          {beat && (
            <p className="pointer-events-none absolute left-3 top-3 max-w-[60%] rounded-md bg-surface/90 px-2.5 py-1.5 text-[12.5px] shadow-sm ring-1 ring-border">
              <b>{beat.title}.</b> {beat.caption}
            </p>
          )}
          <Legend />
          {s.showCompare && s.compare && (
            <div className="absolute inset-0 z-10 grid place-items-center bg-bg/70 p-3 backdrop-blur-[2px]">
              <div className="max-h-full w-full max-w-4xl"><ComparePanel c={s.compare} onClose={() => s.setShowCompare(false)} /></div>
            </div>
          )}
        </div>

        <Controls disabled={!run} />
        {beat?.id === last.id && s.done[last.id] && !s.compare && <p className="sr-only">Loading the before/after numbers…</p>}
      </section>

      <aside className="order-3 min-h-[40vh] border-border bg-surface lg:min-h-0 lg:border-l">
        <Drawer run={run} idx={idx} tab={s.tab} setTab={s.setTab} selected={s.selected} universe={universe} tenant={tenant}
          onOpen={(id) => s.select(id)} beatKind={beat?.kind} />
      </aside>
    </div>
  );
}

function Controls({ disabled }: { disabled: boolean }) {
  const { player, dispatch } = useStory();
  const btn = "grid h-8 w-8 place-items-center rounded-md text-text hover:bg-surface-2 disabled:opacity-40";
  return (
    <div className="flex flex-wrap items-center gap-2 border-t border-border bg-surface px-3 py-2" aria-label="Playback">
      <button className={btn} disabled={disabled} onClick={() => dispatch({ type: "step", by: -1 })} aria-label="Step back (←)"><ChevronLeft size={18} /></button>
      <button className={`${btn} bg-surface-2`} disabled={disabled} onClick={() => dispatch({ type: "toggle" })} aria-label={player.playing ? "Pause (space)" : "Play (space)"} data-testid="play">
        {player.playing ? <Pause size={17} /> : <Play size={17} />}
      </button>
      <button className={btn} disabled={disabled} onClick={() => dispatch({ type: "step", by: 1 })} aria-label="Step forward (→)"><ChevronRight size={18} /></button>
      <input type="range" min={-1} max={Math.max(-1, player.total - 1)} value={player.idx} disabled={disabled} aria-label="Scrub through the steps"
        onChange={(e) => dispatch({ type: "seek", idx: Number(e.target.value) })} className="min-w-24 flex-1 accent-[var(--accent)]" data-testid="scrubber" />
      <span className="w-20 text-right text-xs tabular-nums text-muted" data-testid="step-count">
        {player.total ? `step ${player.idx + 1} / ${player.total}` : "no run yet"}
      </span>
      <div className="flex rounded-md bg-surface-2 p-0.5" role="group" aria-label="Playback speed">
        {SPEEDS.map((sp) => (
          <button key={sp} onClick={() => dispatch({ type: "speed", speed: sp })} aria-pressed={player.speed === sp}
            className={`rounded px-2 py-0.5 text-xs ${player.speed === sp ? "bg-surface font-semibold shadow-sm" : "text-muted"}`}>
            {sp}×
          </button>
        ))}
      </div>
    </div>
  );
}

function Legend() {
  const item = "flex items-center gap-1.5";
  return (
    <div className="pointer-events-none absolute bottom-2 left-2 flex flex-wrap gap-x-3 gap-y-1 rounded-md bg-surface/90 px-2.5 py-1.5 text-[11.5px] text-muted shadow-sm ring-1 ring-border" aria-label="Legend">
      <span className={item}><span className="h-3 w-3 rounded-sm border-2 border-alert bg-alert-soft" /> alerting service</span>
      <span className={item}><span className="h-1 w-5 rounded bg-accent" /> current step's path</span>
      <span className={item}><span className="h-3 w-3 rounded-sm border-[3px] border-double border-mem bg-mem-fill" /> AI · written by an agent</span>
      <span className={item}><svg width="22" height="6" aria-hidden="true"><line x1="0" y1="3" x2="22" y2="3" stroke="var(--mem-stroke)" strokeWidth="2.5" strokeDasharray="5 3" /></svg> learned dependency</span>
    </div>
  );
}
