// The landing page: the entry into the console. Every number here is quoted from docs/eval.md or docs/progress.md
// (see the constants below). No seed service, person or ticket name appears on this page, and the copy keeps to
// plain words: no dashes, no jargon in the first five sections.
import {
  ArrowRight, Bell, Brain, Check, ChevronLeft, ChevronRight, Code2, FileSearch, Map, Network, Pause, Play,
  RotateCcw, Shield, Ticket, Users, X,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Glyph } from "../components/Header";
import { ThemeSwitch } from "../components/ThemeSwitch";
import { CypherBlock, Dialog } from "../components/ui";
import { useApp } from "../lib/store";

const REPO = "https://github.com/jsuryacodes/incident-brain";
// Build-time wiring. Served by FastAPI, both are unset and the buttons open the console in this app.
// Vercel static build: VITE_STATIC=1, so there is no API and the buttons open the "Run the console" box instead.
const CONSOLE_URL = import.meta.env.VITE_CONSOLE_URL as string | undefined;
const STATIC = import.meta.env.VITE_STATIC === "1";
const DEMO_VIDEO = import.meta.env.VITE_DEMO_URL as string | undefined;

/** docs/eval.md, "Scores": the 15 hand written scenarios. */
const PROFILES = [
  { name: "Full Incident Brain", what: "every tool: walking the map, the graph algorithms, search and memory", solved: 15, cause: 19, leads: 8, paged: 19, wrong: 0, tone: "ok" },
  { name: "Graph, no algorithms", what: "it can still walk the map and search, but the algorithms are taken away", solved: 12, cause: 16, leads: 7, paged: 16, wrong: 13, tone: "mid" },
  { name: "No graph at all", what: "only search over documents and chats, a list of services and a list of changes", solved: 0, cause: 13, leads: 5, paged: 7, wrong: 15, tone: "bad" },
] as const;

/** docs/progress.md 08C, GET /api/storm/latest: naive 6/6/5 against the agent's 2/2/2, 5 pages held back, 35 calls. */
const STORM = { alerts: 6, naiveIncidents: 6, naivePages: 6, naiveWoken: 5, incidents: 2, pages: 2, suppressed: 5, calls: 35 };

const SPEEDS = [0.5, 1, 2] as const;
const reducedMotion = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

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

/** One stage at a time, with play, pause, step and speed. `loop` wraps round; otherwise it stops on the last stage. */
function usePlayer(count: number, baseMs: number, { loop = false, autostart = true } = {}) {
  const [i, setI] = useState(0);
  const [playing, setPlaying] = useState(autostart && !reducedMotion());
  const [speed, setSpeed] = useState<number>(1);
  useEffect(() => {
    if (!playing) return;
    const t = setTimeout(() => {
      setI((p) => {
        if (p + 1 < count) return p + 1;
        if (loop) return 0;
        setPlaying(false);
        return p;
      });
    }, baseMs / speed);
    return () => clearTimeout(t);
  }, [playing, i, speed, count, baseMs, loop]);
  const go = useCallback((n: number) => {
    setPlaying(false);
    setI(loop ? (n + count) % count : Math.max(0, Math.min(count - 1, n)));
  }, [count, loop]);
  return { i, setI, playing, setPlaying, speed, setSpeed, go };
}

type Player = ReturnType<typeof usePlayer>;

function Controls({ p, restart, compact }: { p: Player; restart?: () => void; compact?: boolean }) {
  const btn = "flex items-center gap-1 rounded-md border border-border bg-surface px-2 py-1 text-xs text-muted hover:text-text";
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <button onClick={() => p.setPlaying(!p.playing)} className={btn} aria-label={p.playing ? "Pause" : "Play"} data-testid="play">
        {p.playing ? <Pause size={13} /> : <Play size={13} />}{!compact && <span>{p.playing ? "Pause" : "Play"}</span>}
      </button>
      <button onClick={() => p.go(p.i - 1)} className={btn} aria-label="Previous" data-testid="prev"><ChevronLeft size={13} />{!compact && <span>Back</span>}</button>
      <button onClick={() => p.go(p.i + 1)} className={btn} aria-label="Next" data-testid="next"><ChevronRight size={13} />{!compact && <span>Next</span>}</button>
      {restart && <button onClick={restart} className={btn} aria-label="Restart" data-testid="restart"><RotateCcw size={13} />{!compact && <span>Restart</span>}</button>}
      <span className="ml-1 flex rounded-md bg-surface-2 p-0.5" role="group" aria-label="Speed">
        {SPEEDS.map((s) => (
          <button key={s} onClick={() => p.setSpeed(s)} aria-pressed={p.speed === s} data-testid={`speed-${s}`}
            className={`rounded px-1.5 py-0.5 text-xs ${p.speed === s ? "bg-surface font-medium shadow-sm" : "text-muted hover:text-text"}`}>
            {s}&times;
          </button>
        ))}
      </span>
    </div>
  );
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

// 12 services. No names: the shape is the point, and the seed's names stay out of the frontend.
const N = [
  { x: 60, y: 48 }, { x: 150, y: 30 }, { x: 246, y: 44 }, { x: 330, y: 92 },
  { x: 36, y: 132 }, { x: 128, y: 120 }, { x: 222, y: 128 }, { x: 310, y: 176 },
  { x: 70, y: 214 }, { x: 160, y: 208 }, { x: 250, y: 226 }, { x: 128, y: 290 },
];
const EDGES: [number, number][] = [
  [0, 1], [1, 2], [2, 3], [0, 5], [1, 5], [2, 6], [3, 7], [4, 5], [5, 6], [6, 7],
  [4, 8], [5, 9], [6, 10], [8, 9], [9, 10], [10, 7], [9, 11], [11, 8],
];
const PATH = [1, 5, 9, 11]; // the alarm, then each hop, then the cause
const LEARNED: [number, number] = [11, 6]; // the dashed amber road an agent wrote down

const HERO_CAPTIONS = [
  "Hundreds of services. Each one calls the next.",
  "An alarm goes off on one service.",
  "The trouble spreads to everything that calls it.",
  "The agent follows the roads, one hop at a time.",
  "Still going. Every hop is a real query.",
  "One more hop.",
  "It finds the change that broke things.",
  "It writes down the road it learned.",
  "Next time, this answer is already there.",
];

function HeroGraph() {
  const p = usePlayer(HERO_CAPTIONS.length, 1500, { loop: true });
  const { i } = p;
  const alert = i >= 1;
  const hops = i <= 2 ? 0 : Math.min(i - 2, PATH.length - 1);
  const litNodes = new Set(i >= 3 ? PATH.slice(0, hops + 1) : alert ? [PATH[0]] : []);
  const cause = i >= 6;
  const learned = i >= 7;
  const onPath = (a: number, b: number) => {
    for (let n = 0; n < hops; n++) if ((PATH[n] === a && PATH[n + 1] === b) || (PATH[n] === b && PATH[n + 1] === a)) return true;
    return false;
  };
  return (
    <div className="relative">
      <div aria-hidden className="pointer-events-none absolute -inset-10 -z-10 rounded-full opacity-60 blur-3xl"
        style={{ background: "radial-gradient(45% 45% at 55% 40%, var(--accent-soft), transparent 70%)" }} />
      <svg viewBox="0 0 380 330" className="h-auto w-full" role="img"
        aria-label="A map of services. One of them starts alarming, the agent follows the roads to the change that caused it, then writes down a road it did not know about.">
        {EDGES.map(([a, b]) => {
          const lit = onPath(a, b);
          return <line key={`${a}-${b}`} x1={N[a].x} y1={N[a].y} x2={N[b].x} y2={N[b].y} className="ib-edge"
            stroke={lit ? "var(--accent)" : "var(--edge)"} strokeWidth={lit ? 2.6 : 1.2} opacity={lit ? 1 : 0.75} />;
        })}
        <line x1={N[LEARNED[0]].x} y1={N[LEARNED[0]].y} x2={N[LEARNED[1]].x} y2={N[LEARNED[1]].y}
          stroke="var(--mem-stroke)" strokeWidth={2.2} strokeDasharray="6 5" className="ib-learned"
          style={{ opacity: learned ? 1 : 0, strokeDashoffset: learned ? 0 : 120 }} />
        {N.map((n, k) => {
          const isAlert = k === PATH[0] && alert;
          const isCause = k === PATH[PATH.length - 1] && cause;
          const lit = litNodes.has(k);
          return (
            <g key={k}>
              {isAlert && <circle cx={n.x} cy={n.y} r="9" className="ib-ripple" fill="none" stroke="var(--alert)" strokeWidth="2" />}
              <circle cx={n.x} cy={n.y} r={isAlert || isCause ? 9.5 : 7} className="ib-node"
                fill={isAlert ? "var(--alert)" : isCause ? "var(--accent)" : lit ? "var(--accent-soft)" : "var(--node)"}
                stroke={isAlert ? "var(--alert)" : lit || isCause ? "var(--accent)" : "var(--node-stroke)"} strokeWidth="1.6" />
            </g>
          );
        })}
        {alert && <text x={N[PATH[0]].x + 14} y={N[PATH[0]].y - 8} className="ib-tag" fill="var(--alert)">alarm</text>}
        {cause && <text x={N[PATH[3]].x + 14} y={N[PATH[3]].y + 18} className="ib-tag" fill="var(--accent)">cause</text>}
        {learned && <text x={N[LEARNED[1]].x + 12} y={N[LEARNED[1]].y - 10} className="ib-tag" fill="var(--mem-stroke)">learned</text>}
      </svg>
      <div className="mt-2 flex flex-col items-center gap-2">
        <p data-testid="hero-caption" className="min-h-10 max-w-sm text-center text-sm text-muted">{HERO_CAPTIONS[i]}</p>
        <Controls p={p} compact />
      </div>
    </div>
  );
}

/* ─────────────────────────────── page ─────────────────────────────── */

export default function LandingView() {
  const setView = useApp((s) => s.setView);
  const [runOpen, setRunOpen] = useState(false);
  const openConsole = () => {
    if (CONSOLE_URL) location.href = CONSOLE_URL;
    else if (STATIC) setRunOpen(true);
    else setView("firefighter");
  };
  return (
    <div className="min-h-full overflow-x-clip bg-bg" data-testid="landing">
      <header className="sticky top-0 z-20 border-b border-border/70 bg-bg/85 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3 sm:px-6">
          <span className="flex items-center gap-2 font-semibold tracking-tight"><Glyph /> Incident Brain</span>
          <nav aria-label="Sections" className="ml-auto hidden items-center gap-4 text-sm text-muted md:flex">
            <a href="#how" className="hover:text-text">How it works</a>
            <a href="#demo" className="hover:text-text">The demo company</a>
            <a href="#why" className="hover:text-text">Why a graph</a>
          </nav>
          <ThemeSwitch />
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
            An agent team for the first hour of an outage
          </p>
          <h1 className="text-[2rem] leading-[1.08] font-semibold tracking-tight sm:text-5xl lg:text-[3.4rem]">
            When something breaks at 3&nbsp;a.m., Incident Brain finds out why, <span className="text-accent">and shows its work.</span>
          </h1>
          <p className="mt-5 max-w-xl text-base text-muted sm:text-lg">
            It keeps a map of how a company's software fits together. When an alarm goes off it walks that map, names the
            change that broke things, wakes the one right person, and writes down what it learned.
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
            To be straight with you: the agent decisions you see here are made by a set of fixed rules, not by a language
            model. We built the language model version too and it can be swapped in, but we did not run it live for this entry.
          </p>
        </div>
        <HeroGraph />
      </div>

      {/* 2 · the problem */}
      <Section tint eyebrow="The problem" title="Nobody can hold a whole company in their head."
        lead="A big company runs hundreds of small programs that call each other. When one of them breaks, the first hour goes on working out where to even look.">
        <div className="grid gap-5 sm:grid-cols-3">
          {[
            { icon: Bell, t: "One fault, dozens of alarms", d: "Everything that was counting on the broken piece starts complaining at the same time. The screen fills up and it all looks urgent." },
            { icon: Users, t: "The person who built it has left", d: "The obvious owner changed team or quit a year ago. At 3 a.m. nobody is sure who to wake." },
            { icon: FileSearch, t: "The reason is in an old chat", d: "Why a thing was built that way sits in a message from last year that nobody can find any more." },
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

      {/* 4b · the demo company */}
      <DemoCompany />

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
              Three agents work the incident: one sorts the alarms, one investigates, one writes it up. They hand over
              through a single incident record in the graph, not through a chat log. What one session learns is saved as
              part of the map, so a later session starts from it. Each company has its own graph, so nothing leaks across.
            </p>
          </Card>
          <Card>
            <Network size={20} className="text-accent" />
            <h3 className="mt-3 font-semibold">Track 3: Company Brain</h3>
            <p className="mt-2 text-sm text-muted">
              Ask the Brain answers questions about the company, like who owns a thing, why it was built that way, what
              happened last time. It quotes the exact source text back at you, and it warns you when the person it names
              has left. The Explorer view shows the whole map, with everything an agent wrote in amber.
            </p>
          </Card>
        </div>
      </Section>

      {/* 10 · CTA */}
      <Section id="run" tint eyebrow="Try it" title="Open the console.">
        <div className="grid gap-6 lg:grid-cols-[1.1fr_1fr]">
          <Card>
            <p className="text-sm text-muted">Five views: the <b className="text-text">Story</b> of a real incident played
              back step by step, the <b className="text-text">Firefighter</b> you can point at any alarm,
              the <b className="text-text">Eval</b> table, <b className="text-text">Ask the Brain</b>, and the
              graph <b className="text-text">Explorer</b>.</p>
            <div className="mt-5 flex flex-wrap gap-3">
              <button onClick={openConsole} data-testid="open-console-bottom"
                className="inline-flex items-center gap-2 rounded-lg bg-text px-5 py-2.5 font-medium text-bg hover:opacity-90">
                Open the console <ArrowRight size={16} />
              </button>
              <a href={REPO} target="_blank" rel="noreferrer"
                className="inline-flex items-center gap-2 rounded-lg border border-border bg-surface px-5 py-2.5 font-medium hover:bg-surface-2">
                <Code2 size={16} /> Read the code
              </a>
            </div>
          </Card>
          <RunPanel />
        </div>
        <p className="mt-8 max-w-3xl text-xs leading-relaxed text-muted">
          Honest note: the agent decisions on this page and in the console are made by a set of fixed rules in mock mode.
          No model is called, nothing is charged, and the same question always gives the same answer. The language model
          planner is built and can be swapped in behind the same interface. We did not run it live for this entry.
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

      {runOpen && (
        <Dialog title="Run the console" onClose={() => setRunOpen(false)} labelledBy="run-title">
          <div className="space-y-4 text-sm" data-testid="run-dialog">
            <p className="text-muted">The console needs the graph database and the API, so it runs on your machine, not here.
              Two commands and it is up:</p>
            <pre className="overflow-x-auto rounded-md bg-code p-3 font-mono text-xs"><code>{"scripts/setup.sh\nscripts/ui.sh"}</code></pre>
            <p className="text-muted">Then open <span className="font-mono text-text">http://localhost:8000</span>.</p>
            <div className="flex flex-wrap gap-3">
              <a href={REPO} target="_blank" rel="noreferrer" data-testid="run-repo"
                className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-1.5 font-medium hover:bg-surface-2">
                <Code2 size={15} /> GitHub repository
              </a>
              {DEMO_VIDEO ? (
                <a href={DEMO_VIDEO} target="_blank" rel="noreferrer" data-testid="run-video"
                  className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-1.5 font-medium hover:bg-surface-2">
                  <Play size={15} /> Watch the demo
                </a>
              ) : (
                <span data-testid="run-video" className="inline-flex items-center gap-2 rounded-lg border border-dashed border-border px-3 py-1.5 text-muted">
                  <Play size={15} /> Video coming soon
                </span>
              )}
            </div>
          </div>
        </Dialog>
      )}
    </div>
  );
}

/** The same instructions, always on the page, so the modal is never the only place they live. */
function RunPanel() {
  return (
    <Card>
      <h3 className="font-semibold">Run it yourself</h3>
      <p className="mt-2 text-sm text-muted">The console needs the graph database and the API, so it runs on your machine.
        Two commands:</p>
      <pre className="mt-3 overflow-x-auto rounded-md bg-code p-3 font-mono text-xs"><code>{"scripts/setup.sh\nscripts/ui.sh"}</code></pre>
      <p className="mt-3 text-sm text-muted">Then open <span className="font-mono text-text">http://localhost:8000</span>.</p>
      {!DEMO_VIDEO && <p className="mt-3 text-xs text-muted">A recorded walk through will be linked here.</p>}
    </Card>
  );
}

/* ───────────────────────────── sections ───────────────────────────── */

const TRACK1 = [
  ["Reasoning over many steps", "It follows the chain of who calls who, up to six steps out, until it reaches the change that explains the alarm."],
  ["Graph queries and algorithms as its tools", "It has 22 ready made queries to pick from, including shortest paths, importance scores and clustering. It never writes a raw query itself."],
  ["Picking its tools through MCP", "The same set of tools is served over MCP, so any MCP client can use them, not just our app."],
  ["Doing something with what it finds", "It wakes the right person, opens a ticket, marks an out of date document, and saves what it learned. Each of those is a change to the graph."],
  ["Showing why it believes it", "Every step keeps the query it ran, the route it walked and the sentence it quoted. You can check any claim."],
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
        <p className="mt-4 max-w-2xl text-base text-muted sm:text-lg">
          The track asks for an agent that works on data where the links matter, and that can show how it got there. Here is
          what it asks for, and how we do each one.
        </p>
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

/* ───────────────────── how it works: the 5 step player ───────────────────── */

function Alarm() {
  return (
    <svg viewBox="0 0 320 150" className="h-auto w-full" role="img" aria-label="One service on the map turns red and starts alarming.">
      {[[60, 40], [160, 30], [250, 60], [95, 110], [200, 115]].map(([x, y], i) => (
        <g key={i}>
          <circle cx={x} cy={y} r={i === 1 ? 14 : 10} fill={i === 1 ? "var(--alert)" : "var(--node)"}
            stroke={i === 1 ? "var(--alert)" : "var(--node-stroke)"} strokeWidth="1.6" />
          {i === 1 && <circle cx={x} cy={y} r="14" className="ib-ripple" fill="none" stroke="var(--alert)" strokeWidth="2" />}
        </g>
      ))}
      <line x1="60" y1="40" x2="160" y2="30" stroke="var(--edge)" strokeWidth="1.4" />
      <line x1="160" y1="30" x2="250" y2="60" stroke="var(--edge)" strokeWidth="1.4" />
      <line x1="95" y1="110" x2="160" y2="30" stroke="var(--edge)" strokeWidth="1.4" />
      <line x1="200" y1="115" x2="250" y2="60" stroke="var(--edge)" strokeWidth="1.4" />
    </svg>
  );
}

function Walk() {
  const xs = [34, 110, 186, 262];
  return (
    <svg viewBox="0 0 320 150" className="h-auto w-full" role="img" aria-label="A route lights up one hop at a time, from the alarming service to the cause.">
      {xs.slice(0, 3).map((x, i) => (
        <line key={i} x1={x + 12} y1="70" x2={xs[i + 1] - 12} y2="70" stroke="var(--accent)" strokeWidth="2.6"
          className="ib-draw" style={{ animationDelay: `${0.5 + i * 0.8}s` }} />
      ))}
      {xs.map((x, i) => (
        <circle key={x} cx={x} cy="70" r={i === 0 || i === 3 ? 13 : 10}
          fill={i === 0 ? "var(--alert)" : "var(--accent-soft)"} stroke={i === 0 ? "var(--alert)" : "var(--accent)"} strokeWidth="1.6"
          className="ib-pop" style={{ animationDelay: `${i * 0.8}s` }} />
      ))}
      <text x="34" y="105" textAnchor="middle" className="ib-tag" fill="var(--alert)">alarm</text>
      <text x="262" y="105" textAnchor="middle" className="ib-tag ib-pop" style={{ animationDelay: "2.4s" }} fill="var(--accent)">cause</text>
    </svg>
  );
}

const SUSPECTS = [
  { t: "A change next door", s: "ruled out", why: "nothing on the route calls it", bad: true },
  { t: "A newer change elsewhere", s: "ruled out", why: "the broken service cannot reach it", bad: true },
  { t: "A change three steps down", s: "confirmed", why: "on the route, and the timing fits", bad: false },
];

function Suspects() {
  return (
    <div className="space-y-2">
      {SUSPECTS.map((s, i) => (
        <div key={s.t} className="ib-pop flex items-start gap-3 rounded-lg border border-border bg-surface-2 p-3" style={{ animationDelay: `${i * 0.7}s` }}>
          <span className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${s.bad ? "bg-alert-soft text-alert" : "bg-ok-soft text-ok"}`}>
            {s.bad ? <X size={12} /> : <Check size={12} />}
          </span>
          <span className="min-w-0">
            <b className={`text-sm ${s.bad ? "line-through opacity-70" : ""}`}>{s.t}</b>
            <span className={`ml-2 text-xs ${s.bad ? "text-alert" : "text-ok"}`}>{s.s}</span>
            <span className="block text-xs text-muted">{s.why}</span>
          </span>
        </div>
      ))}
    </div>
  );
}

const ACTIONS = [
  { icon: Bell, t: "Paged one person", d: "the person who knows this service and is still here", tone: "ok" },
  { icon: Ticket, t: "Opened a ticket", d: "with the route, the change and the evidence attached", tone: "ok" },
  { icon: Shield, t: "Rollback on hold", d: "this one is risky, so it waits until a person approves", tone: "mem" },
];

function Act() {
  return (
    <div className="space-y-2">
      {ACTIONS.map((a, i) => (
        <div key={a.t} className="ib-pop flex items-start gap-3 rounded-lg border border-border bg-surface-2 p-3" style={{ animationDelay: `${i * 0.7}s` }}>
          <a.icon size={16} className={a.tone === "ok" ? "mt-0.5 text-ok" : "mt-0.5 text-mem"} />
          <span>
            <b className="text-sm">{a.t}</b>
            <span className="block text-xs text-muted">{a.d}</span>
          </span>
        </div>
      ))}
    </div>
  );
}

function Remember() {
  return (
    <svg viewBox="0 0 320 150" className="h-auto w-full" role="img" aria-label="A new dashed road is drawn between two services and kept for next time.">
      <line x1="70" y1="50" x2="240" y2="50" stroke="var(--edge)" strokeWidth="1.4" />
      <line x1="70" y1="50" x2="240" y2="110" stroke="var(--mem-stroke)" strokeWidth="2.4" strokeDasharray="7 5"
        className="ib-draw" style={{ animationDelay: "0.4s" }} />
      {[[70, 50], [240, 50], [240, 110]].map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r="11" fill="var(--node)" stroke="var(--node-stroke)" strokeWidth="1.6" />
      ))}
      <text x="155" y="135" textAnchor="middle" className="ib-tag ib-pop" style={{ animationDelay: "1.4s" }} fill="var(--mem-stroke)">
        remembered for next time
      </text>
    </svg>
  );
}

const STEPS = [
  { icon: Bell, t: "An alarm goes off", art: Alarm,
    lines: ["One service starts failing. That is all the agent is told.", "No cause, no owner, no hint about where to look."] },
  { icon: Map, t: "Walk the map", art: Walk,
    lines: ["It follows the roads out of the broken building: what it leans on, what leans on it.", "Each hop is a real query against the graph, not a guess."] },
  { icon: FileSearch, t: "Line up the suspects", art: Suspects,
    lines: ["Every recent change goes on a board.", "Ones the alarm cannot reach are crossed out, with the reason written next to them.", "What is left has to fit both the route and the timing."] },
  { icon: Shield, t: "Act, but safely", art: Act,
    lines: ["It wakes one person, the one who knows this service and is still at the company.", "It opens a ticket with the evidence.", "If undoing the change looks risky, it stops and waits for a human to say yes."] },
  { icon: Brain, t: "Remember it", art: Remember,
    lines: ["The road it did not know about is saved on the map.", "So is the fix, and what turned out to be a dead end.", "Next time the same thing happens, the answer is already there."] },
] as const;

function HowItWorks() {
  const [ref, shown] = useReveal<HTMLDivElement>();
  const p = usePlayer(STEPS.length, 4200, { autostart: false });
  const { setPlaying } = p;
  const started = useRef(false);
  useEffect(() => {
    if (shown && !started.current && !reducedMotion()) (started.current = true), setPlaying(true);
  }, [shown, setPlaying]);
  const step = STEPS[p.i];
  const Art = step.art;
  return (
    <section id="how" className="border-y border-border bg-surface/60">
      <div ref={ref} className={`ib-rev ${shown ? "in" : ""} mx-auto w-full max-w-6xl px-4 py-14 sm:px-6 sm:py-20 lg:py-24`}>
        <p className="mb-3 text-xs font-semibold tracking-[0.14em] text-muted uppercase">How it works</p>
        <h2 className="max-w-3xl text-2xl font-semibold tracking-tight sm:text-3xl lg:text-4xl">Think of the company as a city map.</h2>
        <p className="mt-4 max-w-2xl text-base text-muted sm:text-lg">
          The buildings are services. The roads show which one calls which. Incident Brain is a detective that walks the
          roads instead of guessing.
        </p>
        <div className="mt-10 grid gap-6 lg:grid-cols-[minmax(0,21rem)_1fr]"
          tabIndex={0} data-testid="stepper" aria-label="How it works, five steps"
          onKeyDown={(e) => {
            if (e.key === " ") (e.preventDefault(), p.setPlaying(!p.playing));
            else if (e.key === "ArrowLeft") (e.preventDefault(), p.go(p.i - 1));
            else if (e.key === "ArrowRight") (e.preventDefault(), p.go(p.i + 1));
          }}>
          <div>
            <ol className="flex gap-2 overflow-x-auto pb-2 lg:block lg:space-y-1 lg:overflow-visible lg:pb-0">
              {STEPS.map(({ icon: I, t }, n) => (
                <li key={t}>
                  <button onClick={() => p.go(n)} aria-current={p.i === n ? "step" : undefined} data-testid={`step-${n + 1}`}
                    className={`flex w-full min-w-44 items-center gap-3 rounded-lg border px-3 py-2.5 text-left text-sm transition-colors lg:min-w-0 ${
                      p.i === n ? "border-accent bg-accent-soft font-medium" : "border-transparent text-muted hover:bg-surface-2"}`}>
                    <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-xs ${
                      p.i === n ? "border-accent text-accent" : "border-border"}`}>{n + 1}</span>
                    <I size={15} className="shrink-0" aria-hidden /> <span className="truncate">{t}</span>
                  </button>
                </li>
              ))}
            </ol>
            <div className="mt-4"><Controls p={p} restart={() => (p.setI(0), p.setPlaying(true))} /></div>
          </div>
          <Card>
            <p className="font-mono text-xs text-muted">step {p.i + 1} of {STEPS.length}</p>
            <h3 className="mt-2 text-xl font-semibold tracking-tight sm:text-2xl" data-testid="step-title">{step.t}</h3>
            <div key={p.i} className="mt-5 min-h-40 rounded-lg border border-border bg-bg p-4"><Art /></div>
            <div className="mt-4 space-y-1.5 text-sm text-muted">{step.lines.map((l) => <p key={l}>{l}</p>)}</div>
            <div className="mt-5 h-1 w-full overflow-hidden rounded-full bg-surface-2">
              <div className="h-full rounded-full bg-accent transition-[width] duration-500" style={{ width: `${((p.i + 1) / STEPS.length) * 100}%` }} />
            </div>
          </Card>
        </div>
      </div>
    </section>
  );
}

function Storm() {
  const [ref, shown] = useReveal<HTMLDivElement>();
  return (
    <section>
      <div ref={ref} className={`ib-rev ${shown ? "in" : ""} mx-auto w-full max-w-6xl px-4 py-14 sm:px-6 sm:py-20 lg:py-24`}>
        <p className="mb-3 text-xs font-semibold tracking-[0.14em] text-muted uppercase">The alarm storm</p>
        <h2 className="max-w-3xl text-2xl font-semibold tracking-tight sm:text-3xl lg:text-4xl">
          {STORM.alerts} alarms at once. {STORM.pages} people woken instead of {STORM.naiveWoken}.
        </h2>
        <p className="mt-4 max-w-2xl text-base text-muted sm:text-lg">
          Most of a storm is one problem seen from several places. The agent groups the alarms that share a root, pages
          once for each real problem, and holds the rest back. For every one it holds back it writes down why.
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
            <p className="mt-4 text-sm text-muted">Page every alarm and you get <b className="text-text">{STORM.naiveIncidents} problems, {STORM.naivePages} pages, {STORM.naiveWoken} people woken.</b></p>
          </Card>
          <ArrowRight className="mx-auto hidden text-muted md:block" aria-hidden />
          <Card>
            <p className="text-xs font-medium text-muted uppercase">Real problems out</p>
            <div className="mt-3 space-y-2">
              <div className="rounded-lg border border-border bg-surface-2 p-3 text-sm">
                <b>Problem 1.</b> Five alarms, all leaning on the same overloaded service. One page.
              </div>
              <div className="rounded-lg border border-border bg-surface-2 p-3 text-sm">
                <b>Problem 2.</b> One alarm that touches none of the others, with a change of its own. Its own page.
              </div>
            </div>
            <p className="mt-4 text-sm text-muted">{STORM.suppressed} pages held back, each with the route that explains it. {STORM.calls} tool calls in all.</p>
          </Card>
        </div>
      </div>
    </section>
  );
}

const METRICS = [
  { key: "solved", label: "Incidents solved", max: 15 },
  { key: "cause", label: "Causes found", max: 19 },
  { key: "leads", label: "Wrong leads thrown out", max: 8 },
  { key: "paged", label: "Right person woken", max: 19 },
] as const;

function WhyGraph() {
  const [ref, shown] = useReveal<HTMLDivElement>();
  const tone = { ok: "var(--ok)", mid: "var(--accent)", bad: "var(--alert)" } as const;
  return (
    <section id="why" className="border-y border-border bg-surface/60">
      <div ref={ref} className={`ib-rev ${shown ? "in" : ""} mx-auto w-full max-w-6xl px-4 py-14 sm:px-6 sm:py-20 lg:py-24`}>
        <p className="mb-3 text-xs font-semibold tracking-[0.14em] text-muted uppercase">Why a graph?</p>
        <h2 className="max-w-3xl text-2xl font-semibold tracking-tight sm:text-3xl lg:text-4xl">We took the map away and measured.</h2>
        <p className="mt-4 max-w-3xl text-base text-muted sm:text-lg">
          Same agent, same loop, same report, 15 written incidents. The only thing that changes is which tools it is
          allowed to use. The marking is done by a separate checker, not by the agent.
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
                Harmful things it suggested doing: <b className={p.wrong ? "text-alert" : "text-ok"}>{p.wrong}</b>
              </p>
            </Card>
          ))}
        </div>
        <p className="mt-6 max-w-3xl text-xs leading-relaxed text-muted">
          With no map, nothing can show a route, so no incident is fully solved. It still guesses a cause from text and a
          list of changes, and it wakes the wrong people. With the map but no algorithms, ordinary incidents come out the
          same. The three it loses are the alarm storms, where it has no way to group alarms and so pages for each one.
          Two more sets run the same way: 50 generated incidents (full 50 of 50, no graph 0 of 50) and 6 written by an
          agent that had never seen our planner (full 6 of 6, no graph 0 of 6).
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
    <Section eyebrow="Nothing is hidden" title="Every answer comes with its receipt."
      lead="Each step keeps the tool it picked, why it picked it, the query it ran, the route it walked and the sentence it quoted. Anyone can check any claim on this page.">
      <div className="grid gap-5 lg:grid-cols-[1.15fr_1fr]">
        <Card>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="rounded-full bg-accent-soft px-2 py-0.5 font-medium text-accent">step 4</span>
            <span className="font-mono text-muted">recent_changes_downstream</span>
            <span className="text-muted">· 12 ms</span>
          </div>
          <p className="mt-3 text-sm"><b>Why this tool:</b> the alarming service did not change itself, so look for a change
            on something it leans on, nearest first.</p>
          <div className="mt-4"><CypherBlock cypher={RECEIPT_CYPHER} /></div>
          <p className="mt-3 text-xs text-muted">An example receipt, in the shape the console draws. Real ones carry the
            run's own values and results.</p>
        </Card>
        <div className="space-y-5">
          <Card>
            <p className="text-xs font-medium text-muted uppercase">The route it walked</p>
            <svg viewBox="0 0 320 60" className="mt-3 h-auto w-full" role="img" aria-label="Four services in a line, from the alarming one to the cause.">
              {[0, 1, 2].map((i) => <line key={i} x1={40 + i * 80} y1="30" x2={112 + i * 80} y2="30" stroke="var(--accent)" strokeWidth="2.4" />)}
              {[0, 1, 2, 3].map((i) => (
                <circle key={i} cx={32 + i * 80} cy="30" r={i === 0 || i === 3 ? 11 : 8}
                  fill={i === 0 ? "var(--alert)" : i === 3 ? "var(--accent)" : "var(--accent-soft)"}
                  stroke={i === 0 ? "var(--alert)" : "var(--accent)"} strokeWidth="1.6" />
              ))}
              <text x="32" y="55" textAnchor="middle" className="ib-tag" fill="var(--alert)">alarm</text>
              <text x="272" y="55" textAnchor="middle" className="ib-tag" fill="var(--accent)">cause</text>
            </svg>
            <p className="mt-2 text-sm text-muted">Three hops from the alarm to the change. Nothing else on that route changed.</p>
          </Card>
          <Card>
            <p className="text-xs font-medium text-muted uppercase">The source it quoted</p>
            <blockquote className="mt-3 border-l-2 pl-3 text-sm italic" style={{ borderColor: "var(--mem-stroke)" }}>
              “…we cut the retry budget on that dependency last quarter and never updated the runbook.”
            </blockquote>
            <p className="mt-2 text-xs text-muted">Word for word from a chat message in the graph, with the id of the message.
              The wording here is made up for the example; the console quotes the real thing.</p>
          </Card>
        </div>
      </div>
    </Section>
  );
}

const HOOD = [
  ["FalkorDB", "The main store, not a cache. One separate graph per company, so no query can reach another company's data."],
  ["22 read tools and 10 write tools", "Fixed queries with slots for values. The agent picks a tool and fills the slots. It never writes a query itself."],
  ["Graph algorithms", "algo.BFS, algo.SPpaths, algo.SSpaths, algo.pageRank, algo.betweenness, algo.WCC, algo.labelPropagation (CDLP), and full text search."],
  ["MCP server", "The same tools over stdio and HTTP, so any MCP client can use them."],
  ["A team of agents", "Triage, Investigator and Communicator share one incident record. The handover is graph state, not a transcript."],
  ["Memory between sessions", "Roads it learned, facts, fixes and runbooks are written back and used again later."],
] as const;

function UnderTheHood() {
  return (
    <Section tint eyebrow="Under the hood" title="The technical details.">
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
            aria-label="The console, the command line and MCP clients call the agent loop. The loop calls the tool registry, which queries FalkorDB.">
            {[
              { y: 16, t: "Console · CLI · MCP clients", fill: "var(--surface-2)" },
              { y: 86, t: "Agent loop · rules or a model", fill: "var(--accent-soft)" },
              { y: 156, t: "Tools · 22 read + 10 write", fill: "var(--surface-2)" },
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

/* ──────────────────── meet the demo company ──────────────────── */

// Every figure below is counted from the seeded Kestrel Pay graph, and the story is the one planted in
// docs/schema.md §7. The data is made up; the company does not exist.
const KESTREL = [
  ["27", "services"], ["43", "links between them"], ["20", "people"], ["4", "teams"],
  ["38", "recent changes"], ["12", "documents"], ["10", "team chats"], ["19", "tickets"],
  ["5", "written decisions"], ["8", "past incidents"], ["4", "runbooks"],
] as const;

// The real dependency shape around the incident, simplified: checkout at the top, the rules service at the
// bottom, and the config service that nobody wrote down.
const DEMO_NODES: Record<string, { x: number; y: number; label: string }> = {
  checkout: { x: 60, y: 30, label: "checkout" },
  gateway: { x: 60, y: 86, label: "api gateway" },
  payments: { x: 60, y: 142, label: "payments" },
  fraud: { x: 60, y: 198, label: "fraud scoring" },
  rules: { x: 60, y: 254, label: "rules" },
  config: { x: 232, y: 254, label: "config" },
  rulesdb: { x: 232, y: 198, label: "rules store" },
  payouts: { x: 232, y: 142, label: "payouts" },
};
const DEMO_EDGES: [string, string][] = [
  ["checkout", "gateway"], ["gateway", "payments"], ["payments", "fraud"], ["fraud", "rules"],
  ["rules", "rulesdb"], ["payouts", "config"],
];

function DemoMap({ stage }: { stage: number }) {
  // 0 the map · 1 the change lands · 2 the hidden road appears · 3 the alarm goes off upstream
  const lit = stage >= 1;
  const hidden = stage >= 2;
  const alarm = stage >= 3;
  const onChain = (a: string, b: string) =>
    lit && [["payments", "fraud"], ["fraud", "rules"]].some(([x, y]) => x === a && y === b);
  return (
    <svg viewBox="0 0 300 290" className="h-auto w-full" role="img"
      aria-label="A small map of the demo company. A change lands on the rules service, an undeclared link to the config service appears, and the payments service starts alarming two hops above.">
      {DEMO_EDGES.map(([a, b]) => (
        <line key={`${a}${b}`} x1={DEMO_NODES[a].x} y1={DEMO_NODES[a].y} x2={DEMO_NODES[b].x} y2={DEMO_NODES[b].y}
          className="ib-edge" stroke={onChain(a, b) ? "var(--accent)" : "var(--edge)"} strokeWidth={onChain(a, b) ? 2.6 : 1.3} />
      ))}
      {hidden && (
        <line x1={DEMO_NODES.rules.x} y1={DEMO_NODES.rules.y} x2={DEMO_NODES.config.x} y2={DEMO_NODES.config.y}
          stroke="var(--mem-stroke)" strokeWidth="2.4" strokeDasharray="7 5" className="ib-draw" />
      )}
      {Object.entries(DEMO_NODES).map(([k, n]) => {
        const isChange = k === "rules" && lit;
        const isAlarm = k === "payments" && alarm;
        const isHot = k === "config" && hidden;
        return (
          <g key={k}>
            {isAlarm && <circle cx={n.x} cy={n.y} r="10" className="ib-ripple" fill="none" stroke="var(--alert)" strokeWidth="2" />}
            <circle cx={n.x} cy={n.y} r={isAlarm || isChange ? 10 : 7.5} className="ib-node"
              fill={isAlarm ? "var(--alert)" : isChange ? "var(--accent)" : isHot ? "var(--mem-fill)" : "var(--node)"}
              stroke={isAlarm ? "var(--alert)" : isChange ? "var(--accent)" : isHot ? "var(--mem-stroke)" : "var(--node-stroke)"} strokeWidth="1.6" />
            <text x={n.x > 150 ? n.x - 13 : n.x + 13} y={n.y + 3.5} textAnchor={n.x > 150 ? "end" : "start"}
              className="ib-tag" fill="var(--muted)">{n.label}</text>
          </g>
        );
      })}
      {lit && <text x={DEMO_NODES.rules.x - 10} y={DEMO_NODES.rules.y + 26} className="ib-tag ib-pop" fill="var(--accent)">cache 300s to 5s</text>}
      {hidden && <text x="146" y="238" textAnchor="middle" className="ib-tag ib-pop" fill="var(--mem-stroke)">nobody wrote this down</text>}
      {alarm && <text x={DEMO_NODES.payments.x - 14} y={DEMO_NODES.payments.y - 14} className="ib-tag ib-pop" fill="var(--alert)">payments failing</text>}
    </svg>
  );
}

const FINDINGS = [
  { t: "It walks from the alarm down the chain",
    lines: ["The payments service is failing. Two hops below it sits a change from 40 minutes ago.",
      "A junior engineer cut a cache time from 300 seconds to 5, so rule edits would show up faster. Ticket RISK-412."] },
  { t: "It throws out the leads that cannot be the cause",
    lines: ["Another service was changed more recently, which looks worse at first glance.",
      "The payments service cannot reach it, so it is crossed out, with that reason written down.",
      "Each thrown out lead keeps the query that killed it."] },
  { t: "It finds the road nobody wrote down",
    lines: ["The catalogue says the rules service only talks to its own database.",
      "An old chat says otherwise: on every cache miss it also calls the config service.",
      "With a 5 second cache, almost every payment turns into another call to that one service."] },
  { t: "It digs up the decision everyone forgot",
    lines: ["A written decision says the cache must stay at 300 seconds or more.",
      "It came out of a chat in the risk engineering channel more than a year ago.",
      "The ticket from three days ago quietly contradicts it. Nobody noticed."] },
  { t: "It works out who to wake",
    lines: ["The listed owner of the rules service left the company 95 days ago, so paging them would waste the night.",
      "It ranks the people who are still here by what they have actually touched: commits on this service, and who fixed the same thing last time.",
      "One page goes out, with the reason attached."] },
  { t: "It stops before doing anything risky",
    lines: ["Undoing a change is not always safe, so it checks the graph first.",
      "When the check says risky, the plan says hold and wait for a person to approve.",
      "Nothing is executed without that approval."] },
] as const;

const DEMO_QUERIES = [
  { q: `MATCH p=(s:Service {id:$id})-[:DEPENDS_ON*0..N]->(d:Service)
MATCH (d)<-[:CHANGED]-(dep:Deploy) WHERE dep.ts > $since
OPTIONAL MATCH (who:Person)-[:DEPLOYED]->(dep)
RETURN d.id, dep.id, min(length(p)) AS hops
ORDER BY hops, dep.ts DESC`,
    say: "From the alarming service, follow who calls who downwards and keep anything that was changed recently. Nearest first." },
  { q: `MATCH (p:Person {status:'active'})-[w:WORKED_ON]->(s:Service {id:$id})
RETURN p.id, p.name, p.role, w.commits, w.last_at`,
    say: "Who to wake. It only counts people who are still at the company, and it shows the numbers behind the choice." },
  { q: `UNWIND $ids AS sid
MATCH (s:Service {id:sid})
CALL algo.BFS(s, $depth, 'DEPENDS_ON') YIELD nodes
UNWIND nodes AS d
RETURN d.id, collect(DISTINCT sid)`,
    say: "Six alarms at once. Spread out from each one and see which service they all end up leaning on." },
];

function DemoCompany() {
  const [ref, shown] = useReveal<HTMLDivElement>();
  const map = usePlayer(4, 2600, { loop: true });
  const find = usePlayer(FINDINGS.length, 5000, { autostart: false });
  const { setPlaying } = find;
  const started = useRef(false);
  useEffect(() => {
    if (shown && !started.current && !reducedMotion()) (started.current = true), setPlaying(true);
  }, [shown, setPlaying]);
  const MAP_LINES = [
    "A payments company that does not exist, with a map of everything it runs.",
    "A new engineer cuts a cache time from 300 seconds down to 5, so rule edits apply faster.",
    "What the catalogue never said: that service also calls the config service on every cache miss. Now it calls it constantly.",
    "Two hops up, payments start failing. The alarm goes off here, far from the change.",
  ];
  return (
    <section id="demo" className="border-y border-border bg-surface/60">
      <div ref={ref} className={`ib-rev ${shown ? "in" : ""} mx-auto w-full max-w-6xl px-4 py-14 sm:px-6 sm:py-20 lg:py-24`}>
        <p className="mb-3 text-xs font-semibold tracking-[0.14em] text-muted uppercase">The demo company</p>
        <h2 className="max-w-3xl text-2xl font-semibold tracking-tight sm:text-3xl lg:text-4xl">Meet Kestrel Pay.</h2>
        <p className="mt-4 max-w-3xl text-base text-muted sm:text-lg">
          To show any of this we had to invent a company. Kestrel Pay is a payments business that does not exist. Every
          service, person, chat and ticket in it is made up, but it is built to break the way real companies break.
        </p>

        {/* a) the company in numbers */}
        <div className="mt-10 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
          {KESTREL.map(([n, what], i) => (
            <div key={what} className={`ib-tick ${shown ? "in" : ""} rounded-lg border border-border bg-surface p-3`} style={{ transitionDelay: `${i * 70}ms` }}>
              <div className="font-mono text-xl font-semibold">{n}</div>
              <div className="text-xs text-muted">{what}</div>
            </div>
          ))}
        </div>

        {/* b) what goes wrong, on the map */}
        <div className="mt-10 grid gap-6 lg:grid-cols-[1fr_minmax(0,24rem)]">
          <Card>
            <h3 className="font-semibold">What goes wrong</h3>
            <p className="mt-2 text-sm text-muted">{MAP_LINES[map.i]}</p>
            <ul className="mt-4 space-y-2 text-sm text-muted">
              <li>· The change looks harmless. It is one number in a config file, shipped for a ticket about rule edits being slow.</li>
              <li>· The service that breaks is two hops above it. Nothing on the failing service itself changed.</li>
              <li>· The engineer who built the rules service left 95 days ago. The document about it still names them.</li>
              <li>· The reason the cache has to stay at 300 seconds is sitting in a team chat from more than a year ago.</li>
            </ul>
            <div className="mt-4"><Controls p={map} compact /></div>
          </Card>
          <Card><DemoMap stage={map.i} /></Card>
        </div>

        {/* c) the storm */}
        <div className="mt-6 grid gap-6 md:grid-cols-[1fr_1fr]">
          <Card>
            <h3 className="font-semibold">Then the storm</h3>
            <p className="mt-2 text-sm text-muted">
              Six alarms go off within a minute of each other. Five of them are different services that all lean on the
              same overloaded config service. The sixth has nothing to do with it and has a change of its own.
            </p>
            <p className="mt-3 text-sm text-muted">
              The agent turns {STORM.alerts} alarms into {STORM.incidents} real problems and {STORM.pages} pages. The
              other {STORM.suppressed} stay quiet, and each one keeps the route that shows it was only feeling the same
              problem from further up.
            </p>
          </Card>
          <Card>
            <h3 className="font-semibold">Why this is hard without a map</h3>
            <p className="mt-2 text-sm text-muted">
              Searching the text gets you the wrong answer here. The most recent change is not the cause, the document
              names someone who left, and the one link that explains everything was never written down in the first place.
            </p>
            <p className="mt-3 text-sm text-muted">
              You can only get there by walking the connections, which is exactly what the graph is for.
            </p>
          </Card>
        </div>

        {/* d) what the agent finds */}
        <div className="mt-10 grid gap-6 lg:grid-cols-[minmax(0,21rem)_1fr]"
          tabIndex={0} data-testid="findings" aria-label="What the agent finds, step by step"
          onKeyDown={(e) => {
            if (e.key === " ") (e.preventDefault(), find.setPlaying(!find.playing));
            else if (e.key === "ArrowLeft") (e.preventDefault(), find.go(find.i - 1));
            else if (e.key === "ArrowRight") (e.preventDefault(), find.go(find.i + 1));
          }}>
          <div>
            <h3 className="font-semibold">What the agent finds</h3>
            <ol className="mt-4 space-y-1">
              {FINDINGS.map((f, n) => (
                <li key={f.t}>
                  <button onClick={() => find.go(n)} aria-current={find.i === n ? "step" : undefined} data-testid={`finding-${n + 1}`}
                    className={`flex w-full items-center gap-3 rounded-lg border px-3 py-2 text-left text-sm transition-colors ${
                      find.i === n ? "border-accent bg-accent-soft font-medium" : "border-transparent text-muted hover:bg-surface-2"}`}>
                    <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs ${
                      find.i === n ? "border-accent text-accent" : "border-border"}`}>{n + 1}</span>
                    <span className="truncate">{f.t}</span>
                  </button>
                </li>
              ))}
            </ol>
            <div className="mt-4"><Controls p={find} restart={() => (find.setI(0), find.setPlaying(true))} /></div>
          </div>
          <Card>
            <p className="font-mono text-xs text-muted">finding {find.i + 1} of {FINDINGS.length}</p>
            <h4 className="mt-2 text-lg font-semibold tracking-tight sm:text-xl" data-testid="finding-title">{FINDINGS[find.i].t}</h4>
            <div key={find.i} className="mt-4 space-y-2 text-sm text-muted">
              {FINDINGS[find.i].lines.map((l, k) => <p key={l} className="ib-pop" style={{ animationDelay: `${k * 0.25}s` }}>{l}</p>)}
            </div>
            {find.i === 3 && (
              <blockquote key="q" className="ib-pop mt-4 border-l-2 pl-3 text-sm italic" style={{ borderColor: "var(--mem-stroke)", animationDelay: "0.5s" }}>
                “Cold cache or tiny TTL, same thing: every payment turns into a rulesets fetch.”
                <span className="mt-1 block text-xs not-italic text-muted">from the chat the agent dug up, quoted word for word</span>
              </blockquote>
            )}
            <div className="mt-5 h-1 w-full overflow-hidden rounded-full bg-surface-2">
              <div className="h-full rounded-full bg-accent transition-[width] duration-500" style={{ width: `${((find.i + 1) / FINDINGS.length) * 100}%` }} />
            </div>
          </Card>
        </div>

        {/* e) what FalkorDB does for us */}
        <div className="mt-12">
          <h3 className="text-xl font-semibold tracking-tight">What FalkorDB is doing underneath</h3>
          <p className="mt-2 max-w-3xl text-sm text-muted">
            All of it lives in one graph: services, people, changes, documents, chats, decisions and old incidents. That
            is what lets the agent get from an alarm to a change to a person to a year old chat in a few hops. Three of
            the queries it actually runs:
          </p>
          <div className="mt-6 grid gap-5 lg:grid-cols-3">
            {DEMO_QUERIES.map((d) => (
              <Card key={d.say}>
                <CypherBlock cypher={d.q} />
                <p className="mt-3 text-sm text-muted">{d.say}</p>
              </Card>
            ))}
          </div>
          <p className="mt-5 max-w-3xl text-sm text-muted">
            The built in algorithms do the heavy lifting: shortest path between two services, breadth first search to see
            how far a problem reaches, connected components to prove two alarms cannot share a cause, PageRank and
            betweenness to tell which services everything leans on, label propagation to find clusters, and full text
            search over documents and chats.
          </p>
          <p className="mt-3 max-w-3xl text-sm text-muted">
            Each company gets its own graph. Northwind Health, the second company in the demo, is stored separately, so
            no query can see across.
          </p>
        </div>

        {/* f) the second company */}
        <Card className="mt-8">
          <h3 className="font-semibold">A second company, no code changes</h3>
          <p className="mt-2 text-sm text-muted">
            Northwind Health is a made up health company with 9 services, 8 people and 2 teams, and a different incident
            of its own. The same agent solves it without a line of code being changed for it. Nothing about Kestrel Pay
            is baked into the agent; everything it knows, it reads from the graph in front of it.
          </p>
        </Card>
      </div>
    </section>
  );
}
