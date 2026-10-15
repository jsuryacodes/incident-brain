import { Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { GraphCanvas } from "../components/GraphCanvas";
import { Empty, Skeleton } from "../components/ui";
import { api } from "../lib/api";
import { useApp } from "../lib/store";
import type { Elements } from "../lib/types";
import { NodePane } from "./story/Drawer";

const LABELS = ["Service", "Team", "Person", "Deploy", "Incident", "Decision", "Doc", "Ticket", "ChatThread", "Runbook",
  "Resolution", "RootCause", "PublicPostmortem", "Fact"];

const NAMES: Record<string, string> = { PublicPostmortem: "Postmortem", ChatThread: "Chat" };

export default function ExplorerView() {
  const { tenant, meta, toast } = useApp();
  const [labels, setLabels] = useState<string[]>(["Service", "Team", "Person"]);
  const [agentOnly, setAgentOnly] = useState(false);
  const [hubs, setHubs] = useState(false);
  const [query, setQuery] = useState("");
  const [data, setData] = useState<(Elements & Record<string, any>) | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const tenantName = meta?.tenants.find((t) => t.id === tenant)?.name || tenant;

  useEffect(() => {
    let alive = true;
    setData(null);
    const load = () => api.explorer(tenant, labels, agentOnly ? "agent" : undefined).then((d) => alive && setData(d),
      (e) => toast(`Couldn't load the graph: ${e.message}`, "error", load));
    load();
    return () => void (alive = false);
  }, [tenant, labels, agentOnly, toast]);

  const match = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q || !data) return null;
    return new Set(data.nodes.filter((n) => n.name.toLowerCase().includes(q) || n.id.toLowerCase().includes(q)).map((n) => n.id));
  }, [query, data]);

  const toggle = (l: string) => setLabels((ls) => (ls.includes(l) ? ls.filter((x) => x !== l) : [...ls, l]));
  return (
    <div className="grid h-full min-h-0 grid-cols-1 lg:grid-cols-[260px_minmax(0,1fr)_360px]">
      <aside className="scroll-thin space-y-4 overflow-y-auto border-border bg-surface p-3 lg:border-r" aria-label="Explorer filters">
        <label className="relative block">
          <Search size={14} className="absolute left-2.5 top-2.5 text-muted" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search nodes" aria-label="Search nodes" data-testid="explorer-search"
            className="w-full rounded-md border border-border bg-surface-2 py-1.5 pl-8 pr-2 text-sm" />
          {match && <span className="mt-1 block text-[11.5px] text-muted">{match.size} match{match.size === 1 ? "" : "es"}</span>}
        </label>
        <label className="flex items-center justify-between gap-2 rounded-md bg-mem-fill/60 px-2.5 py-2 text-sm ring-1 ring-mem/40">
          <span><b>Agent memory only</b><span className="block text-[11.5px] text-muted">what agents wrote, in amber</span></span>
          <input type="checkbox" checked={agentOnly} onChange={(e) => setAgentOnly(e.target.checked)} data-testid="agent-only" className="h-4 w-4 accent-[var(--mem-stroke)]" />
        </label>
        <label className="flex items-center justify-between gap-2 px-1 text-sm">
          <span><b>Critical hubs</b><span className="block text-[11.5px] text-muted">size services by <code className="font-mono">algo.pageRank</code></span></span>
          <input type="checkbox" checked={hubs} onChange={(e) => setHubs(e.target.checked)} data-testid="hubs" className="h-4 w-4" />
        </label>
        <fieldset disabled={agentOnly} className="disabled:opacity-50">
          <legend className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Labels</legend>
          <div className="grid grid-cols-2 gap-x-2 gap-y-1">
            {LABELS.map((l) => (
              <label key={l} className="flex items-center gap-1.5 text-[13px]">
                <input type="checkbox" checked={labels.includes(l)} onChange={() => toggle(l)} data-testid={`label-${l}`} /> {NAMES[l] || l}
              </label>
            ))}
          </div>
        </fieldset>
        {data && (
          <p className="text-[12px] text-muted" data-testid="explorer-counts">
            {data.nodes.length} nodes · {data.edges.length} edges on screen. Agent memory in {tenantName}: <b className="text-text">{data.agent_nodes}</b> nodes,{" "}
            <b className="text-text">{data.agent_edges}</b> edges{data.truncated ? " · capped" : ""}.
          </p>
        )}
      </aside>
      <section className="relative min-h-[60vh] lg:min-h-0" aria-label="Company graph">
        {!data ? (
          <div className="p-4"><Skeleton className="h-full min-h-80" /></div>
        ) : data.nodes.length === 0 ? (
          <Empty title={agentOnly ? `No agent memory in ${tenantName}` : "Nothing to show"}>
            {agentOnly
              ? "No agent has written anything to this company's graph yet. Each company is its own FalkorDB graph, so memory learned at another company can never appear here."
              : "Pick at least one label."}
          </Empty>
        ) : (
          <GraphCanvas elements={data} layoutKey={`explorer:${tenant}:${agentOnly ? "agent" : labels.slice().sort().join(",")}`} sizeByPagerank={hubs}
            selected={selected} onSelect={setSelected} match={match} ariaLabel={`${tenantName} company graph`} />
        )}
        {hubs && data && data.nodes.length > 0 && (
          <p className="pointer-events-none absolute bottom-2 left-2 rounded-md bg-surface/90 px-2.5 py-1.5 text-[11.5px] text-muted ring-1 ring-border">
            Service size = PageRank over DEPENDS_ON (<code className="font-mono">{data.pagerank}</code>)
          </p>
        )}
      </section>
      <aside className="scroll-thin min-h-[30vh] overflow-y-auto border-border bg-surface p-4 lg:border-l" aria-label="Node details">
        {selected && data ? <NodePane id={selected} universe={data} tenant={tenant} onOpen={setSelected} />
          : <Empty title="Click a node">Its properties, edges and the sources that back it show up here.</Empty>}
      </aside>
    </div>
  );
}
