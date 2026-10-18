import { Info, KeyRound, Laptop, LockOpen, Moon, Sun } from "lucide-react";
import { useCallback, useState } from "react";
import { useApp, type View } from "../lib/store";
import { useTheme } from "../lib/theme";
import { Dialog } from "./ui";

const REPO = "https://github.com/jsuryacodes/incident-brain";
const TABS: { id: View; label: string }[] = [
  { id: "story", label: "Story" },
  { id: "firefighter", label: "Firefighter" },
  { id: "eval", label: "Eval" },
  { id: "brain", label: "Ask the Brain" },
  { id: "explorer", label: "Explorer" },
];

export function Glyph({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="var(--text)" />
      <path d="M10 11 22 10M10 11 16 22M22 10 16 22" stroke="var(--bg)" strokeWidth="1.8" fill="none" />
      <circle cx="10" cy="11" r="3.3" fill="var(--accent)" />
      <circle cx="22" cy="10" r="3.3" fill="var(--bg)" />
      <circle cx="16" cy="22" r="3.7" fill="var(--mem-stroke)" />
    </svg>
  );
}

export function Header() {
  const { view, setView, tenant, setTenant, meta, unlocked } = useApp();
  const { pref, cycle } = useTheme();
  const [dialog, setDialog] = useState<"code" | "about" | null>(null);
  const close = useCallback(() => setDialog(null), []);
  const ThemeIcon = pref === "system" ? Laptop : pref === "light" ? Sun : Moon;
  const mode = unlocked ? (meta?.llm_modes.includes("live") ? "Mock · live available" : "Mock") : "Replay";
  return (
    <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border bg-surface px-4 py-2">
      <a href="/" onClick={(e) => (e.preventDefault(), setView("story"))} className="flex items-center gap-2 font-semibold tracking-tight">
        <Glyph /> <span>Incident Brain</span>
      </a>
      <nav aria-label="Views" className="flex rounded-lg bg-surface-2 p-0.5">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setView(t.id)} aria-current={view === t.id ? "page" : undefined}
            className={`rounded-md px-3 py-1 text-sm ${view === t.id ? "bg-surface font-medium shadow-sm" : "text-muted hover:text-text"}`}>
            {t.label}
          </button>
        ))}
      </nav>
      <div className="ml-auto flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-1.5 text-sm text-muted">
          <span className="hidden sm:inline">Company</span>
          <select aria-label="Company (tenant)" value={tenant} onChange={(e) => setTenant(e.target.value)} data-testid="tenant"
            className="rounded-md border border-border bg-surface px-2 py-1 text-sm text-text">
            {(meta?.tenants || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </label>
        <span data-testid="mode-badge" title={unlocked ? "Access code accepted: story buttons start fresh mock runs that write to the graph." : "No access code: the story plays recorded runs (golden replays). Nothing is written."}
          className={`rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ${unlocked ? "bg-ok-soft text-ok ring-ok/30" : "bg-surface-2 text-muted ring-border"}`}>
          {mode}
        </span>
        <button onClick={() => setDialog("code")} aria-label={unlocked ? "Access code (unlocked)" : "Enter access code"}
          className="flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-sm text-muted hover:text-text">
          {unlocked ? <LockOpen size={15} /> : <KeyRound size={15} />} <span className="hidden md:inline">{unlocked ? "Unlocked" : "Access code"}</span>
        </button>
        <button onClick={cycle} aria-label={`Theme: ${pref}. Click to change.`} title={`Theme: ${pref}`} data-testid="theme-toggle"
          className="flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-sm text-muted hover:text-text">
          <ThemeIcon size={15} /> <span className="hidden md:inline capitalize">{pref}</span>
        </button>
        <button onClick={() => setDialog("about")} aria-label="About Incident Brain" className="rounded-md border border-border p-1.5 text-muted hover:text-text">
          <Info size={15} />
        </button>
      </div>
      {dialog === "code" && <CodeDialog onClose={close} />}
      {dialog === "about" && <AboutDialog onClose={close} />}
    </header>
  );
}

function CodeDialog({ onClose }: { onClose: () => void }) {
  const { unlocked, unlock, lock, meta } = useApp();
  const [code, setCodeText] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <Dialog title="Access code" onClose={onClose} labelledBy="code-title">
      {unlocked ? (
        <div className="space-y-3 text-sm">
          <p>Unlocked for this tab. Story buttons now start <b>fresh mock runs</b> that write to the graph, and Brain conversations are saved.</p>
          <button onClick={() => (lock(), onClose())} className="rounded-md border border-border px-3 py-1.5">Forget the code</button>
        </div>
      ) : (
        <form className="space-y-3 text-sm" onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setErr("");
          try {
            if (await unlock(code.trim())) onClose();
            else setErr("That code didn't work.");
          } catch (x) {
            setErr((x as Error).message);
          } finally {
            setBusy(false);
          }
        }}>
          <p className="text-muted">Without a code everything works on recorded runs and nothing is written. With the code, the
            story runs fresh (mock mode, free) and writes its memory to the graph.{meta && !meta.code_configured && " This server has no code set, so fresh runs are off."}</p>
          <label className="block">
            <span className="mb-1 block font-medium">Code</span>
            <input type="password" autoComplete="off" value={code} onChange={(e) => setCodeText(e.target.value)} autoFocus data-testid="code-input"
              className="w-full rounded-md border border-border bg-surface-2 px-3 py-2" />
          </label>
          {err && <p role="alert" className="text-alert">{err}</p>}
          <p className="text-xs text-muted">Kept in this tab only (sessionStorage) and sent as a request header.</p>
          <button disabled={!code.trim() || busy} className="rounded-md bg-text px-3 py-1.5 font-medium text-bg disabled:opacity-50">
            {busy ? "Checking…" : "Unlock"}
          </button>
        </form>
      )}
    </Dialog>
  );
}

function AboutDialog({ onClose }: { onClose: () => void }) {
  return (
    <Dialog title="About Incident Brain" onClose={onClose} labelledBy="about-title">
      <div className="space-y-3 text-sm">
        <p>Each company is one FalkorDB graph: services, people, deploys, docs, chats, decisions and past incidents. When an
          alert fires, three agents (Triage, Investigator, Communicator) find the cause by querying that graph, and every step is
          kept as a receipt with its exact Cypher. What they learn (a hidden dependency, the fix, a better runbook) is written back
          in amber, so the next incident is solved from memory.</p>
        <ul className="space-y-1.5">
          <li><b>Track 1: Agents That Act on Connected Data.</b> The Story view: agents walk dependency paths, run PageRank, page the right person, open tickets.</li>
          <li><b>Track 2: Agent Memory and Coordination.</b> Hand-offs through the graph, the learned edge, Session 2 recalling Session 1, tenant-separated memory.</li>
          <li><b>Track 3: Company Brain.</b> Ask the Brain: answers with verbatim sources; the Explorer shows the whole company graph.</li>
        </ul>
        <p className="flex flex-wrap gap-3">
          <a className="text-accent underline" href="/welcome" onClick={(e) => (e.preventDefault(), onClose(), useApp.getState().setView("landing"))}>Landing page</a>
          <a className="text-accent underline" href={REPO} target="_blank" rel="noreferrer">Repository</a>
          <a className="text-accent underline" href={`${REPO}#readme`} target="_blank" rel="noreferrer">README</a>
          <a className="text-accent underline" href={`${REPO}/blob/main/docs/explain.md`} target="_blank" rel="noreferrer">How it works</a>
          <a className="text-accent underline" href={`${REPO}/blob/main/docs/schema.md`} target="_blank" rel="noreferrer">Graph schema</a>
        </p>
      </div>
    </Dialog>
  );
}
