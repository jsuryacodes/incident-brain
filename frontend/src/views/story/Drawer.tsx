import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { callNumbers } from "../../lib/replay";
import type { Elements, Run, Source, StepEvent } from "../../lib/types";
import { AGENT_LANE, CypherBlock, Empty, JsonBlock, Skeleton, SourceCard } from "../../components/ui";
import type { DrawerTab } from "./store";
import { ReportCard } from "./ReportCard";

export function Drawer(p: {
  run: Run | null; idx: number; tab: DrawerTab; setTab: (t: DrawerTab) => void; selected: string | null;
  universe: Elements | undefined; tenant: string; onOpen: (id: string) => void; beatKind?: string;
}) {
  const step = p.run && p.idx >= 0 ? p.run.steps[p.idx] : null;
  const tabs: { id: DrawerTab; label: string; show: boolean }[] = [
    { id: "step", label: "Receipt", show: true },
    { id: "node", label: "Node", show: !!p.selected },
    { id: "report", label: p.beatKind === "resolve" ? "Resolution" : "Report", show: !!p.run?.report && p.idx === (p.run?.steps.length ?? 0) - 1 },
  ];
  return (
    <section className="flex h-full min-h-0 flex-col" aria-label="Receipt drawer">
      <div role="tablist" className="flex gap-1 border-b border-border px-3 pt-2">
        {tabs.filter((t) => t.show).map((t) => (
          <button key={t.id} role="tab" aria-selected={p.tab === t.id} onClick={() => p.setTab(t.id)}
            className={`-mb-px border-b-2 px-2.5 py-1.5 text-sm ${p.tab === t.id ? "border-accent font-medium" : "border-transparent text-muted hover:text-text"}`}>
            {t.label}
          </button>
        ))}
      </div>
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto p-4" data-testid="drawer">
        {p.tab === "node" && p.selected ? (
          <NodePane id={p.selected} universe={p.universe} tenant={p.tenant} onOpen={p.onOpen} />
        ) : p.tab === "report" && p.run?.report ? (
          <ReportCard run={p.run} universe={p.universe} kind={p.beatKind} />
        ) : step ? (
          <StepPane step={step} n={callNumbers(p.run!.steps)[p.idx]} onOpen={p.onOpen} />
        ) : (
          <Empty title="Every step is a receipt">
            When the agents run, this panel shows the exact Cypher each tool sent to FalkorDB, its parameters, what came back
            and the sources it quoted.
          </Empty>
        )}
      </div>
    </section>
  );
}

function StepPane({ step, n, onOpen }: { step: StepEvent; n: number; onOpen: (id: string) => void }) {
  const lane = AGENT_LANE[step.agent] || AGENT_LANE.brain;
  return (
    <div className="space-y-4" data-testid="receipt">
      <div>
        <div className="flex items-center gap-2 text-xs">
          <span className={`h-2 w-2 rounded-full ${lane.dot}`} />
          <span className={`font-semibold ${lane.cls}`}>{lane.name}</span>
          <span className="text-muted">· step {step.seq} · tool call {n}</span>
        </div>
        <h3 className="mt-1 font-mono text-[15px] font-semibold">{step.tool}</h3>
        <p className="mt-1 text-[13px] leading-snug">{step.summary}</p>
      </div>
      {step.cited.length > 0 && (
        <div>
          <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted">Sources</h4>
          <div className="space-y-2">{step.cited.map((s: Source) => <SourceCard key={s.id + s.excerpt} s={s} onOpen={onOpen} />)}</div>
        </div>
      )}
      {step.queries.length > 0 ? (
        <div>
          <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
            Cypher{step.queries.length > 1 ? ` · ${step.queries.length} queries` : ""}
          </h4>
          <div className="space-y-2">
            {step.queries.map((q, i) => (
              <div key={i} className="space-y-1">
                <CypherBlock cypher={q.cypher} write={q.write} />
                {Object.keys(q.params).length > 0 && (
                  <details className="text-xs">
                    <summary className="cursor-pointer text-muted">Parameters</summary>
                    <JsonBlock value={q.params} />
                  </details>
                )}
              </div>
            ))}
          </div>
        </div>
      ) : (
        step.action === "handoff" && (
          <p className="rounded-lg bg-surface-2 p-3 text-xs text-muted">A hand-off is not a query: the note is saved as a Step node in
            the graph, and the next agent starts from it with an empty conversation.</p>
        )
      )}
      {step.result_preview && (
        <details className="text-xs" open={step.queries.length === 0}>
          <summary className="cursor-pointer font-semibold uppercase tracking-wide text-muted">{step.action === "handoff" ? "Hand-off details" : "Result"}</summary>
          <JsonBlock value={step.action === "handoff" ? step.args : step.result_preview} />
        </details>
      )}
    </div>
  );
}

export function NodePane({ id, universe, tenant, onOpen }: { id: string; universe: Elements | undefined; tenant: string; onOpen: (id: string) => void }) {
  const el = universe?.nodes.find((n) => n.id === id);
  const [live, setLive] = useState<any>(undefined);
  useEffect(() => {
    let alive = true;
    setLive(undefined);
    api.node(tenant, id).then((r) => alive && setLive(r), () => alive && setLive(null)); // null: not in the live graph (recorded run)
    return () => void (alive = false);
  }, [id, tenant]);
  const name = (x: string) => universe?.nodes.find((n) => n.id === x)?.name || x;
  const edges = (universe?.edges || []).filter((e) => e.source === id || e.target === id);
  const props = el?.props || live?.result?.props || {};
  return (
    <div className="space-y-4" data-testid="node-pane">
      <div>
        <div className="flex items-center gap-2 text-xs text-muted">
          <span className="rounded bg-surface-2 px-1.5 py-0.5 ring-1 ring-border">{el?.label || live?.result?.label}</span>
          {(el?.origin || live?.origin) === "agent" ? (
            <span className="chip-mem rounded px-1.5 py-0.5 font-medium">AI · written by an agent</span>
          ) : (
            <span>seeded company data</span>
          )}
        </div>
        <h3 className="mt-1 text-[15px] font-semibold">{el?.name || id}</h3>
        <p className="font-mono text-[11px] text-muted">{id}</p>
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[12.5px]">
        {Object.entries(props).filter(([k]) => !["origin", "name"].includes(k)).slice(0, 14).map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-muted">{k}</dt>
            <dd className="min-w-0 break-words">{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd>
          </div>
        ))}
      </dl>
      {edges.length > 0 && (
        <div>
          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Edges in this view</h4>
          <ul className="space-y-0.5 text-[12.5px]">
            {edges.slice(0, 20).map((e) => {
              const other = e.source === id ? e.target : e.source;
              return (
                <li key={`${e.source}${e.type}${e.target}`} className="flex items-center gap-1.5">
                  <span className={`font-mono text-[11px] ${e.origin === "agent" ? "text-mem" : "text-muted"}`}>
                    {e.source === id ? `${e.type} →` : `← ${e.type}`}
                  </span>
                  <button className="truncate hover:underline" onClick={() => onOpen(other)}>{name(other)}</button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {live === undefined ? <Skeleton className="h-16" /> : live?.sources?.length > 0 && (
        <div>
          <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted">Sources</h4>
          <div className="space-y-2">{live.sources.map((s: Source) => <SourceCard key={s.id} s={s} onOpen={onOpen} />)}</div>
        </div>
      )}
    </div>
  );
}
