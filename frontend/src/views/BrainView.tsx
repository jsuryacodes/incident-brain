import { CircleHelp, Info, Loader2, Send } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { GraphCanvas } from "../components/GraphCanvas";
import { CypherBlock, Skeleton, SourceCard } from "../components/ui";
import { api } from "../lib/api";
import { useApp } from "../lib/store";
import type { Source } from "../lib/types";

type Turn = { q: string; a?: any; error?: string; pending?: boolean };
const DONT_KNOW = /don't know|do not know|no information|nothing in/i;

function userId() {
  try {
    let u = sessionStorage.getItem("ib.user");
    if (!u) sessionStorage.setItem("ib.user", (u = `web-${Math.random().toString(36).slice(2, 8)}`));
    return u;
  } catch {
    return "web";
  }
}

export default function BrainView() {
  const { tenant, unlocked, meta, toast } = useApp();
  const [sugs, setSugs] = useState<{ kind: string; question: string }[] | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const session = useRef<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const persisted = unlocked && !!meta?.code_configured;

  useEffect(() => {
    const load = () => api.suggestions(tenant).then((r) => setSugs(r.questions), (e) => toast(`Couldn't load suggestions: ${e.message}`, "error", load));
    load();
  }, [tenant, toast]);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [turns]);

  const ask = async (q: string) => {
    q = q.trim();
    if (!q || turns.some((t) => t.pending)) return;
    setText("");
    const done = turns.filter((t) => t.a);
    setTurns((ts) => [...ts, { q, pending: true }]);
    try {
      const a = await api.ask({
        tenant, user: userId(), question: q, session_id: persisted ? session.current : null,
        turns: done.slice(-10).map((t) => ({ question: t.q, answer: t.a.answer, citations: t.a.citations.map((c: any) => ({ node_id: c.node_id })), people: t.a.people })),
      });
      if (a.session_id) session.current = a.session_id;
      setTurns((ts) => ts.map((t, i) => (i === ts.length - 1 ? { q, a } : t)));
    } catch (e) {
      setTurns((ts) => ts.map((t, i) => (i === ts.length - 1 ? { q, error: (e as Error).message } : t)));
    }
  };

  return (
    <div className="mx-auto flex h-full max-w-4xl flex-col px-3 sm:px-4">
      <div className="scroll-thin min-h-0 flex-1 space-y-4 overflow-y-auto py-4" data-testid="brain-thread">
        {turns.length === 0 && (
          <div className="fade-in">
            <h1 className="text-lg font-semibold">Ask the Brain</h1>
            <p className="mt-1 text-sm text-muted">Questions about this company, answered from its graph. Every answer quotes its sources word for word, or says it doesn't know.</p>
            <h2 className="mb-2 mt-5 text-xs font-semibold uppercase tracking-wide text-muted">Try one</h2>
            <div className="grid gap-2 sm:grid-cols-2">
              {!sugs ? [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-12" />) : sugs.map((s) => (
                <button key={s.question} onClick={() => ask(s.question)} data-testid="suggestion"
                  className="card flex items-center gap-2 p-3 text-left text-[13.5px] hover:border-accent">
                  <CircleHelp size={15} className="shrink-0 text-muted" /> <span className="flex-1">{s.question}</span>
                </button>
              ))}
            </div>
          </div>
        )}
        {turns.map((t, i) => (
          <div key={i} className="space-y-2">
            <p className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-sm bg-text px-3.5 py-2 text-[13.5px] text-bg">{t.q}</p>
            {t.pending && <div className="flex items-center gap-2 text-sm text-muted"><Loader2 size={15} className="animate-spin" /> Querying the graph…</div>}
            {t.error && <p role="alert" className="text-sm text-alert">Couldn't answer: {t.error} <button className="underline" onClick={() => ask(t.q)}>Retry</button></p>}
            {t.a && <Answer a={t.a} tenant={tenant} idx={i} />}
          </div>
        ))}
        <div ref={end} />
      </div>
      <form className="border-t border-border py-3" onSubmit={(e) => (e.preventDefault(), ask(text))}>
        <div className="flex gap-2">
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder={turns.length ? "Ask a follow-up, e.g. “Who should I call about it?”" : "Ask about a decision, a service, who knows what…"}
            aria-label="Your question" maxLength={500} data-testid="brain-input"
            className="min-w-0 flex-1 rounded-lg border border-border bg-surface px-3 py-2 text-sm" />
          <button disabled={!text.trim()} aria-label="Ask" className="flex items-center gap-1.5 rounded-lg bg-text px-3 py-2 text-sm font-medium text-bg disabled:opacity-40">
            <Send size={15} /> Ask
          </button>
        </div>
        <p className="mt-1.5 text-[11.5px] text-muted">
          {persisted ? "Saved: this conversation is stored in the graph as Step nodes." : "Not saved: without an access code nothing is written. Follow-ups still work in this tab."}
        </p>
      </form>
    </div>
  );
}

function Answer({ a, tenant, idx }: { a: any; tenant: string; idx: number }) {
  const dontKnow = !a.citations?.length && DONT_KNOW.test(a.answer || "");
  const [graphOpen, setGraphOpen] = useState(false);
  if (!a.answer) {
    return <p className="text-sm text-muted">No answer passed the grounding checks, so none is shown.</p>;
  }
  return (
    <article className={`card fade-in space-y-3 p-4 ${dontKnow ? "border-dashed" : ""}`} data-testid="answer">
      {dontKnow ? (
        <div className="flex items-start gap-2" data-testid="dont-know">
          <Info size={16} className="mt-0.5 shrink-0 text-muted" />
          <div>
            <p className="text-[13.5px]">{a.answer}</p>
            <p className="mt-1 text-[12px] text-muted">The graph has no source for this, so the Brain doesn't guess.</p>
          </div>
        </div>
      ) : (
        <p className="text-[13.5px] leading-relaxed">{a.answer}</p>
      )}
      {a.stale_warnings?.length > 0 && (
        <ul className="space-y-1 text-[12.5px]">
          {a.stale_warnings.map((w: any) => <li key={w.node_id} className="rounded-md bg-alert-soft px-2 py-1"><b>Out of date:</b> {w.node_id}: {w.reason}</li>)}
        </ul>
      )}
      {a.sources?.length > 0 && (
        <div>
          <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted">Sources</h3>
          <div className="grid gap-2 md:grid-cols-2">{a.sources.map((s: Source) => <SourceCard key={s.id + s.excerpt} s={s} />)}</div>
        </div>
      )}
      {a.cited_graph?.nodes?.length > 1 && (
        <details onToggle={(e) => setGraphOpen((e.target as HTMLDetailsElement).open)}>
          <summary className="cursor-pointer text-[12.5px] font-medium text-muted">Cited nodes as a graph</summary>
          {graphOpen && (
            <div className="relative mt-2 h-56 rounded-lg border border-border bg-bg">
              <GraphCanvas elements={a.cited_graph} layoutKey={`brain:${tenant}:${idx}:${a.session_id || ""}:${a.question}`} compact
                current={{ nodes: new Set(a.citations.map((c: any) => c.node_id)), edges: new Set() }} ariaLabel="Graph of the cited nodes" />
            </div>
          )}
        </details>
      )}
      <details>
        <summary className="cursor-pointer text-[12.5px] font-medium text-muted">How I got this ({a.steps.length} steps)</summary>
        <ol className="mt-2 space-y-2">
          {a.steps.map((s: any) => (
            <li key={s.seq} className="text-[12.5px]">
              <p><span className="font-mono font-medium">{s.tool}</span> <span className="text-muted">{s.summary}</span></p>
              {(s.receipt?.queries || []).slice(0, 3).map((q: any, i: number) => <div key={i} className="mt-1"><CypherBlock cypher={q.cypher} /></div>)}
            </li>
          ))}
        </ol>
      </details>
      <p className="text-[11px] text-muted">mode {a.mode}{a.persisted ? ` · saved in ${a.session_id}` : " · not saved"} · turn {a.turn}</p>
    </article>
  );
}
