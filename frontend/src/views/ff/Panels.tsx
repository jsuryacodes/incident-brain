import { CheckCircle2, CircleDashed, Loader2, ShieldAlert, ShieldCheck, XCircle } from "lucide-react";
import { useState } from "react";
import type { Action, Execution, Hypothesis, Report } from "../../lib/types";

const short = (id: string) => id.split(":").pop() || id;

export function Chip({ id, onOpen, tone = "" }: { id: string; onOpen?: (id: string) => void; tone?: string }) {
  return (
    <button onClick={() => onOpen?.(id)} title={id}
      className={`max-w-[11rem] shrink-0 truncate whitespace-nowrap rounded px-1.5 py-0.5 font-mono text-[11px] ring-1 ring-border hover:bg-surface-2 ${tone}`}>
      {short(id)}
    </button>
  );
}

const STATUS = {
  confirmed: { icon: CheckCircle2, cls: "text-ok", ring: "ring-ok/40 bg-ok-soft", label: "confirmed" },
  open: { icon: CircleDashed, cls: "text-accent", ring: "ring-accent/40 bg-accent-soft", label: "open" },
  rejected: { icon: XCircle, cls: "text-muted", ring: "ring-border bg-surface-2", label: "rejected" },
} as const;

/** The hypothesis board: every lead with evidence for and against, its status and the reason. */
export function Board({ hypotheses, breakdown, onOpen }: { hypotheses: Hypothesis[]; breakdown?: { effect: string; factor: string; node_id: string | null }[]; onOpen?: (id: string) => void }) {
  const order = { confirmed: 0, open: 1, rejected: 2 };
  const hs = [...hypotheses].sort((a, b) => order[a.status] - order[b.status]);
  return (
    <div className="space-y-3" data-testid="board">
      <div className="flex flex-wrap gap-2 text-[12px]">
        {(["confirmed", "open", "rejected"] as const).map((s) => (
          <span key={s} className={`rounded-full px-2 py-0.5 ring-1 ${STATUS[s].ring}`}>{hs.filter((h) => h.status === s).length} {STATUS[s].label}</span>
        ))}
      </div>
      {hs.map((h) => {
        const S = STATUS[h.status];
        return (
          <article key={h.id} className={`rounded-lg p-3 ring-1 ${S.ring}`} data-testid={`hyp-${h.status}`}>
            <div className="flex items-start gap-2">
              <S.icon size={16} className={`mt-0.5 shrink-0 ${S.cls}`} />
              <div className="min-w-0">
                <p className={`text-[13px] font-medium leading-snug ${h.status === "rejected" ? "text-muted line-through decoration-1" : ""}`}>{h.claim}</p>
                {!h.contradicting.some((e) => e.claim === h.reason) && <p className="mt-1 text-[12px] leading-snug">{h.reason}</p>}
              </div>
            </div>
            {(h.supporting.length > 0 || h.contradicting.length > 0) && (
              <ul className="mt-2 space-y-1 text-[12px]">
                {h.supporting.map((e, i) => (
                  <li key={`s${i}`} className="flex items-start gap-1.5"><span className="text-ok">for</span><Chip id={e.node_id} onOpen={onOpen} /><span className="text-muted">{e.claim}</span></li>
                ))}
                {h.contradicting.map((e, i) => (
                  <li key={`c${i}`} className="flex items-start gap-1.5"><span className="text-alert">against</span><Chip id={e.node_id} onOpen={onOpen} /><span className="text-muted">{e.claim}</span></li>
                ))}
              </ul>
            )}
          </article>
        );
      })}
      {breakdown && breakdown.length > 0 && (
        <section>
          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Confidence: what raised or lowered it</h4>
          <ul className="space-y-0.5 text-[12.5px]">
            {breakdown.map((b, i) => (
              <li key={i}><span className={`font-mono font-bold ${b.effect === "+" ? "text-ok" : "text-alert"}`}>{b.effect}</span> {b.factor}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

const KIND: Record<string, string> = {
  rollback: "Roll back", hold: "Hold", page: "Page", escalate: "Escalate", suppress_page: "Suppress page", notify: "Notify",
  open_ticket: "Ticket", flag_stale: "Flag stale",
};

/** The action plan: each step with its graph justification and (rollbacks) the safety check; Approve executes it. */
export function Actions({ plan, execution, canApprove, approving, onApprove, onOpen, incidents }: {
  plan: Action[]; execution: Execution | null; canApprove: boolean; approving: boolean;
  onApprove: (ids: string[] | null) => void; onOpen?: (id: string) => void; incidents: number;
}) {
  const [off, setOff] = useState<Set<string>>(new Set());
  const done = new Map((execution?.results || []).map((r) => [r.action, r]));
  return (
    <div className="space-y-3" data-testid="actions">
      <div className="rounded-lg bg-surface-2 p-3 text-[12.5px] leading-snug">
        {execution ? (
          <p><b>{execution.already_executed ? "Already approved earlier." : "Approved and executed (simulated)."}</b> Each action wrote to the
            company's copy of the graph with origin "agent" ({execution.session_id}).</p>
        ) : canApprove ? (
          <p>Nothing has run yet. Approving executes the checked actions <b>in simulation</b> (no real pager or deploy) on this run's copy of
            the company, then re-runs the checks.</p>
        ) : (
          <p>Approval needs the access code and a fresh run. Recorded runs show the approval that was recorded with them.</p>
        )}
      </div>
      {Array.from({ length: incidents }, (_, k) => k).map((k) => (
        <section key={k} className="space-y-2">
          {incidents > 1 && <h4 className="text-xs font-semibold uppercase tracking-wide text-muted">Incident {k + 1}</h4>}
          {plan.filter((a) => a.incident === k).map((a) => {
            const r = done.get(a.id);
            const risky = a.safety?.verdict === "risky";
            return (
              <article key={a.id} className="rounded-lg border border-border p-2.5" data-testid={`action-${a.kind}`}>
                <div className="flex items-start gap-2">
                  {canApprove && !execution && (
                    <input type="checkbox" className="mt-1" aria-label={`approve ${a.title}`} checked={!off.has(a.id)}
                      onChange={() => setOff((s) => { const n = new Set(s); n.has(a.id) ? n.delete(a.id) : n.add(a.id); return n; })} />
                  )}
                  <span className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[10.5px] font-semibold uppercase tracking-wide ring-1 ${
                    a.kind === "hold" ? "bg-alert-soft text-alert ring-alert/30" : a.kind === "suppress_page" ? "bg-surface-2 text-muted ring-border" : "bg-accent-soft text-accent ring-accent/30"}`}>
                    {KIND[a.kind] || a.kind}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className={`text-[13px] font-medium leading-snug ${a.kind === "suppress_page" ? "line-through decoration-1" : ""}`}>{a.title}</p>
                    <p className="mt-0.5 text-[12px] leading-snug text-muted">{a.justification.why}</p>
                    {a.justification.path.length > 1 && (
                      <p className="mt-1 flex flex-wrap items-center gap-1 text-[11.5px]">
                        {a.justification.path.map((id, i) => (
                          <span key={id + i} className="flex items-center gap-1">{i > 0 && <span className="text-accent">→</span>}<Chip id={id} onOpen={onOpen} /></span>
                        ))}
                      </p>
                    )}
                    {a.safety && (
                      <div className={`mt-2 rounded-md p-2 text-[12px] ring-1 ${risky ? "bg-alert-soft ring-alert/30" : "bg-ok-soft ring-ok/30"}`} data-testid="safety">
                        <p className="flex items-center gap-1 font-semibold">{risky ? <ShieldAlert size={14} /> : <ShieldCheck size={14} />}
                          Safety check: {a.safety.verdict}</p>
                        {a.safety.reasons.map((x, i) => <p key={i} className="mt-0.5">{x}</p>)}
                        {a.safety.blast && <p className="mt-0.5 text-muted">{a.safety.blast}</p>}
                      </div>
                    )}
                    {r && <p className={`mt-1.5 text-[12px] font-medium ${r.ok ? "text-ok" : "text-alert"}`}>
                      {!r.ok ? `failed: ${r.summary}` : ["page", "rollback", "open_ticket", "flag_stale"].includes(a.kind) ? `✓ ${r.summary.split(": ")[0]}` : "✓ recorded as a decision"}</p>}
                  </div>
                </div>
              </article>
            );
          })}
        </section>
      ))}
      {canApprove && !execution && (
        <button disabled={approving} onClick={() => onApprove(off.size ? plan.filter((a) => !off.has(a.id)).map((a) => a.id) : null)}
          className="flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-[13px] font-medium text-white disabled:opacity-50" data-testid="approve">
          {approving && <Loader2 size={14} className="animate-spin" />} Approve {off.size ? `${plan.length - off.size} of ${plan.length}` : "all"} (simulated)
        </button>
      )}
      {execution?.verification && (
        <section className="space-y-1.5" data-testid="verification">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted">Verification: the checks, run again</h4>
          {execution.verification.checks.map((c, i) => (
            <p key={i} className={`rounded-md p-2 text-[12.5px] ring-1 ${c.cleared ? "bg-ok-soft ring-ok/30" : "bg-surface-2 ring-border"}`}>
              <b>{c.cleared ? "Cleared" : "Not cleared"}</b>{incidents > 1 ? ` (incident ${c.incident + 1})` : ""}: {c.summary}
            </p>
          ))}
        </section>
      )}
    </div>
  );
}

/** Report of a Firefighter run: one card per incident, then the rejected leads and suppressed pages. */
export function FFReport({ r, onOpen }: { r: Report; onOpen?: (id: string) => void }) {
  const incs: any[] = r.incidents || [{ ...r, alerts: [] }];
  return (
    <div className="space-y-4" data-testid="ff-report">
      <p className="text-[13.5px] leading-snug">{r.summary}</p>
      {incs.map((i, k) => {
        const lc = i.likely_cause || {};
        return (
          <article key={k} className="rounded-lg border border-border p-3">
            <div className="flex flex-wrap items-center gap-1.5 text-[12px]">
              {incs.length > 1 && <b className="mr-1">Incident {k + 1}</b>}
              {(i.alerts || []).map((a: string) => <Chip key={a} id={a} onOpen={onOpen} tone="text-alert" />)}
              <span className="ml-auto rounded-full bg-surface-2 px-2 py-0.5 ring-1 ring-border">confidence {i.confidence}</span>
            </div>
            <p className="mt-2 text-[13px]">
              {lc.deploy_id ? <>Cause <span className="font-mono">{lc.deploy_id}</span></> : i.root ? <>Shared root <b>{short(i.root.service_id)}</b> (no change: under load)</> : "No cause found"}
            </p>
            {lc.path?.length > 1 && (
              <p className="mt-1 flex flex-wrap items-center gap-1 text-[12px]">
                {lc.path.map((id: string, n: number) => <span key={id} className="flex items-center gap-1">{n > 0 && <span className="text-accent">→</span>}<Chip id={id} onOpen={onOpen} /></span>)}
              </p>
            )}
            <p className="mt-1 text-[12.5px] text-muted">{lc.explanation}</p>
            <p className="mt-1.5 text-[12.5px]"><b>{i.contact?.person_id ? `Page ${i.contact.name}` : i.contact?.team_id ? `Escalate to ${i.contact.team_id}` : "Nobody to page"}</b>{i.contact?.reason ? `: ${i.contact.reason}` : ""}</p>
            {i.bus_factor_warning && <p className="mt-1 text-[12px] text-alert">{i.bus_factor_warning}</p>}
            {i.look_first?.service_ids && <p className="mt-1 text-[12px]">Look first: {i.look_first.service_ids.map(short).join(", ")} <span className="text-muted">({i.look_first.algorithm})</span></p>}
          </article>
        );
      })}
      {(r.suppressed_pages || []).length > 0 && (
        <section>
          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Pages not sent ({r.suppressed_pages.length})</h4>
          <ul className="space-y-1 text-[12.5px]" data-testid="suppressed">
            {r.suppressed_pages.map((p: any) => <li key={p.alert}><s>{p.name || p.team_id}</s> for {short(p.alert)}: <span className="text-muted">{p.reason}</span></li>)}
          </ul>
        </section>
      )}
      {(r.rejected_leads || []).length > 0 && (
        <section>
          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Recent changes ruled out</h4>
          <ul className="space-y-1 text-[12.5px]">
            {r.rejected_leads.map((x: any) => <li key={x.deploy_id}><span className="font-mono">{short(x.deploy_id)}</span>: <span className="text-muted">{x.reason}</span></li>)}
          </ul>
        </section>
      )}
    </div>
  );
}
