import { X } from "lucide-react";
import type { Compare } from "../../lib/types";
import { IndustryLine } from "./ReportCard";

const short = (id: string | null) => (id ? id.split(":").pop() : "—");

export function ComparePanel({ c, onClose }: { c: Compare; onClose: () => void }) {
  const best = Math.min(...c.columns.map((x) => x.investigator_tool_calls_until_cause ?? Infinity));
  return (
    <div className="card fade-in max-h-full overflow-auto p-4 sm:p-5" role="region" aria-label="Before and after memory" data-testid="compare">
      <div className="mb-3 flex items-start gap-3">
        <div>
          <h2 className="text-base font-semibold">Before / after memory</h2>
          <p className="text-[12.5px] text-muted">Same agents, same tools. The only difference is what Session 1 wrote into the graph.
            {c.source === "replay" ? " Numbers from the recorded runs." : " Numbers from your fresh runs."}</p>
        </div>
        <button onClick={onClose} aria-label="Close before/after panel" className="ml-auto rounded p-1 text-muted hover:text-text"><X size={18} /></button>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        {c.columns.map((col) => {
          const n = col.investigator_tool_calls_until_cause;
          return (
            <section key={col.key} className={`rounded-lg border p-3 ${n === best ? "border-ok/50 bg-ok-soft/40" : "border-border bg-surface-2"}`} data-testid={`compare-${col.key}`}>
              <h3 className="text-sm font-semibold">{col.title}</h3>
              <p className="text-[12px] text-muted">alert on {short(col.alert_service)}{col.incident ? ` · ${col.incident}` : ""}</p>
              <div className="mt-2">
                <div className={`text-3xl font-semibold tabular-nums ${col.cause_found ? "" : "text-alert"}`} data-testid="calls">
                  {col.cause_found ? n : "not found"}
                </div>
                <div className="text-[11.5px] text-muted">{c.metric.toLowerCase().replace(/^investigator/, "Investigator")}</div>
              </div>
              <dl className="mt-3 space-y-1.5 text-[12.5px]">
                <Row k="Cause found?" v={col.cause_found ? `yes: ${col.cause}` : "no: cause unknown"} />
                <Row k="Recalled from memory" v={col.recalled_incident ? `${col.recalled_incident.key}` : "nothing (no agent memory)"} mem={!!col.recalled_incident} />
                <Row k="Who fixed it" v={col.recalled_incident?.fixed_by.join(", ") || "—"} />
                <Row k="Who to call" v={col.contact || "—"} />
                <Row k="Confidence" v={col.confidence || "—"} />
                {col.cause_found && <Row k="Whole team, tool calls until cause" v={String(col.tool_calls_until_cause)} />}
              </dl>
              {col.industry_match && <div className="mt-2"><IndustryLine text={col.industry_match} /></div>}
            </section>
          );
        })}
      </div>
    </div>
  );
}

function Row({ k, v, mem }: { k: string; v: string; mem?: boolean }) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-muted">{k}</dt>
      <dd className={mem ? "chip-mem inline-block rounded px-1.5" : ""}>{v}</dd>
    </div>
  );
}
