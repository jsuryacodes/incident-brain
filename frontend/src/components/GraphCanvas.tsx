import cytoscape, { type Core, type ElementDefinition, type StylesheetJson } from "cytoscape";
import fcose from "cytoscape-fcose";
import { Maximize2, Minus, Plus } from "lucide-react";
import { useEffect, useRef } from "react";
import { useTheme } from "../lib/theme";
import { edgeKey, type Elements } from "../lib/types";

cytoscape.use(fcose);

type Pos = { x: number; y: number };
const LAYOUTS = new Map<string, Map<string, Pos>>(); // layoutKey -> positions: computed once, reused (nothing jumps)

export type GraphProps = {
  elements: Elements;
  layoutKey: string;
  visible?: Set<string> | null; // node ids on screen (null = all)
  visibleEdges?: Set<string> | null; // edge keys on screen (null = all among visible nodes)
  current?: { nodes: Set<string>; edges: Set<string> };
  fresh?: { nodes: Set<string>; edges: Set<string> };
  justLearned?: string[];
  alertId?: string | null;
  selected?: string | null;
  onSelect?: (id: string | null) => void;
  sizeByPagerank?: boolean;
  match?: Set<string> | null; // search hits
  ariaLabel: string;
  compact?: boolean;
};

const reducedMotion = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

function seeded(seed: number) {
  let s = seed >>> 0;
  return () => ((s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 4294967296);
}

const SHAPES: Record<string, string> = {
  Service: "round-rectangle", Person: "ellipse", Team: "hexagon", Deploy: "diamond", Incident: "round-triangle",
  Decision: "round-pentagon", Doc: "rectangle", Ticket: "rectangle", ChatThread: "rectangle", RootCause: "octagon",
  PublicPostmortem: "round-tag", Fact: "star", Resolution: "round-diamond", Runbook: "round-rectangle",
};
const SIZE: Record<string, number> = { Service: 32, Team: 26, Incident: 28 };

const learnedEdge = (e: { type: string; origin?: string; props?: Record<string, unknown> }) =>
  e.type === "DEPENDS_ON" && (e.props?.source === "learned" || e.origin === "agent");

function toDefs(els: Elements): ElementDefinition[] {
  const ids = new Set(els.nodes.map((n) => n.id));
  const nodes = [...els.nodes].sort((a, b) => a.id.localeCompare(b.id)).map((n) => ({
    group: "nodes" as const,
    data: { id: n.id, label: n.label, name: n.origin === "agent" ? `AI · ${n.name}` : n.name, origin: n.origin, pr: n.pagerank ?? 0 },
    classes: [n.label === "Service" ? "svc" : "", n.origin === "agent" ? "agent" : ""].join(" "),
  }));
  const seen = new Set<string>();
  const edges = els.edges
    .filter((e) => ids.has(e.source) && ids.has(e.target) && e.source !== e.target)
    .map((e) => ({ ...e, k: edgeKey(e) }))
    .filter((e) => !seen.has(e.k) && seen.add(e.k))
    .sort((a, b) => a.k.localeCompare(b.k))
    .map((e) => ({
      group: "edges" as const,
      data: { id: e.k, source: e.source, target: e.target, type: e.type },
      classes: [learnedEdge(e) ? "learned" : "", e.origin === "agent" ? "agent" : ""].join(" "),
    }));
  return [...nodes, ...edges];
}

/** fcose with a fixed seed, run headless once per layoutKey. */
function computeLayout(defs: ElementDefinition[]): Map<string, Pos> {
  const cy = cytoscape({ headless: true, styleEnabled: true, elements: defs,
    style: [{ selector: "node", style: { width: 40, height: 40 } }, { selector: "node.svc", style: { width: 48, height: 48 } }] });
  const real = Math.random;
  Math.random = seeded(7);
  try {
    cy.layout({ name: "fcose", quality: "proof", randomize: true, animate: false, fit: false, nodeRepulsion: () => 9000,
      idealEdgeLength: () => 85, nodeSeparation: 110, packComponents: true, numIter: 2500 } as any).run();
  } finally {
    Math.random = real;
  }
  const out = new Map<string, Pos>();
  cy.nodes().forEach((n) => void out.set(n.id(), { ...n.position() }));
  cy.destroy();
  return out;
}

function hashAngle(id: string) {
  let h = 2166136261;
  for (const c of id) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
  return ((h >>> 0) % 360) * (Math.PI / 180);
}

/** Positions for every node: cached layout, new nodes placed beside their placed neighbours (existing ones never move). */
function positionsFor(key: string, defs: ElementDefinition[]): Map<string, Pos> {
  let pos = LAYOUTS.get(key);
  const nodeIds = defs.filter((d) => d.group === "nodes").map((d) => d.data.id as string);
  if (!pos) {
    pos = computeLayout(defs);
    LAYOUTS.set(key, pos);
    return pos;
  }
  const missing = nodeIds.filter((id) => !pos!.has(id));
  for (const id of missing) {
    const nb = defs.filter((d) => d.group === "edges" && (d.data.source === id || d.data.target === id))
      .map((d) => (d.data.source === id ? d.data.target : d.data.source) as string)
      .map((n) => pos!.get(n)).filter(Boolean) as Pos[];
    const c = nb.length ? { x: nb.reduce((a, p) => a + p.x, 0) / nb.length, y: nb.reduce((a, p) => a + p.y, 0) / nb.length } : { x: 0, y: 0 };
    const a = hashAngle(id);
    pos.set(id, { x: c.x + Math.cos(a) * 70, y: c.y + Math.sin(a) * 70 });
  }
  return pos;
}

const css = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888";

function buildStyle(sizeByPagerank: boolean, compact: boolean): StylesheetJson {
  const t = reducedMotion() ? 0 : 1;
  const v = {
    node: css("--node"), stroke: css("--node-stroke"), edge: css("--edge"), label: css("--label"), bg: css("--bg"),
    accent: css("--accent"), alert: css("--alert"), alertSoft: css("--alert-soft"), mem: css("--mem-stroke"), memFill: css("--mem-fill"),
    muted: css("--muted"),
  };
  const fs = compact ? 10 : 12;
  return [
    { selector: "node", style: {
      shape: (n: any) => SHAPES[n.data("label")] || "ellipse",
      width: (n: any) => (sizeByPagerank && n.data("pr") ? 18 + Math.sqrt(n.data("pr")) * 120 : SIZE[n.data("label")] || 18),
      height: (n: any) => (sizeByPagerank && n.data("pr") ? 18 + Math.sqrt(n.data("pr")) * 120 : SIZE[n.data("label")] || 18),
      "background-color": v.node, "border-width": 1.5, "border-color": v.stroke, label: "", color: v.label,
      "font-size": fs, "font-family": "Inter, system-ui, sans-serif", "font-weight": 500, "text-valign": "bottom", "text-margin-y": 5,
      "text-background-color": v.bg, "text-background-opacity": 0.85, "text-background-padding": "2px", "text-background-shape": "roundrectangle",
      "text-wrap": "ellipsis", "text-max-width": "150px", "min-zoomed-font-size": 6,
      "transition-property": "opacity, border-width, border-color, background-color, overlay-opacity, overlay-padding",
      "transition-duration": 0.45 * t, opacity: 1, "overlay-opacity": 0,
    } as any },
    { selector: "node.svc", style: { label: "data(name)" } },
    { selector: "node.label-on", style: { label: "data(name)" } },
    { selector: "node.agent", style: { "background-color": v.memFill, "border-color": v.mem, "border-width": 4, "border-style": "double" } },
    { selector: "node.alert", style: { "border-color": v.alert, "border-width": 4, "background-color": v.alertSoft, color: v.alert, "font-weight": 700 } },
    { selector: "node.current", style: { "border-color": v.accent, "border-width": 3.5, label: "data(name)", "z-index": 20 } },
    { selector: "node.current.agent", style: { "border-color": v.mem, "border-width": 5 } },
    { selector: "node.current.alert", style: { "border-color": v.alert } },
    { selector: "node.dim", style: { opacity: 0.55 } },
    { selector: "node.match", style: { "border-color": v.accent, "border-width": 4, label: "data(name)", "z-index": 30 } },
    { selector: "node.selected", style: { "overlay-color": v.accent, "overlay-opacity": 0.14, "overlay-padding": 7, label: "data(name)", "z-index": 40 } },
    { selector: "node.pulse", style: { "overlay-color": v.mem, "overlay-opacity": 0.32, "overlay-padding": 12 } },
    { selector: "node.hidden", style: { opacity: 0, events: "no", label: "" } },
    { selector: "edge", style: {
      width: 1.4, "line-color": v.edge, "target-arrow-color": v.edge, "target-arrow-shape": "triangle", "arrow-scale": 0.75,
      "curve-style": "bezier", opacity: 0.9, "transition-property": "opacity, line-color, width", "transition-duration": 0.45 * t,
      "font-size": 9, color: v.muted, "text-rotation": "autorotate", "text-background-color": v.bg, "text-background-opacity": 0.9,
      "text-background-padding": "1px",
    } as any },
    { selector: "edge.agent", style: { "line-color": v.mem, "target-arrow-color": v.mem, width: 1.8 } },
    { selector: "edge.current", style: { "line-color": v.accent, "target-arrow-color": v.accent, width: 4, "z-index": 15, label: "data(type)", opacity: 1 } },
    { selector: "edge.learned", style: { "line-style": "dashed", "line-dash-pattern": [8, 5], "line-color": v.mem, "target-arrow-color": v.mem, width: 3, "z-index": 18 } },
    { selector: "edge.learned.current", style: { width: 5, label: "learned DEPENDS_ON", color: v.mem, "font-weight": 600 } as any },
    { selector: "edge.dim", style: { opacity: 0.45 } },
    { selector: "edge.hidden", style: { opacity: 0, events: "no", label: "" } },
    { selector: "edge.drawing", style: { opacity: 0 } },
    { selector: ".ghost", style: { width: 1, height: 1, opacity: 0, label: "", events: "no" } },
    { selector: "edge.ghost-edge", style: { "line-style": "dashed", "line-dash-pattern": [8, 5], "line-color": v.mem, "target-arrow-color": v.mem,
      "target-arrow-shape": "triangle", width: 5, opacity: 1, "z-index": 50 } as any },
  ];
}

export function GraphCanvas(p: GraphProps) {
  const box = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const drawn = useRef(new Set<string>());
  const props = useRef(p);
  props.current = p;
  const theme = useTheme((s) => s.theme);

  // create once
  useEffect(() => {
    const cy = cytoscape({ container: box.current, minZoom: 0.2, maxZoom: 3, boxSelectionEnabled: false,
      autoungrabify: false, style: buildStyle(!!p.sizeByPagerank, !!p.compact) });
    cyRef.current = cy;
    cy.on("tap", "node", (e) => props.current.onSelect?.(e.target.id()));
    cy.on("tap", (e) => e.target === cy && props.current.onSelect?.(null));
    cy.on("mouseover", "node", (e) => e.target.addClass("label-on"));
    cy.on("mouseout", "node", (e) => !isLabelled(e.target.id()) && e.target.removeClass("label-on"));
    const ro = new ResizeObserver(() => (cy.resize(), frame(false)));
    ro.observe(box.current!);
    return () => {
      ro.disconnect();
      cy.destroy();
      cyRef.current = null;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const isLabelled = (id: string) => {
    const q = props.current;
    return !!(q.current?.nodes.has(id) || q.selected === id || q.match?.has(id) || id === q.alertId);
  };

  // elements + positions
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    const defs = toDefs(p.elements);
    const pos = positionsFor(p.layoutKey, defs);
    const want = new Set(defs.map((d) => d.data.id as string));
    const first = cy.elements().length === 0 || cy.scratch("_layoutKey") !== p.layoutKey;
    cy.batch(() => {
      cy.elements().filter((e) => !want.has(e.id())).remove();
      for (const d of defs) {
        const ex = cy.getElementById(d.data.id as string);
        if (ex.nonempty()) {
          ex.data(d.data);
          ex.classes(d.classes as string);
          continue;
        }
        cy.add({ ...d, position: d.group === "nodes" ? pos.get(d.data.id as string) : undefined, classes: `${d.classes} hidden` });
      }
    });
    if (first) {
      cy.scratch("_layoutKey", p.layoutKey);
      drawn.current = new Set();
    }
    applyClasses();
    if (first) frame(false);
  }, [p.elements, p.layoutKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const applyClasses = () => {
    const cy = cyRef.current;
    if (!cy) return;
    const q = props.current;
    const hasCurrent = !!q.current && (q.current.nodes.size > 0 || q.current.edges.size > 0);
    cy.batch(() => {
      cy.nodes().forEach((n) => {
        if (n.hasClass("ghost")) return;
        const id = n.id();
        const shown = !q.visible || q.visible.has(id);
        const cur = !!q.current?.nodes.has(id);
        n.toggleClass("hidden", !shown);
        n.toggleClass("current", shown && cur);
        n.toggleClass("dim", shown && hasCurrent && !cur && id !== q.alertId);
        n.toggleClass("alert", id === q.alertId);
        n.toggleClass("selected", id === q.selected);
        n.toggleClass("match", !!q.match?.has(id));
        n.toggleClass("label-on", shown && isLabelled(id));
      });
      cy.edges().forEach((e) => {
        if (e.hasClass("ghost-edge")) return;
        const k = e.id();
        const ends = (!q.visible || (q.visible.has(e.source().id()) && q.visible.has(e.target().id())));
        const shown = ends && (!q.visibleEdges || q.visibleEdges.has(k));
        const cur = !!q.current?.edges.has(k);
        e.toggleClass("hidden", !shown);
        e.toggleClass("current", shown && cur);
        e.toggleClass("dim", shown && hasCurrent && !cur && !e.hasClass("learned"));
      });
    });
    if (!reducedMotion()) {
      q.fresh?.nodes.forEach((id) => cy.getElementById(id).flashClass("pulse", 650));
    }
    drawn.current.forEach((k) => cy.getElementById(k).hasClass("hidden") && drawn.current.delete(k)); // scrubbed back: may draw again
    for (const k of q.justLearned || []) {
      if (drawn.current.has(k)) continue;
      drawn.current.add(k);
      drawIn(cy, k);
    }
  };

  /** Frame the current step (plus the alert) so it is readable; with no current step, everything on screen.
   *  Only the camera moves: node positions never change. */
  const frame = (animate: boolean) => {
    const cy = cyRef.current;
    if (!cy || cy.width() === 0) return;
    const q = props.current;
    const focus = new Set<string>([...(q.current?.nodes || []), ...(q.fresh?.nodes || [])]);
    if (focus.size && q.alertId) focus.add(q.alertId);
    const shown = cy.nodes().not(".hidden").not(".ghost");
    let eles: cytoscape.NodeCollection = focus.size ? shown.filter((n) => focus.has(n.id())) : shown;
    if (eles.empty()) eles = shown.nonempty() ? shown : cy.nodes();
    if (eles.empty()) return;
    const bb = eles.boundingBox({ includeLabels: true });
    const pad = q.compact ? 16 : 70;
    const zoom = Math.max(0.45, Math.min((cy.width() - 2 * pad) / Math.max(bb.w, 1), (cy.height() - 2 * pad) / Math.max(bb.h, 1), q.compact ? 1.2 : 1.5));
    const pan = { x: cy.width() / 2 - zoom * (bb.x1 + bb.w / 2), y: cy.height() / 2 - zoom * (bb.y1 + bb.h / 2) };
    cy.stop();
    if (animate && !reducedMotion()) cy.animate({ zoom, pan } as any, { duration: 650, easing: "ease-in-out-cubic" } as any);
    else cy.viewport({ zoom, pan });
  };
  const framed = useRef("");

  // visibility / emphasis
  useEffect(() => {
    applyClasses();
    const sig = `${p.visible?.size ?? -1}|${[...(p.current?.nodes || [])].sort().join(",")}`;
    if (sig !== framed.current) {
      framed.current = sig;
      frame(true);
    }
  }, [p.visible, p.visibleEdges, p.current, p.fresh, p.justLearned, p.alertId, p.selected, p.match]); // eslint-disable-line react-hooks/exhaustive-deps

  // theme / sizing → restyle without reload
  useEffect(() => {
    cyRef.current?.style(buildStyle(!!p.sizeByPagerank, !!p.compact));
  }, [theme, p.sizeByPagerank, p.compact]);

  const fit = () => frame(true);
  const zoom = (f: number) => {
    const cy = cyRef.current;
    if (cy) cy.zoom({ level: cy.zoom() * f, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
  };

  return (
    <div className="absolute inset-0">
      <div ref={box} className="h-full w-full" role="img" aria-label={p.ariaLabel} data-testid="graph" />
      <div className="absolute right-2 top-2 flex flex-col gap-1">
        {[
          { label: "Zoom in", icon: <Plus size={15} />, on: () => zoom(1.25) },
          { label: "Zoom out", icon: <Minus size={15} />, on: () => zoom(0.8) },
          { label: "Fit graph to screen", icon: <Maximize2 size={14} />, on: fit },
        ].map((b) => (
          <button key={b.label} onClick={b.on} aria-label={b.label} title={b.label}
            className="grid h-8 w-8 place-items-center rounded-md border border-border bg-surface text-muted shadow-sm hover:text-text">
            {b.icon}
          </button>
        ))}
      </div>
    </div>
  );
}

/** The money shot: a dashed amber line drawing itself from source to target, then the real edge takes over. */
function drawIn(cy: Core, key: string) {
  const edge = cy.getElementById(key);
  if (edge.empty()) return;
  if (reducedMotion()) return;
  const src = edge.source(), tgt = edge.target();
  const gid = `ghost:${key}`;
  edge.addClass("drawing");
  const ghost = cy.add({ group: "nodes", data: { id: gid }, position: { ...src.position() }, classes: "ghost" });
  cy.add({ group: "edges", data: { id: `${gid}:e`, source: src.id(), target: gid }, classes: "ghost-edge" });
  ghost.animate({ position: { ...tgt.position() } } as any, {
    duration: 1300, easing: "ease-in-out-cubic",
    complete: () => {
      cy.getElementById(gid).remove();
      edge.removeClass("drawing");
    },
  } as any);
}
