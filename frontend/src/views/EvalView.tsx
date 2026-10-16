import { CheckCircle2, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/store";
import { Empty, Skeleton } from "../components/ui";

type Totals = Record<string, number>;
const METRICS: { key: string; label: string; of?: string; better: "high" | "low" }[] = [
  { key: "cause_correct", label: "Causes right", of: "incidents_expected", better: "high" },
  { key: "false_leads_rejected", label: "False leads rejected", of: "false_leads", better: "high" },
  { key: "paged_right", label: "Right person paged", of: "incidents_expected", better: "high" },
  { key: "wrong_actions", label: "Wrong actions", better: "low" },
];
const SET_NAMES: Record<string, string> = { dev: "Scenario library", generated: "50 generated", holdout: "Held-out (run once)" };

export default function EvalView() {
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [bench, setBench] = useState<any>(null);
  useEffect(() => void api.benchmarks().then(setBench, () => setBench(null)), []);
  const setView = useApp((x) => x.setView);
  useEffect(() => void api.evalLatest().then(setRes, (e) => setErr(e.message)), []);
  if (err) return <Empty title="No eval results yet">{err}</Empty>;
  if (!res) return <div className="p-6"><Skeleton className="h-96" /></div>;
  const profiles: string[] = Object.keys(res.profiles);
  const sets: string[] = Object.keys(res.totals);
  const dev = res.totals.dev || {};
  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl space-y-6 p-4 lg:p-6">
        <header>
          <h1 className="text-xl font-semibold">Firefighter eval: does the graph make the decisions better?</h1>
          <p className="mt-1 max-w-3xl text-[13.5px] text-muted">The same planner, loop, report format and grounding checks, with three tool sets. Every scenario is a
            fixture on a fresh copy of the company; every expected answer is re-derived by an independent oracle (plain Python, no Cypher).
            Mock mode (deterministic planner), {res.generated_at}.</p>
        </header>

        <section id="why" className="rounded-xl border border-border bg-surface p-4" data-testid="why-graph">
          <h2 className="text-base font-semibold">Why a graph?</h2>
          <p className="mt-0.5 text-[13px] text-muted">Hand-written scenarios (incl. alert storms and the memory ablation). Bars: share of the best possible.</p>
          <div className="mt-3 grid gap-4 md:grid-cols-4">
            {METRICS.map((m) => (
              <div key={m.key}>
                <p className="text-[12px] font-semibold uppercase tracking-wide text-muted">{m.label}</p>
                <ul className="mt-1.5 space-y-1.5">
                  {profiles.map((p) => {
                    const t: Totals = dev[p] || {};
                    const v = t[m.key] ?? 0;
                    const max = m.of ? t[m.of] || 1 : Math.max(1, ...profiles.map((q) => (dev[q] || {})[m.key] || 0));
                    const pct = Math.round((v / max) * 100);
                    return (
                      <li key={p} className="text-[12.5px]">
                        <div className="flex justify-between"><span>{res.profiles[p].title}</span><b className="tabular-nums">{v}{m.of ? `/${t[m.of]}` : ""}</b></div>
                        <div className="mt-0.5 h-2 rounded bg-surface-2">
                          <div className={`h-2 rounded ${m.better === "low" ? (v ? "bg-alert" : "bg-ok") : p === "full" ? "bg-accent" : "bg-muted"}`}
                            style={{ width: `${m.better === "low" ? (v ? Math.max(6, pct) : 0) : pct}%` }} />
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
          <p className="mt-3 text-[12.5px] text-muted">{profiles.map((p) => <span key={p} className="mr-3"><b>{res.profiles[p].title}:</b> {res.profiles[p].about}.</span>)}</p>
        </section>

        <section className="overflow-x-auto rounded-xl border border-border bg-surface" data-testid="scoreboard">
          <table className="w-full text-[13px]">
            <thead className="bg-surface-2 text-left text-[12px] text-muted">
              <tr><th className="p-2">Set</th>{profiles.map((p) => <th key={p} className="p-2">{res.profiles[p].title}</th>)}</tr>
            </thead>
            <tbody>
              {sets.map((k) => (
                <tr key={k} className="border-t border-border">
                  <td className="p-2 font-medium">{SET_NAMES[k] || k}</td>
                  {profiles.map((p) => {
                    const t: Totals = res.totals[k][p];
                    return <td key={p} className="p-2"><b className="text-[15px]">{t.passed}/{t.scenarios}</b> passed · causes {t.cause_correct}/{t.incidents_expected} · {t.wrong_actions} wrong actions</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="overflow-x-auto rounded-xl border border-border bg-surface">
          <table className="w-full text-[12.5px]">
            <thead className="bg-surface-2 text-left text-[12px] text-muted">
              <tr><th className="p-2">Scenario</th><th className="p-2">Shape</th>{profiles.map((p) => <th key={p} className="p-2">{res.profiles[p].title}</th>)}</tr>
            </thead>
            <tbody>
              {res.scenarios.filter((s: any) => s.set !== "generated").map((s: any) => (
                <tr key={s.id} className="border-t border-border align-top">
                  <td className="p-2 font-mono">
                    <button className="text-accent underline-offset-2 hover:underline" title="Watch it in the Firefighter"
                      onClick={() => { const u = new URL(location.href); u.searchParams.set("scenario", s.id); history.replaceState({}, "", u); setView("firefighter"); }}>
                      {s.id}</button>
                  </td>
                  <td className="p-2">{s.shape}</td>
                  {profiles.map((p) => {
                    const r = s.results[p];
                    return (
                      <td key={p} className="p-2">
                        <span className="flex items-center gap-1">{r.passed ? <CheckCircle2 size={14} className="text-ok" /> : <XCircle size={14} className="text-alert" />}
                          <span className="text-muted">{r.tool_calls} calls{r.wrong_actions ? `, ${r.wrong_actions} wrong` : ""}</span></span>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        {bench && <Benchmarks b={bench} />}
        <p className="text-[12.5px] text-muted">The full write-up, with what each scenario tests and where the algorithms change the outcome, is in docs/eval.md.</p>
      </div>
    </div>
  );
}

function Benchmarks({ b }: { b: any }) {
  const gs: string[] = Object.keys(b.graphs);
  const raw = Object.keys(b.graphs[gs[0]].raw);
  const tools = Object.keys(b.graphs[gs[0]].tools);
  const slow = tools.map((t) => [t, b.graphs[gs.at(-1)!].tools[t]?.db_ms ?? 0] as [string, number]).sort((x, y) => y[1] - x[1]).slice(0, 6);
  return (
    <section className="rounded-xl border border-border bg-surface p-4" data-testid="benchmarks">
      <h2 className="text-base font-semibold">Does it scale? Hero company vs a generated 2,000-service company</h2>
      <p className="mt-0.5 text-[12.5px] text-muted">Median of {b.runs} runs, {b.machine}, FalkorDB in Docker on the same machine ({b.generated_at}).</p>
      <div className="mt-3 grid gap-4 md:grid-cols-2">
        <table className="text-[12.5px]">
          <thead className="text-left text-muted"><tr><th className="py-1">Algorithm / query</th>{gs.map((g) => <th key={g} className="py-1">{g} ({b.graphs[g].size.services.toLocaleString()} services)</th>)}</tr></thead>
          <tbody>{raw.map((k) => (
            <tr key={k} className="border-t border-border"><td className="py-1 pr-2">{k}</td>
              {gs.map((g) => { const r = b.graphs[g].raw[k]; return <td key={g} className="py-1 tabular-nums">{r.error ? "timeout" : `${r.ms} ms`}</td>; })}</tr>
          ))}</tbody>
        </table>
        <table className="text-[12.5px]">
          <thead className="text-left text-muted"><tr><th className="py-1">Slowest tools at scale</th>{gs.map((g) => <th key={g} className="py-1">{g}</th>)}</tr></thead>
          <tbody>{slow.map(([t]) => (
            <tr key={t} className="border-t border-border"><td className="py-1 pr-2 font-mono">{t}</td>
              {gs.map((g) => { const x = b.graphs[g].tools[t]; return <td key={g} className="py-1 tabular-nums">{x?.error ? "error" : `${x?.db_ms} ms`}</td>; })}</tr>
          ))}</tbody>
        </table>
      </div>
    </section>
  );
}
