import { Check, Copy, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { pretty, tokenize } from "../lib/cypher";
import type { Source } from "../lib/types";

export function Dialog({ title, onClose, children, labelledBy }: { title: string; onClose: () => void; children: ReactNode; labelledBy: string }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current!;
    if (!d.open) d.showModal();
    const close = () => onClose();
    d.addEventListener("close", close);
    return () => d.removeEventListener("close", close);
  }, [onClose]);
  return (
    <dialog ref={ref} aria-labelledby={labelledBy}
      className="m-auto w-[min(92vw,560px)] rounded-xl border border-border bg-surface p-0 text-text shadow-2xl backdrop:bg-black/40"
      onClick={(e) => e.target === ref.current && ref.current?.close()}>
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <h2 id={labelledBy} className="text-base font-semibold">{title}</h2>
        <button aria-label="Close" onClick={() => ref.current?.close()} className="rounded p-1 text-muted hover:text-text"><X size={18} /></button>
      </div>
      <div className="px-5 py-4">{children}</div>
    </dialog>
  );
}

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      aria-label={`${label} to clipboard`}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setDone(true);
          setTimeout(() => setDone(false), 1200);
        } catch {
          /* clipboard blocked: nothing to do */
        }
      }}
      className="inline-flex items-center gap-1 rounded-md border border-border bg-surface px-2 py-0.5 text-xs text-muted hover:text-text">
      {done ? <Check size={12} /> : <Copy size={12} />} {done ? "Copied" : label}
    </button>
  );
}

export function CypherBlock({ cypher, write }: { cypher: string; write?: boolean }) {
  const text = pretty(cypher);
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-code">
      <div className="flex items-center gap-2 border-b border-border px-2.5 py-1 text-[11px] text-muted">
        <span className="font-medium">Cypher</span>
        {write && <span className="chip-mem rounded px-1.5 py-px text-[10px] font-semibold">WRITE</span>}
        <span className="ml-auto"><CopyButton text={text} /></span>
      </div>
      <pre className="cy-code scroll-thin max-h-64 overflow-auto p-3 font-mono text-[12px] leading-[1.55] whitespace-pre-wrap break-words">
        {tokenize(text).map((t, i) => (t.c ? <span key={i} className={t.c}>{t.t}</span> : t.t))}
      </pre>
    </div>
  );
}

export function JsonBlock({ value, max = 1500 }: { value: unknown; max?: number }) {
  const s = typeof value === "string" ? value : JSON.stringify(value, null, 1);
  return (
    <pre className="scroll-thin max-h-48 overflow-auto rounded-lg border border-border bg-code p-3 font-mono text-[11.5px] leading-[1.5] whitespace-pre-wrap break-words text-text">
      {s.length > max ? s.slice(0, max) + " …" : s}
    </pre>
  );
}

const LABEL_NAMES: Record<string, string> = { ChatThread: "Chat", PublicPostmortem: "Public postmortem", Doc: "Doc", Ticket: "Ticket" };

export function SourceCard({ s, onOpen }: { s: Source; onOpen?: (id: string) => void }) {
  return (
    <figure className="rounded-lg border border-border bg-surface-2 p-3" data-testid="source-card">
      <figcaption className="mb-1 flex items-center gap-2 text-xs">
        <span className="rounded bg-surface px-1.5 py-0.5 font-medium text-muted ring-1 ring-border">{LABEL_NAMES[s.label] || s.label}</span>
        <span className="min-w-0 flex-1 truncate font-medium">{s.title}</span>
      </figcaption>
      {s.excerpt && <blockquote className="border-l-2 border-accent pl-2 text-[13px] leading-snug">“{s.excerpt}”</blockquote>}
      <div className="mt-1.5 font-mono text-[11px] text-muted">
        {onOpen ? <button className="underline-offset-2 hover:underline" onClick={() => onOpen(s.id)}>{s.id}</button> : s.id}
      </div>
    </figure>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden="true" />;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="grid h-full place-items-center p-6 text-center">
      <div className="max-w-sm">
        <p className="font-medium">{title}</p>
        {children && <div className="mt-1 text-sm text-muted">{children}</div>}
      </div>
    </div>
  );
}

export const AGENT_LANE: Record<string, { name: string; cls: string; dot: string }> = {
  triage: { name: "Triage", cls: "text-triage", dot: "bg-triage" },
  investigator: { name: "Investigator", cls: "text-investigator", dot: "bg-investigator" },
  communicator: { name: "Communicator", cls: "text-communicator", dot: "bg-communicator" },
  brain: { name: "Brain", cls: "text-investigator", dot: "bg-investigator" },
};
