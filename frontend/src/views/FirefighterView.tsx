import { ChevronLeft, ChevronRight, Flame, Loader2, Pause, Play, Siren } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { GraphCanvas } from "../components/GraphCanvas";
import { Empty, Skeleton } from "../components/ui";
import { dwellMs, graphAt, SPEEDS } from "../lib/replay";
import { useApp } from "../lib/store";
import { edgeKey, type Elements, type StepEvent } from "../lib/types";
import { useFF, type FFTab } from "./ff/store";
import { Actions, Board, FFReport } from "./ff/Panels";
import { NodePane, StepPane } from "./story/Drawer";
import { oneLine } from "./story/Timeline";

const short = (id: string) => id.split(":").pop() || id;

export default function FirefighterView() {
  const { tenant, unlocked, meta, toast } = useApp();
  const s = useFF();
  const fresh = unlocked && !!meta?.code_configured;
  const run = s.run;
  const idx = s.player.idx;

  useEffect(() => {
    void s.init(tenant).then(() => {
      const want = new URLSearchParams(location.search).get("scenario");
      const st = useFF.getState();
      if (want && st.scenarios.some((x) => x.id === want) && !st.run) void st.pick(want, false).catch((e) => toast(e.message, "error"));
    });
  }, [tenant]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!s.player.playing || !run) return;
    const t = setTimeout(() => s.dispatch({ type: "tick" }), dwellMs(run.steps[idx + 1], s.player.speed) * 0.8);
    return () => clearTimeout(t);
  }, [s.player.playing, idx, s.player.speed, run]); // eslint-disable-line react-hooks/exhaustive-deps

  const alerts = run?.alerts.map((a) => a.service_id) || [];
  const rootAll = (run?.report?.incidents || []).map((i: any) => i.root?.service_id).find(Boolean) as string | undefined;
  const universe: Elements | undefined = useMemo(() => s.graph ? {
    nodes: s.graph.nodes.map((n) => (n.id === rootAll ? { ...n, name: `ROOT · ${n.name}` } : n)), edges: s.graph.edges } : undefined,
  [s.graph, rootAll]);
  useEffect(() => {
    document.querySelector('[data-testid="ff-timeline"] [aria-current="step"]')?.scrollIntoView({ block: "nearest" });
  }, [idx]);
  const g = useMemo(() => {
    if (!run || !s.graph) return null;
    const st = graphAt(run.steps, idx, s.graph.base);
    if (idx === run.steps.length - 1 && run.report) {  // the end: frame what was decided (causes, paths, roots, alerts)
      const incs: any[] = run.report.incidents || [run.report];
      const nodes = new Set<string>(alerts);
      incs.forEach((i) => {
        (i.likely_cause?.path || []).forEach((x: string) => nodes.add(x));
        if (i.likely_cause?.deploy_id) nodes.add(i.likely_cause.deploy_id);
        if (i.root?.service_id) nodes.add(i.root.service_id);
        if (i.contact?.person_id) nodes.add(i.contact.person_id);
      });
      const edges = new Set([...st.edges].filter((k) => { const [a, , b] = k.split("|"); return nodes.has(a) && nodes.has(b); }));
      return { ...st, current: { nodes, edges } };
    }
    return st;
  }, [run, s.graph, idx]); // eslint-disable-line react-hooks/exhaustive-deps
  // the storm's shared root is ringed once correlation has named it
  const corrIdx = run ? run.steps.findIndex((st) => st.tool === "correlate_alerts") : -1;
  const roots = (run?.report?.incidents || []).map((i: any) => i.root?.service_id).filter(Boolean);
  const rootId = corrIdx >= 0 && idx >= corrIdx ? roots[0] || null : null;
  const atEnd = !!run && idx === run.steps.length - 1;
  const steps = run?.steps || [];
  const board = useMemo(() => latestBoard(steps, idx, run?.report, atEnd), [steps, idx, run, atEnd]);
  const pick = (id: string, asFresh: boolean) => void s.pick(id, asFresh).catch((e) => toast(`Couldn't start: ${e.message}`, "error"));

  if (s.error) return <Empty title="The Firefighter didn't load">{s.error}</Empty>;
  const sc = s.scenarios.find((x) => x.id === s.sel);
  const tabs: { id: FFTab; label: string; show: boolean }[] = [
    { id: "step", label: "Receipt", show: true },
    { id: "board", label: "Hypotheses", show: !!board },
    { id: "actions", label: "Actions", show: atEnd && !!run?.report?.action_plan?.length },
    { id: "report", label: "Report", show: atEnd && !!run?.report },
    { id: "node", label: "Node", show: !!s.selected },
  ];
  return (
    <div className="grid h-full min-h-0 grid-cols-1 lg:grid-cols-[320px_minmax(0,1fr)_440px]">
      <aside className="order-2 flex min-h-0 flex-col border-border bg-surface lg:order-1 lg:border-r">
        <div className={`scroll-thin overflow-y-auto border-b-2 border-border p-3 shadow-sm ${run ? "max-h-[32%]" : "max-h-[60%]"}`} data-testid="scenarios">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">Scenarios {fresh ? "(fresh mock runs)" : "(recorded)"}</p>
          {!s.scenarios.length ? <Skeleton className="mt-2 h-40" /> : (
            <ul className="mt-2 space-y-1.5">
              {s.scenarios.map((x) => (
                <li key={x.id}>
                  <button onClick={() => pick(x.id, fresh)} disabled={s.loading} aria-current={s.sel === x.id ? "true" : undefined}
                    data-testid={`scenario-${x.id}`}
                    className={`w-full rounded-lg border p-2 text-left text-[12.5px] leading-snug disabled:opacity-60 ${s.sel === x.id ? "border-accent bg-accent-soft" : "border-border hover:bg-surface-2"}`}>
                    <span className="flex items-center gap-1.5 font-medium">
                      {x.alerts.length > 2 ? <Flame size={13} className="text-alert" /> : <Siren size={13} className="text-alert" />}
                      {x.shape}
                      {s.loading && s.sel === x.id && <Loader2 size={13} className="ml-auto animate-spin" />}
                    </span>
                    <span className="mt-0.5 block text-[11.5px] text-muted">{x.alerts.length} alert{x.alerts.length > 1 ? "s" : ""}: {x.alerts.map((a) => short(a.service_id)).join(", ")}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {fresh && <CustomAlert />}
        </div>
        <ol className="scroll-thin min-h-0 flex-1 space-y-1.5 overflow-y-auto p-3" aria-label="Firefighter steps" data-testid="ff-timeline">
          {!run && <li className="text-sm text-muted">Pick a scenario: the Firefighter lists every recent change as a lead, checks each one against the dependency graph, and proposes what to do.</li>}
          {steps.slice(0, idx + 1).map((st, i) => (
            <li key={st.seq} className="fade-in">
              <button onClick={() => s.dispatch({ type: "seek", idx: i })} aria-current={i === idx ? "step" : undefined} data-testid="ff-step"
                className={`w-full rounded-lg border p-2 text-left ${i === idx ? "border-accent bg-accent-soft ring-1 ring-accent" : "border-border hover:bg-surface-2"}`}>
                <span className="flex items-center gap-2"><span className="truncate font-mono text-[12px] font-medium">{st.tool}</span>
                  <span className="ml-auto shrink-0 text-[11px] text-muted">{i + 1}</span></span>
                {st.why && <span className="mt-0.5 block text-[11.5px] italic leading-snug text-accent">why: {st.why}</span>}
                <span className="mt-0.5 line-clamp-2 block text-[12px] leading-snug text-muted">{oneLine(st)}</span>
              </button>
            </li>
          ))}
        </ol>
      </aside>

      <section className="relative order-1 flex min-h-[62vh] flex-col lg:order-2 lg:min-h-0" aria-label="Firefighter run">
        <div className="relative min-h-0 flex-1">
          {universe && g && (
            <GraphCanvas elements={universe} layoutKey={`ff:${run?.runId}`} visible={g.nodes} visibleEdges={withAlertEdges(g.edges, s.graph!.edges, alerts)}
              current={g.current} fresh={g.fresh} justLearned={g.justLearned} alertIds={alerts} rootId={rootId}
              selected={s.selected} onSelect={s.select} ariaLabel="The Firefighter's graph: alerting services in red, the current step in blue" />
          )}
          {!run && !s.loading && <Empty title="No run yet">Choose a scenario on the left. {fresh ? "With the access code each one runs fresh (mock, free) on a copy of the company." : "Visitors watch a recording; enter the access code for fresh runs."}</Empty>}
          {s.loading && !run && <div className="grid h-full place-items-center"><Loader2 className="animate-spin text-muted" /></div>}
          {run && (
            <div className="pointer-events-none absolute left-3 top-3 max-w-[70%] space-y-1.5">
              <p className="rounded-md bg-surface/95 px-3 py-2 text-[13px] shadow-sm ring-1 ring-border" data-testid="ff-caption">
                <b className="text-alert">{alerts.length} alert{alerts.length > 1 ? "s" : ""}</b>{sc ? ` · ${sc.shape}` : " · your alert"}
                <span className="ml-2 text-[11px] uppercase tracking-wide text-muted">{run.mode === "replay" ? "recorded run" : `fresh ${run.mode} run`}
                  {" · mock planner (scripted, no LLM)"}</span>
                {run.toolsVia?.transport === "mcp" && (
                  <span className="mt-0.5 block text-[12px] text-accent" data-testid="via-mcp">
                    Tools selected through MCP: {run.toolsVia.tools_listed} tools listed by the MCP server, {run.toolsVia.mcp_calls} tools/call requests
                  </span>
                )}
              </p>
              {atEnd && <Outcome report={run.report} alerts={alerts.length} />}
            </div>
          )}
        </div>
        <Controls disabled={!run} />
      </section>

      <aside className="order-3 flex min-h-[40vh] flex-col border-border bg-surface lg:min-h-0 lg:border-l">
        <div role="tablist" className="flex gap-1 border-b border-border px-3 pt-2">
          {tabs.filter((t) => t.show).map((t) => (
            <button key={t.id} role="tab" aria-selected={s.tab === t.id} onClick={() => s.setTab(t.id)} data-testid={`tab-${t.id}`}
              className={`-mb-px border-b-2 px-2.5 py-1.5 text-sm ${s.tab === t.id ? "border-accent font-medium" : "border-transparent text-muted hover:text-text"}`}>
              {t.label}
            </button>
          ))}
        </div>
        <div className="scroll-thin min-h-0 flex-1 overflow-y-auto p-4" data-testid="ff-drawer">
          {s.tab === "node" && s.selected ? <NodePane id={s.selected} universe={universe} tenant={tenant} onOpen={s.select} />
            : s.tab === "board" && board ? <Board hypotheses={board.hypotheses} breakdown={board.breakdown} onOpen={s.select} />
            : s.tab === "actions" && run?.report ? (
              <Actions plan={run.report.action_plan || []} execution={run.execution} canApprove={fresh && run.mode !== "replay"} approving={s.approving}
                onApprove={(ids) => void s.approve(ids).catch((e) => toast(`Approval failed: ${e.message}`, "error"))} onOpen={s.select}
                incidents={(run.report.incidents || [0]).length} />)
            : s.tab === "report" && run?.report ? <FFReport r={run.report} onOpen={s.select} />
            : run && idx >= 0 ? <StepPane step={steps[idx]} n={idx + 1} onOpen={s.select} />
            : <Empty title="Every step is a receipt">The exact Cypher each tool ran, why the agent chose it, and what came back.</Empty>}
        </div>
      </aside>
    </div>
  );
}

/** Hypotheses so far: the last submitted board (end of run), or none mid-run. */
function latestBoard(steps: StepEvent[], idx: number, report: any, atEnd: boolean) {
  if (atEnd && report?.hypotheses) return { hypotheses: report.hypotheses, breakdown: report.confidence_breakdown };
  for (let i = Math.min(idx, steps.length - 1); i >= 0; i--) {
    const h = (steps[i].args as any)?.hypotheses || (steps[i].args as any)?.details?.hypotheses;
    if (h) return { hypotheses: h, breakdown: (steps[i].args as any)?.confidence_breakdown };
  }
  return null;
}

function withAlertEdges(edges: Set<string>, all: { source: string; target: string; type: string }[], alerts: string[]) {
  const out = new Set(edges);
  all.forEach((e) => alerts.includes(e.source) && alerts.includes(e.target) && out.add(edgeKey(e as any)));
  return out;
}

/** The headline at the end of a run: alerts → incidents, pages sent vs suppressed. */
function Outcome({ report, alerts }: { report: any; alerts: number }) {
  if (!report) return null;
  const incs = report.incidents || [report];
  const pages = incs.filter((i: any) => i.contact?.person_id || i.contact?.team_id).length;
  const supp = (report.suppressed_pages || []).length;
  return (
    <p className="rounded-md bg-surface/95 px-3 py-2 text-[15px] font-semibold shadow-sm ring-1 ring-accent" data-testid="outcome">
      {alerts} alert{alerts > 1 ? "s" : ""} → {incs.length} incident{incs.length > 1 ? "s" : ""} · {pages} page{pages !== 1 ? "s" : ""}
      {supp > 0 && <span className="text-muted"> · {supp} suppressed</span>}
    </p>
  );
}

function Controls({ disabled }: { disabled: boolean }) {
  const { player, dispatch } = useFF();
  const btn = "grid h-8 w-8 place-items-center rounded-md text-text hover:bg-surface-2 disabled:opacity-40";
  return (
    <div className="flex flex-wrap items-center gap-2 border-t border-border bg-surface px-3 py-2" aria-label="Playback">
      <button className={btn} disabled={disabled} onClick={() => dispatch({ type: "step", by: -1 })} aria-label="Step back"><ChevronLeft size={18} /></button>
      <button className={`${btn} bg-surface-2`} disabled={disabled} onClick={() => dispatch({ type: "toggle" })} aria-label={player.playing ? "Pause" : "Play"} data-testid="ff-play">
        {player.playing ? <Pause size={17} /> : <Play size={17} />}
      </button>
      <button className={btn} disabled={disabled} onClick={() => dispatch({ type: "step", by: 1 })} aria-label="Step forward"><ChevronRight size={18} /></button>
      <input type="range" min={-1} max={Math.max(-1, player.total - 1)} value={player.idx} disabled={disabled} aria-label="Scrub through the steps"
        onChange={(e) => dispatch({ type: "seek", idx: Number(e.target.value) })} className="min-w-24 flex-1 accent-[var(--accent)]" data-testid="ff-scrubber" />
      <span className="w-20 text-right text-xs tabular-nums text-muted">{player.total ? `step ${player.idx + 1} / ${player.total}` : "no run yet"}</span>
      <div className="flex rounded-md bg-surface-2 p-0.5" role="group" aria-label="Playback speed">
        {SPEEDS.map((sp) => (
          <button key={sp} onClick={() => dispatch({ type: "speed", speed: sp })} aria-pressed={player.speed === sp}
            className={`rounded px-2 py-0.5 text-xs ${player.speed === sp ? "bg-surface font-semibold shadow-sm" : "text-muted"}`}>{sp}×</button>
        ))}
      </div>
    </div>
  );
}

function CustomAlert() {
  const { services, runCustom, loading } = useFF();
  const toast = useApp((x) => x.toast);
  const [svc, setSvc] = useState("");
  const [symptom, setSymptom] = useState("5xx rate 8% and p99 3s for the last 10 minutes");
  return (
    <form className="mt-3 space-y-1.5 border-t border-border pt-3" onSubmit={(e) => {
      e.preventDefault();
      if (svc) void runCustom([{ service_id: svc, symptom }]).catch((err) => toast(err.message, "error"));
    }}>
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">Or your own alert</p>
      <select value={svc} onChange={(e) => setSvc(e.target.value)} aria-label="Alerting service"
        className="w-full rounded-md border border-border bg-surface px-2 py-1 text-[13px]">
        <option value="">Pick a service…</option>
        {services.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
      </select>
      <input value={symptom} onChange={(e) => setSymptom(e.target.value)} aria-label="Symptom" maxLength={300}
        className="w-full rounded-md border border-border bg-surface px-2 py-1 text-[13px]" />
      <button disabled={!svc || loading} className="rounded-md bg-accent px-2.5 py-1 text-[13px] font-medium text-white disabled:opacity-50">Run (mock)</button>
    </form>
  );
}
