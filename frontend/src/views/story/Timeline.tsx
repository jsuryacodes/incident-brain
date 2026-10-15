import { ArrowRight, PenLine } from "lucide-react";
import { useEffect, useRef } from "react";
import { callNumbers } from "../../lib/replay";
import type { Beat, Run, StepEvent } from "../../lib/types";
import { AGENT_LANE } from "../../components/ui";

const writeLabel = (s: StepEvent) => {
  const parts = [
    ...s.writes.nodes.map((n) => (n.props.key ? `${n.label} ${n.props.key}` : n.label)),
    ...s.writes.edges.filter((e) => e.type === "DEPENDS_ON").map(() => "learned DEPENDS_ON"),
  ];
  if (!parts.length && s.writes.edges.length) parts.push(`${s.writes.edges.length} edge${s.writes.edges.length > 1 ? "s" : ""}`);
  return parts.slice(0, 3).join(" · ");
};

/** The card's one-liner: the step summary without the tool name ("read_source → ok" becomes "read chat:…"). */
export const oneLine = (s: StepEvent) => {
  const t = s.summary.replace(/^[a-z_]+ → /, "");
  return t === "ok" && typeof s.args.node_id === "string" ? `read ${s.args.node_id}` : t;
};

export function Timeline({ run, beat, idx, onSeek }: { run: Run | null; beat: Beat | null; idx: number; onSeek: (i: number) => void }) {
  const box = useRef<HTMLOListElement>(null);
  useEffect(() => {
    box.current?.querySelector('[aria-current="step"]')?.scrollIntoView({ block: "nearest", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }, [idx, run]);
  if (!run || !beat) {
    return (
      <div className="p-4 text-sm text-muted">
        <p className="font-medium text-text">Agent timeline</p>
        <p className="mt-1">Each tool call appears here as the agents work: Triage, then the Investigator, then the Communicator.</p>
      </div>
    );
  }
  const nums = callNumbers(run.steps);
  const steps = run.steps.slice(0, idx + 1);
  return (
    <ol ref={box} className="scroll-thin h-full space-y-1.5 overflow-y-auto p-3" aria-label="Agent timeline" data-testid="timeline">
      {steps.map((s, i) => {
        const lane = AGENT_LANE[s.agent] || AGENT_LANE.brain;
        const newLane = i === 0 || steps[i - 1].agent !== s.agent;
        const cur = i === idx;
        const next = run.steps[i + 1]?.agent;
        return (
          <li key={s.seq} className="fade-in">
            {newLane && (
              <div className={`mb-1 mt-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide ${lane.cls}`}>
                <span className={`h-2 w-2 rounded-full ${lane.dot}`} /> {lane.name}{beat.kind === "resolve" ? " · postmortem" : ""}
              </div>
            )}
            {s.action === "handoff" ? (
              <button onClick={() => onSeek(i)} aria-current={cur ? "step" : undefined}
                className={`w-full rounded-lg border-2 p-2.5 text-left ${cur ? "border-accent bg-accent-soft" : "border-border bg-surface-2"}`}>
                <div className="flex items-center gap-1.5 text-xs font-semibold">
                  <span className={lane.cls}>{lane.name}</span>
                  <ArrowRight size={13} className="text-muted" />
                  <span className={next ? (AGENT_LANE[next]?.cls || "") : ""}>{next ? AGENT_LANE[next]?.name : s.tool === "submit_report" ? "Final report" : "Done"}</span>
                </div>
                <div className="text-[11px] text-muted">via incident state (a Step node)</div>
                <p className="mt-1 line-clamp-3 text-[12.5px] leading-snug">{s.summary}</p>
              </button>
            ) : (
              <button onClick={() => onSeek(i)} aria-current={cur ? "step" : undefined} data-testid="step-card"
                className={`w-full rounded-lg border p-2 text-left transition-colors ${cur ? "border-accent bg-accent-soft ring-1 ring-accent" : "border-border bg-surface hover:bg-surface-2"}`}>
                <div className="flex items-center gap-2">
                  <span className="truncate font-mono text-[12px] font-medium">{s.tool}</span>
                  <span className="ml-auto shrink-0 text-[11px] text-muted">tool call {nums[i]}</span>
                </div>
                <p className="mt-0.5 line-clamp-2 text-[12px] leading-snug text-muted">{oneLine(s)}</p>
                {(s.writes.nodes.length > 0 || s.writes.edges.length > 0) && (
                  <span className="chip-mem mt-1 inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium">
                    <PenLine size={11} /> wrote {writeLabel(s)}
                  </span>
                )}
              </button>
            )}
          </li>
        );
      })}
    </ol>
  );
}
