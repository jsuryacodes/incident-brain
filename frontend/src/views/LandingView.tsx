// The landing page: the entry into the console. Every number here is quoted from docs/eval.md or docs/progress.md
// (see NUMBERS below) — nothing is invented, and no seed service/person/ticket name appears on this page.
import { ArrowRight, Bell, Brain, Check, Code2, FileSearch, Laptop, Map, Moon, Network, Play, Shield, Sun, Users } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Glyph } from "../components/Header";
import { CypherBlock } from "../components/ui";
import { useApp } from "../lib/store";
import { useTheme } from "../lib/theme";

const REPO = "https://github.com/jsuryacodes/incident-brain";
// Build-time wiring. Served by FastAPI: both unset -> the button switches to the console view in this app.
// Vercel static build: VITE_STATIC=1 -> "Open the console" goes to the "Run it yourself" section unless
// VITE_CONSOLE_URL points at a real deployment.
const CONSOLE_URL = import.meta.env.VITE_CONSOLE_URL as string | undefined;
const STATIC = import.meta.env.VITE_STATIC === "1";
const DEMO_VIDEO = import.meta.env.VITE_DEMO_URL as string | undefined;

/** docs/eval.md, "Scores" -> scenario library (hand-written), the 15 hand-written scenarios. */
const PROFILES = [
  { name: "Full Incident Brain", what: "every tool: traversals, graph algorithms, full-text, memory", solved: 15, cause: 19, leads: 8, paged: 19, wrong: 0, tone: "ok" },
  { name: "Graph, no algorithms", what: "traversals and full-text only — no PageRank, betweenness or shortest paths", solved: 12, cause: 16, leads: 7, paged: 16, wrong: 13, tone: "mid" },
  { name: "No graph", what: "full-text over docs and chats, a service list and a flat change log", solved: 0, cause: 13, leads: 5, paged: 7, wrong: 15, tone: "bad" },
] as const;

/** docs/progress.md 08C: GET /api/storm/latest — naive 6/6/5 vs agent 2/2/2, 5 pages suppressed, 35 tool calls. */
const STORM = { alerts: 6, naiveIncidents: 6, naivePages: 6, naiveWoken: 5, incidents: 2, pages: 2, suppressed: 5, calls: 35 };

/* ─────────────────────────────── bits ─────────────────────────────── */

/** Reveal on scroll, once. Reduced motion keeps everything visible (see .ib-rev in styles.css). */
function useReveal<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || shown) return;
    if (!("IntersectionObserver" in window)) return setShown(true);
    const io = new IntersectionObserver(([e]) => e.isIntersecting && (setShown(true), io.disconnect()), { rootMargin: "0px 0px -12% 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, [shown]);
  return [ref, shown] as const;
}

/** Phase clock for the looping hero animation and the stepper. Stops at `hold` when motion is reduced. */
function usePhase(count: number, ms: number, hold = count - 1) {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return setI(hold);
    const t = setInterval(() => setI((p) => (p + 1) % count), ms);
    return () => clearInterval(t);
  }, [count, ms, hold]);
  return [i, setI] as const;
}

function Section({ id, eyebrow, title, lead, children, tint }: {
  id?: string; eyebrow?: string; title?: string; lead?: string; children: React.ReactNode; tint?: boolean;
}) {
  const [ref, shown] = useReveal<HTMLDivElement>();
  return (
    <section id={id} className={tint ? "border-y border-border bg-surface/60" : undefined}>
      <div ref={ref} className={`ib-rev ${shown ? "in" : ""} mx-auto w-full max-w-6xl px-4 py-14 sm:px-6 sm:py-20 lg:py-24`}>
        {eyebrow && <p className="mb-3 text-xs font-semibold tracking-[0.14em] text-muted uppercase">{eyebrow}</p>}
        {title && <h2 className="max-w-3xl text-2xl font-semibold tracking-tight sm:text-3xl lg:text-4xl">{title}</h2>}
        {lead && <p className="mt-4 max-w-2xl text-base text-muted sm:text-lg">{lead}</p>}
        <div className={title || lead ? "mt-10" : undefined}>{children}</div>
      </div>
    </section>
  );
}

function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`card p-5 sm:p-6 ${className}`}>{children}</div>;
}

/* ───────────────────────── hero graph animation ───────────────────────── */

// 12 services. No names: the shapes are the point, and seed names stay out of the frontend.
const N = [
  { x: 60, y: 48 }, { x: 150, y: 30 }, { x: 246, y: 44 }, { x: 330, y: 92 },
  { x: 36, y: 132 }, { x: 128, y: 120 }, { x: 222, y: 128 }, { x: 310, y: 176 },
  { x: 70, y: 214 }, { x: 160, y: 208 }, { x: 250, y: 226 }, { x: 128, y: 290 },
];
const EDGES: [number, number][] = [
  [0, 1], [1, 2], [2, 3], [0, 5], [1, 5], [2, 6], [3, 7], [4, 5], [5, 6], [6, 7],
  [4, 8], [5, 9], [6, 10], [8, 9], [9, 10], [10, 7], [9, 11], [11, 8],
];
const PATH = [1, 5, 9, 11]; // alert -> cause, hop by hop
const LEARNED: [number, number] = [11, 6]; // the dashed amber edge an agent wrote

function HeroGraph() {
  // 0 calm · 1 alert · 2 ripple · 3-5 path hops · 6 cause · 7 learned · 8 hold
  const [p] = usePhase(9, 1150, 7);
  const alert = p >= 1;
  const hops = p <= 2 ? 0 : Math.min(p - 2, PATH.length - 1); // lit path segments
  const litNodes = new Set(p >= 3 ? PATH.slice(0, hops + 1) : alert ? [PATH[0]] : []);
  const cause = p >= 6;
  const learned = p >= 7;
  const onPath = (a: number, b: number) => {
    for (let i = 0; i < hops; i++) if ((PATH[i] === a && PATH[i + 1] === b) || (PATH[i] === b && PATH[i + 1] === a)) return true;
    return false;
  };
  const label = ["Everything is fine.", "An alarm fires.", "The ripple spreads.", "Walk the roads…", "…one hop…", "…then the next…",
    "Here is the real cause.", "Remember it: a new road.", "Next time, instant."][p];
  return (
    <div className="relative">
      <div aria-hidden className="pointer-events-none absolute -inset-10 -z-10 rounded-full opacity-60 blur-3xl"
        style={{ background: "radial-gradient(45% 45% at 55% 40%, var(--accent-soft), transparent 70%)" }} />
      <svg viewBox="0 0 380 330" className="h-auto w-full" role="img"
        aria-label="A dependency graph: one service alerts, the agent follows the dependency path to the real cause, then records a learned dependency.">
        <g>
          {EDGES.map(([a, b]) => {
            const lit = onPath(a, b);
            return <line key={`${a}-${b}`} x1={N[a].x} y1={N[a].y} x2={N[b].x} y2={N[b].y} className="ib-edge"
              stroke={lit ? "var(--accent)" : "var(--edge)"} strokeWidth={lit ? 2.6 : 1.2} opacity={lit ? 1 : 0.75} />;
          })}
          {/* the learned edge draws itself in, then stays */}
          <line x1={N[LEARNED[0]].x} y1={N[LEARNED[0]].y} x2={N[LEARNED[1]].x} y2={N[LEARNED[1]].y}
            stroke="var(--mem-stroke)" strokeWidth={2.2} strokeDasharray="6 5" className="ib-learned"
            style={{ opacity: learned ? 1 : 0, strokeDashoffset: learned ? 0 : 120 }} />
          {N.map((n, i) => {
            const isAlert = i === PATH[0] && alert;
            const isCause = i === PATH[PATH.length - 1] && cause;
            const lit = litNodes.has(i);
            return (
              <g key={i}>
                {isAlert && <circle cx={n.x} cy={n.y} r="9" className="ib-ripple" fill="none" stroke="var(--alert)" strokeWidth="2" />}
                <circle cx={n.x} cy={n.y} r={isAlert || isCause ? 9.5 : 7} className="ib-node"
                  fill={isAlert ? "var(--alert)" : isCause ? "var(--accent)" : lit ? "var(--accent-soft)" : "var(--node)"}
                  stroke={isAlert ? "var(--alert)" : lit || isCause ? "var(--accent)" : "var(--node-stroke)"} strokeWidth="1.6" />
              </g>
            );
          })}
          {alert && <text x={N[PATH[0]].x + 14} y={N[PATH[0]].y - 8} className="ib-tag" fill="var(--alert)">alert</text>}
          {cause && <text x={N[PATH[3]].x + 14} y={N[PATH[3]].y + 18} className="ib-tag" fill="var(--accent)">cause</text>}
          {learned && <text x={N[LEARNED[1]].x + 12} y={N[LEARNED[1]].y - 10} className="ib-tag" fill="var(--mem-stroke)">learned</text>}
        </g>
      </svg>
      <p aria-live="off" className="mt-1 h-5 text-center font-mono text-xs text-muted">{label}</p>
    </div>
  );
}

/* ─────────────────────────────── page ─────────────────────────────── */

export default function LandingView() {
  const setView = useApp((s) => s.setView);
  const { pref, cycle } = useTheme();
  const ThemeIcon = pref === "system" ? Laptop : pref === "light" ? Sun : Moon;
  const openConsole = () => {
    if (CONSOLE_URL) location.href = CONSOLE_URL;
    else if (STATIC) document.getElementById("run")?.scrollIntoView({ behavior: "smooth" });
    else setView("story");
  };
  return (
    // The console views fill the viewport; the landing page scrolls the document instead (sticky header, anchors).
    <div className="min-h-full overflow-x-clip bg-bg" data-testid="landing">
      <header className="sticky top-0 z-20 border-b border-border/70 bg-bg/85 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3 sm:px-6">
          <span className="flex items-center gap-2 font-semibold tracking-tight"><Glyph /> Incident Brain</span>
          <span className="ml-auto hidden text-xs text-muted sm:inline">FalkorDB · Track 1</span>
          <button onClick={cycle} aria-label={`Theme: ${pref}. Click to change.`} data-testid="theme-toggle"
            className="rounded-md border border-border p-1.5 text-muted hover:text-text"><ThemeIcon size={15} /></button>
          <a href={REPO} target="_blank" rel="noreferrer" aria-label="Repository"
            className="rounded-md border border-border p-1.5 text-muted hover:text-text"><Code2 size={15} /></a>
          <button onClick={openConsole} data-testid="open-console-top"
            className="rounded-md bg-text px-3 py-1.5 text-sm font-medium text-bg">Open the console</button>
        </div>
      </header>

      {/* 1 · hero */}
      <div className="mx-auto grid max-w-6xl items-center gap-10 px-4 pt-12 pb-10 sm:px-6 sm:pt-20 lg:grid-cols-[1.05fr_1fr] lg:gap-14 lg:pt-24">
        <div className="fade-in">
          <p className="mb-5 inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1 text-xs text-muted">
            <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: "var(--alert)" }} />
            An agent team for the first hour of an incident
          </p>
          <h1 className="text-[2rem] leading-[1.08] font-semibold tracking-tight sm:text-5xl lg:text-[3.4rem]">
            When something breaks at 3&nbsp;a.m., Incident Brain finds out why — <span className="text-accent">and shows its work.</span>
          </h1>
          <p className="mt-5 max-w-xl text-base text-muted sm:text-lg">
            It keeps a map of how a company's software fits together, walks that map when an alarm fires, names the change that
            caused it, wakes the one right person, and writes down what it learned.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <button onClick={openConsole} data-testid="open-console"
              className="inline-flex items-center gap-2 rounded-lg bg-text px-5 py-2.5 font-medium text-bg shadow-sm hover:opacity-90">
              Open the console <ArrowRight size={16} />
            </button>
            <a href="#how" className="inline-flex items-center gap-2 rounded-lg border border-border bg-surface px-5 py-2.5 font-medium hover:bg-surface-2">
              See how it works
            </a>
          </div>
          <p className="mt-6 max-w-xl text-xs leading-relaxed text-muted">
            The agent decisions shown here run on a deterministic rule planner (mock mode). An LLM planner is built and
            swappable, but was not run live for this submission.
          </p>
        </div>
        <HeroGraph />
      </div>

      {/* 2 · the problem */}
      <Section tint eyebrow="The problem" title="Nobody can hold the whole company in their head."
        lead="A company's software is hundreds of small programs calling each other. When one breaks, the first hour goes on figuring out where to even look.">
        <div className="grid gap-5 sm:grid-cols-3">
          {[
            { icon: Bell, t: "Dozens of alarms, one cause", d: "One broken piece sets off everything that depends on it. The screen fills with alarms that are all the same problem." },
            { icon: Users, t: "The person who built it left", d: "The obvious owner changed teams or quit. Who to wake at 3 a.m. is a guess." },
            { icon: FileSearch, t: "The reason is in an old chat", d: "Why something was built that way is buried in a message from a year ago that nobody can find." },
          ].map(({ icon: I, t, d }) => (
            <Card key={t}>
              <I size={20} className="text-accent" />
              <h3 className="mt-3 font-semibold">{t}</h3>
              <p className="mt-2 text-sm text-muted">{d}</p>
            </Card>
          ))}
        </div>
      </Section>

      {/* 3 · track 1 */}
      <TrackOne />

      {/* 4 · how it works */}
      <HowItWorks />

      {/* 5 · alert storm */}
      <Storm />

      {/* 6 · why a graph */}
      <WhyGraph />

      {/* 7 · receipts */}
      <Receipts />

      {/* 8 · under the hood */}
      <UnderTheHood />

      {/* 9 · tracks 2 and 3 */}
      <Section eyebrow="Also covers" title="Tracks 2 and 3, on the same graph.">
        <div className="grid gap-5 md:grid-cols-2">
          <Card>
            <Brain size={20} className="text-mem" />
            <h3 className="mt-3 font-semibold">Track 2: Agent Memory and Coordination</h3>
            <p className="mt-2 text-sm text-muted">
              Three agents (Triage, Investigator, Communicator) hand off through one shared incident node in the graph, not
              through a chat log. What a session learns is written back as graph edges, in amber, so a later session starts
              from it. Each company is its own isolated graph, so memory never leaks between tenants.
            </p>
          </Card>
          <Card>
            <Network size={20} className="text-accent" />
            <h3 className="mt-3 font-semibold">Track 3: Company Brain</h3>
            <p className="mt-2 text-sm text-muted">
              Ask the Brain answers questions about the company — decisions, owners, documents, past incidents — with the exact
              source text quoted back, and warns when the person it names has left. The Explorer view shows the whole graph,
              with everything an agent wrote highlighted.
            </p>
          </Card>
        </div>
      </Section>

      {/* 10 · CTA + run it yourself */}
      <Section id="run" tint eyebrow="Try it" title="Open the console.">
        <div className="grid gap-6 lg:grid-cols-[1.1fr_1fr]">
          <Card>
            <p className="text-sm text-muted">Five views: the <b className="text-text">Story</b> replay of a full incident,
              the <b className="text-text">Firefighter</b> you can point at any alert, the <b className="text-text">Eval</b> table,
              <b className="text-text"> Ask the Brain</b>, and the graph <b className="text-text">Explorer</b>.</p>
            <div className="mt-5 flex flex-wrap gap-3">
              <button onClick={openConsole} data-testid="open-console-bottom"
                className="inline-flex items-center gap-2 rounded-lg bg-text px-5 py-2.5 font-medium text-bg hover:opacity-90">
                Open the console <ArrowRight size={16} />
              </button>
              <a href={REPO} target="_blank" rel="noreferrer"
                className="inline-flex items-center gap-2 rounded-lg border border-border bg-surface px-5 py-2.5 font-medium hover:bg-surface-2">
                <Code2 size={16} /> Read the code
              </a>
              {DEMO_VIDEO && (
                <a href={DEMO_VIDEO} target="_blank" rel="noreferrer"
                  className="inline-flex items-center gap-2 rounded-lg border border-border bg-surface px-5 py-2.5 font-medium hover:bg-surface-2">
                  <Play size={16} /> Watch the demo
                </a>
              )}
            </div>
          </Card>
          <Card>
            <h3 className="font-semibold">Run it yourself</h3>
            <p className="mt-2 text-sm text-muted">The console needs the graph database and the API, so it runs locally. Two commands:</p>
            <pre className="mt-3 overflow-x-auto rounded-md bg-code p-3 font-mono text-xs"><code>{"scripts/setup.sh\nscripts/ui.sh   # → http://localhost:8000"}</code></pre>
            {!DEMO_VIDEO && <p className="mt-3 text-xs text-muted">A recorded walkthrough will be linked here.</p>}
          </Card>
        </div>
        <p className="mt-8 max-w-3xl text-xs leading-relaxed text-muted">
          Honest note: the agent decisions on this page and in the console run on a deterministic rule planner (mock mode) — no
          model calls, no cost, identical every time. An LLM planner is built and swappable behind the same interface; it was
          not run live for this submission.
        </p>
      </Section>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-5 gap-y-2 px-4 py-8 text-xs text-muted sm:px-6">
          <span className="flex items-center gap-2 font-medium text-text"><Glyph size={16} /> Incident Brain</span>
          <span>Built on FalkorDB</span>
          <a className="hover:text-text" href={REPO} target="_blank" rel="noreferrer">Repository</a>
          <a className="hover:text-text" href={`${REPO}/blob/main/docs/eval.md`} target="_blank" rel="noreferrer">Eval</a>
          <a className="hover:text-text" href={`${REPO}/blob/main/docs/schema.md`} target="_blank" rel="noreferrer">Graph schema</a>
          <span className="ml-auto">Track 1: Agents That Act on Connected Data</span>
        </div>
      </footer>
    </div>
  );
}

/* ───────────────────────────── sections ───────────────────────────── */

const TRACK1 = [
  ["Multi-hop reasoning", "Follows dependency paths up to 6 hops to the change that explains the alert."],
  ["Graph queries and algorithms as tools", "22 fixed, parameterised read tools: traversals, shortest paths, PageRank, betweenness, components, communities, full-text."],
  ["Tool selection via MCP", "The same registry is an MCP server (stdio and HTTP), so the tools are selectable from outside the app."],
  ["Acts on the graph", "Pages the right person, opens a ticket, flags a stale document, records what it learned — each write a graph edge."],
  ["Explainable results", "Every step keeps the exact Cypher it ran, the path it walked and the source it quoted."],
] as const;

function TrackOne() {
  const [ref, shown] = useReveal<HTMLDivElement>();
  return (
    <section>
      <div ref={ref} className={`ib-rev ${shown ? "in" : ""} mx-auto w-full max-w-6xl px-4 py-14 sm:px-6 sm:py-20 lg:py-24`}>
        <p className="mb-3 text-xs font-semibold tracking-[0.14em] text-muted uppercase">The challenge</p>
        <h2 className="max-w-3xl text-2xl font-semibold tracking-tight sm:text-3xl lg:text-4xl">
          Track 1: Agents That Act on Connected Data
        </h2>
        <p className="mt-4 max-w-2xl text-base text-muted sm:text-lg">What the track asks for, and where it is in this project.</p>
        <ul className="mt-10 divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
          {TRACK1.map(([ask, how], i) => (
            <li key={ask} className="grid gap-2 p-4 sm:grid-cols-[minmax(0,19rem)_1fr] sm:items-center sm:gap-6 sm:p-5">
              <span className="font-medium">{ask}</span>
              <span className={`ib-tick ${shown ? "in" : ""} flex items-start gap-2 text-sm text-muted`} style={{ transitionDelay: `${180 + i * 170}ms` }}>
                <Check size={16} className="mt-0.5 shrink-0 text-ok" aria-hidden />
                <span>{how}</span>
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

const STEPS = [
  { icon: Bell, t: "An alarm fires", d: "One service starts failing. That is all the agent is told." },
  { icon: Map, t: "Walk the map", d: "It follows the roads out of the broken building: who it depends on, who depends on it, how far the damage can reach." },
  { icon: FileSearch, t: "Line up suspects", d: "Every candidate change goes on a board: confirmed, still open, or rejected — each with the evidence that decided it." },
  { icon: Shield, t: "Act safely", d: "It wakes the one right person, opens a ticket, and holds back a risky rollback until a human approves it." },
  { icon: Brain, t: "Remember", d: "What it learned — a hidden dependency, the fix — becomes a new road on the map. Next time the answer is already there." },
] as const;

function HowItWorks() {
  const [i, setI] = usePhase(STEPS.length, 3600, 0);
  return (
    <Section id="how" tint eyebrow="How it works" title="Think of the company as a city map."
      lead="The buildings are services. The roads are who-depends-on-whom. Incident Brain is a detective that walks the roads instead of guessing.">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,22rem)_1fr]">
        <ol className="relative flex gap-2 overflow-x-auto pb-2 lg:block lg:overflow-visible lg:pb-0">
          {STEPS.map(({ icon: I, t }, n) => (
            <li key={t} className="lg:relative">
              <button onClick={() => setI(n)} aria-current={i === n ? "step" : undefined}
                className={`flex w-full min-w-44 items-center gap-3 rounded-lg border px-3 py-2.5 text-left text-sm transition-colors lg:min-w-0 ${
                  i === n ? "border-accent bg-accent-soft font-medium" : "border-transparent text-muted hover:bg-surface-2"}`}>
                <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-xs ${
                  i === n ? "border-accent text-accent" : "border-border"}`}>{n + 1}</span>
                <I size={15} className="shrink-0" aria-hidden /> <span className="truncate">{t}</span>
              </button>
            </li>
          ))}
        </ol>
        <Card className="min-h-52">
          <p className="font-mono text-xs text-muted">step {i + 1} of {STEPS.length}</p>
          <h3 className="mt-2 text-xl font-semibold tracking-tight sm:text-2xl">{STEPS[i].t}</h3>
          <p className="mt-3 max-w-xl text-base text-muted">{STEPS[i].d}</p>
          <div className="mt-6 h-1 w-full overflow-hidden rounded-full bg-surface-2">
            <div className="h-full rounded-full bg-accent transition-[width] duration-500" style={{ width: `${((i + 1) / STEPS.length) * 100}%` }} />
          </div>
        </Card>
      </div>
    </Section>
  );
}

function Storm() {
  const [ref, shown] = useReveal<HTMLDivElement>();
  return (
    <section>
      <div ref={ref} className={`ib-rev ${shown ? "in" : ""} mx-auto w-full max-w-6xl px-4 py-14 sm:px-6 sm:py-20 lg:py-24`}>
        <p className="mb-3 text-xs font-semibold tracking-[0.14em] text-muted uppercase">The alert storm</p>
        <h2 className="max-w-3xl text-2xl font-semibold tracking-tight sm:text-3xl lg:text-4xl">
          {STORM.alerts} alarms at once. {STORM.pages} people woken instead of {STORM.naiveWoken}.
        </h2>
        <p className="mt-4 max-w-2xl text-base text-muted sm:text-lg">
          Most of a storm is one problem seen from several places. The agent groups the alarms that share a root, pages once per
          real incident, and suppresses the rest <i>with the reason</i> — the path that makes each one downstream of another.
        </p>
        <div className="mt-10 grid items-center gap-6 md:grid-cols-[1fr_auto_1fr]">
          <Card>
            <p className="text-xs font-medium text-muted uppercase">Alarms in</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {Array.from({ length: STORM.alerts }, (_, n) => (
                <span key={n} className="ib-storm-dot flex h-9 w-9 items-center justify-center rounded-lg border text-xs"
                  style={{ borderColor: "var(--alert)", background: "var(--alert-soft)", color: "var(--alert)", animationDelay: `${n * 90}ms` }}>
                  <Bell size={14} />
                </span>
              ))}
            </div>
            <p className="mt-4 text-sm text-muted">Page every alarm and you get <b className="text-text">{STORM.naiveIncidents} incidents, {STORM.naivePages} pages, {STORM.naiveWoken} people woken.</b></p>
          </Card>
          <ArrowRight className="mx-auto hidden text-muted md:block" aria-hidden />
          <Card>
            <p className="text-xs font-medium text-muted uppercase">Incidents out</p>
            <div className="mt-3 space-y-2">
              <div className="rounded-lg border border-border bg-surface-2 p-3 text-sm">
                <b>Incident 1</b> · 5 alarms, one shared dependency that is saturated — one page to the right person.
              </div>
              <div className="rounded-lg border border-border bg-surface-2 p-3 text-sm">
                <b>Incident 2</b> · 1 alarm that reaches none of the others, with its own change — its own page.
              </div>
            </div>
            <p className="mt-4 text-sm text-muted">{STORM.suppressed} pages suppressed, each with the path that explains it. {STORM.calls} tool calls in total.</p>
          </Card>
        </div>
      </div>
    </section>
  );
}

const METRICS = [
  { key: "solved", label: "Scenarios solved", max: 15 },
  { key: "cause", label: "Causes right", max: 19 },
  { key: "leads", label: "False leads rejected", max: 8 },
  { key: "paged", label: "Right person paged", max: 19 },
] as const;

function WhyGraph() {
  const [ref, shown] = useReveal<HTMLDivElement>();
  const tone = { ok: "var(--ok)", mid: "var(--accent)", bad: "var(--alert)" } as const;
  return (
    <section className="border-y border-border bg-surface/60">
      <div ref={ref} className={`ib-rev ${shown ? "in" : ""} mx-auto w-full max-w-6xl px-4 py-14 sm:px-6 sm:py-20 lg:py-24`}>
        <p className="mb-3 text-xs font-semibold tracking-[0.14em] text-muted uppercase">Why a graph?</p>
        <h2 className="max-w-3xl text-2xl font-semibold tracking-tight sm:text-3xl lg:text-4xl">We took the graph away and measured.</h2>
        <p className="mt-4 max-w-3xl text-base text-muted sm:text-lg">
          Same planner, same loop, same report format, same grounding checks — only the tools change, across 15 hand-written
          incident scenarios. Scored by an independent oracle, not by the agent.
        </p>
        <div className="mt-10 grid gap-5 lg:grid-cols-3">
          {PROFILES.map((p) => (
            <Card key={p.name}>
              <div className="flex items-baseline justify-between gap-3">
                <h3 className="font-semibold">{p.name}</h3>
                <span className="font-mono text-sm" style={{ color: tone[p.tone] }}>{p.solved}/15</span>
              </div>
              <p className="mt-1.5 text-xs text-muted">{p.what}</p>
              <dl className="mt-5 space-y-3">
                {METRICS.map((m) => (
                  <div key={m.key}>
                    <div className="flex justify-between text-xs">
                      <dt className="text-muted">{m.label}</dt>
                      <dd className="font-mono">{p[m.key]}/{m.max}</dd>
                    </div>
                    <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-2">
                      <div className="h-full rounded-full transition-[width] duration-[900ms] ease-out"
                        style={{ width: shown ? `${(p[m.key] / m.max) * 100}%` : 0, background: tone[p.tone], transitionDelay: "150ms" }} />
                    </div>
                  </div>
                ))}
              </dl>
              <p className="mt-4 border-t border-border pt-3 text-xs text-muted">
                Wrong actions recommended: <b className={p.wrong ? "text-alert" : "text-ok"}>{p.wrong}</b>
              </p>
            </Card>
          ))}
        </div>
        <p className="mt-6 max-w-3xl text-xs leading-relaxed text-muted">
          Without the graph, nothing can produce a dependency path, so no scenario passes; it still guesses a cause from text
          and a change log, and it pages the wrong person. Without the algorithms, traversals find the same answer on ordinary
          incidents — the three it loses are the alert storms, where it has no way to correlate alarms and pages per alarm.
          Two more sets run the same way: 50 generated scenarios (full 50/50, no graph 0/50) and 6 written by an agent that
          never saw the planner (full 6/6, no graph 0/6).
        </p>
      </div>
    </section>
  );
}

const RECEIPT_CYPHER = `MATCH p = (a:Service {id: $alert})-[:DEPENDS_ON*1..$hops]->(s:Service)
MATCH (s)<-[:TARGETS]-(d:Deploy)
WHERE d.at >= $since
RETURN s.id AS service, d.id AS deploy, d.at AS at,
       length(p) AS hops, [n IN nodes(p) | n.id] AS path
ORDER BY hops ASC, d.at DESC`;

function Receipts() {
  return (
    <Section eyebrow="No black boxes" title="Every answer comes with its receipt."
      lead="Each step of every run keeps the tool it chose, why it chose it, the exact Cypher it ran, the path it walked and the text it quoted. Judges can check any claim.">
      <div className="grid gap-5 lg:grid-cols-[1.15fr_1fr]">
        <Card>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="rounded-full bg-accent-soft px-2 py-0.5 font-medium text-accent">step 4</span>
            <span className="font-mono text-muted">recent_changes_downstream</span>
            <span className="text-muted">· 12 ms</span>
          </div>
          <p className="mt-3 text-sm"><b>Why this tool:</b> the alarm has no change of its own, so look for a change on anything
            it depends on, nearest hop first.</p>
          <div className="mt-4"><CypherBlock cypher={RECEIPT_CYPHER} /></div>
          <p className="mt-3 text-xs text-muted">Example receipt, in the shape the console renders. Live receipts carry the run's
            real parameters and results.</p>
        </Card>
        <div className="space-y-5">
          <Card>
            <p className="text-xs font-medium text-muted uppercase">The path it walked</p>
            <svg viewBox="0 0 320 60" className="mt-3 h-auto w-full" role="img" aria-label="Four services in a chain, from the alerting one to the cause.">
              {[0, 1, 2].map((i) => <line key={i} x1={40 + i * 80} y1="30" x2={112 + i * 80} y2="30" stroke="var(--accent)" strokeWidth="2.4" />)}
              {[0, 1, 2, 3].map((i) => (
                <circle key={i} cx={32 + i * 80} cy="30" r={i === 0 || i === 3 ? 11 : 8}
                  fill={i === 0 ? "var(--alert)" : i === 3 ? "var(--accent)" : "var(--accent-soft)"}
                  stroke={i === 0 ? "var(--alert)" : "var(--accent)"} strokeWidth="1.6" />
              ))}
              <text x="32" y="55" textAnchor="middle" className="ib-tag" fill="var(--alert)">alert</text>
              <text x="272" y="55" textAnchor="middle" className="ib-tag" fill="var(--accent)">cause</text>
            </svg>
            <p className="mt-2 text-sm text-muted">Three hops from the alarm to the change. Nothing else on the path changed in the window.</p>
          </Card>
          <Card className="border-l-2" >
            <p className="text-xs font-medium text-muted uppercase">The source it quoted</p>
            <blockquote className="mt-3 border-l-2 pl-3 text-sm italic" style={{ borderColor: "var(--mem-stroke)" }}>
              “…we dropped the retry budget on that dependency last quarter and never updated the runbook.”
            </blockquote>
            <p className="mt-2 text-xs text-muted">Verbatim from a chat message in the graph, with its node id — illustrative text, in the shape the console quotes.</p>
          </Card>
        </div>
      </div>
    </Section>
  );
}

const HOOD = [
  ["FalkorDB", "The primary store, not a cache. One isolated graph per company, so no query can cross tenants."],
  ["22 read tools + 10 write tools", "Fixed, parameterised Cypher. The agent picks the tool and the arguments; it never writes raw queries."],
  ["Graph algorithms", "algo.BFS · algo.SPpaths · algo.SSpaths · algo.pageRank · algo.betweenness · algo.WCC · algo.labelPropagation (CDLP) · full-text search."],
  ["MCP server", "The same registry over stdio and HTTP, so the tools are usable from any MCP client."],
  ["Multi-agent team", "Triage, Investigator and Communicator share one incident node: the hand-off is graph state, not a transcript."],
  ["Memory across sessions", "Learned dependencies, facts, resolutions and runbooks are written back as edges and reused later."],
] as const;

function UnderTheHood() {
  return (
    <Section tint eyebrow="Under the hood" title="For the judges.">
      <div className="grid gap-5 lg:grid-cols-[1fr_minmax(0,22rem)]">
        <dl className="grid gap-5 sm:grid-cols-2">
          {HOOD.map(([t, d]) => (
            <Card key={t}>
              <dt className="font-semibold">{t}</dt>
              <dd className="mt-2 text-sm text-muted">{d}</dd>
            </Card>
          ))}
        </dl>
        <Card>
          <p className="text-xs font-medium text-muted uppercase">Architecture</p>
          <svg viewBox="0 0 322 300" className="mt-3 h-auto w-full" role="img"
            aria-label="Architecture: the console, CLI and MCP clients call the agent loop, which calls the tool registry, which queries FalkorDB.">
            {[
              { y: 16, t: "Console · CLI · MCP clients", fill: "var(--surface-2)" },
              { y: 86, t: "Agent loop · rule or LLM planner", fill: "var(--accent-soft)" },
              { y: 156, t: "Tool registry · 22 read + 10 write", fill: "var(--surface-2)" },
              { y: 226, t: "FalkorDB · one graph per company", fill: "var(--surface-2)" },
            ].map((b, i) => (
              <g key={b.y}>
                <rect x="14" y={b.y} width="272" height="52" rx="10" fill={b.fill} stroke="var(--border)" />
                <text x="150" y={b.y + 31} textAnchor="middle" className="ib-tag" fill="var(--text)">{b.t}</text>
                {i < 3 && <path d={`M150 ${b.y + 52} l0 12 m-5 -5 l5 6 l5 -6`} stroke="var(--edge)" strokeWidth="1.6" fill="none" />}
              </g>
            ))}
            <path d="M292 234 q22 -92 0 -184" stroke="var(--mem-stroke)" strokeWidth="1.6" strokeDasharray="5 4" fill="none" />
            <text x="-150" y="318" transform="rotate(-90)" textAnchor="middle" className="ib-tag" fill="var(--mem-stroke)">receipts</text>
          </svg>
        </Card>
      </div>
    </Section>
  );
}
