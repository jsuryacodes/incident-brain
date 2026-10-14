import { AlertTriangle, History, Link2, Phone } from "lucide-react";
import type { Elements, Run } from "../../lib/types";
import { SourceCard } from "../../components/ui";

const URL_RE = /\((https?:\/\/[^)\s]+)\)/;

export function IndustryLine({ text }: { text: string }) {
  const url = text.match(URL_RE)?.[1];
  const label = text.replace(URL_RE, "").trim();
  return (
    <p className="flex items-start gap-2 text-[13px]">
      <Link2 size={15} className="mt-0.5 shrink-0 text-muted" />
      <span>{url ? <a className="text-accent underline underline-offset-2" href={url} target="_blank" rel="noreferrer">{label}</a> : label}</span>
    </p>
  );
}

export function ReportCard({ run, universe, kind }: { run: Run; universe: Elements | undefined; kind?: string }) {
  const r = run.report || {};
  const name = (id: string) => universe?.nodes.find((n) => n.id === id)?.name || id.split(":").pop();
  const cost = run.totals?.cost_usd ?? 0;
  if (kind === "resolve") {
    return (
      <article className="space-y-3" data-testid="report">
        <h3 className="text-[15px] font-semibold">Resolved</h3>
        <p className="text-[13px] leading-snug">{r.note}</p>
        <ul className="flex flex-wrap gap-1.5">
          {[r.details?.resolution_id, r.details?.runbook_id, ...(r.details?.similar || [])].filter(Boolean).map((id: string) => (
            <li key={id} className="chip-mem rounded px-1.5 py-0.5 font-mono text-[11px]">{id}</li>
          ))}
        </ul>
        <Footer run={run} cost={cost} />
      </article>
    );
  }
  const cause = r.likely_cause || {};
  const seen = (r.similar_past_incidents || []) as { incident_id: string; what_fixed_it: string; resolved_by: string }[];
  const fromMemory = /Seen before:[^.]*\([^)]*\)[^.]*\./.exec(r.summary || "")?.[0];
  return (
    <article className="space-y-4" data-testid="report">
      <div className="flex items-center gap-2">
        <h3 className="text-[15px] font-semibold">Final report</h3>
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ${r.confidence === "high" ? "bg-ok-soft text-ok ring-ok/30" : "bg-surface-2 text-muted ring-border"}`}>
          confidence {r.confidence}
        </span>
      </div>
      <p className="text-[13px] leading-snug">{r.summary}</p>
      <section>
        <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Likely cause</h4>
        {cause.deploy_id || cause.service_id ? (
          <>
            <p className="font-mono text-[12.5px]">{cause.deploy_id || cause.service_id}{cause.ticket_key ? ` · ${cause.ticket_key}` : ""}</p>
            {cause.path?.length > 0 && (
              <p className="mt-1 flex flex-wrap items-center gap-1 text-[12px]">
                {cause.path.map((id: string, i: number) => (
                  <span key={id} className="flex items-center gap-1">
                    {i > 0 && <span className="text-accent">→</span>}
                    <span className="rounded bg-accent-soft px-1.5 py-0.5 text-text">{name(id)}</span>
                  </span>
                ))}
              </p>
            )}
            {cause.explanation && <p className="mt-1 text-[12.5px] text-muted">{cause.explanation}</p>}
          </>
        ) : (
          <p className="text-[13px] font-medium text-alert">Cause unknown: the agents found no recent change on any path from this service.</p>
        )}
      </section>
      {r.contact && (
        <section>
          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Who to call</h4>
          <p className="text-[13px]"><Phone size={14} className="mr-1.5 inline align-[-2px] text-ok" /><b>{r.contact.name}</b> <span className="text-muted">({r.contact.reason})</span></p>
          {r.bus_factor_warning && (
            <p className="mt-1.5 flex items-start gap-2 rounded-md bg-alert-soft p-2 text-[12.5px] text-text">
              <AlertTriangle size={14} className="mt-0.5 shrink-0 text-alert" /> <span><b>Maintainer left.</b> {r.bus_factor_warning}</span>
            </p>
          )}
        </section>
      )}
      {r.conflicting_decision && (
        <section>
          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">The decision it broke</h4>
          <p className="mb-1.5 text-[12.5px]">{r.conflicting_decision.how_it_conflicts}</p>
          <SourceCard s={{ id: r.conflicting_decision.source_id, label: (universe?.nodes.find((n) => n.id === r.conflicting_decision.source_id)?.label) || "Source",
            title: name(r.conflicting_decision.decision_id) || "", excerpt: r.conflicting_decision.excerpt }} />
        </section>
      )}
      {(fromMemory || seen.length > 0) && (
        <section>
          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Seen before</h4>
          {fromMemory && <p className="chip-mem mb-1.5 flex items-start gap-1.5 rounded-md p-2 text-[12.5px]"><History size={14} className="mt-0.5 shrink-0" /> From memory: {fromMemory}</p>}
          <ul className="space-y-1 text-[12.5px]">
            {seen.map((s) => (
              <li key={s.incident_id}><span className="font-mono text-[11.5px]">{s.incident_id}</span>: {s.what_fixed_it} <span className="text-muted">({s.resolved_by})</span></li>
            ))}
          </ul>
        </section>
      )}
      {r.industry_pattern && <section><IndustryLine text={r.industry_pattern} /></section>}
      {r.recommended_actions?.length > 0 && (
        <section>
          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Recommended actions</h4>
          <ol className="list-decimal space-y-0.5 pl-5 text-[12.5px]">{r.recommended_actions.map((a: string) => <li key={a}>{a}</li>)}</ol>
        </section>
      )}
      <Footer run={run} cost={cost} />
    </article>
  );
}

function Footer({ run, cost }: { run: Run; cost: number }) {
  return (
    <p className="border-t border-border pt-2 text-[11.5px] text-muted">
      Mode: {run.mode === "replay" ? "recorded run (replay)" : run.mode} · {run.totals?.llm_calls ?? "?"} model calls ·{" "}
      {run.totals?.tool_calls ?? run.steps.length} tool calls · cost ${cost.toFixed(4)}
    </p>
  );
}
