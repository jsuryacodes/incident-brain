export type NodeEl = { id: string; label: string; name: string; origin: string; props: Record<string, unknown>; pagerank?: number };
export type EdgeEl = { source: string; target: string; type: string; origin?: string; props?: Record<string, unknown> };
export type Elements = { nodes: NodeEl[]; edges: EdgeEl[] };
export type RunGraph = Elements & { base: string[]; alert: string | null };

export type Source = { id: string; label: string; title: string; excerpt?: string | null };
export type Query = { cypher: string; params: Record<string, unknown>; write?: boolean };

export type StepEvent = {
  seq: number;
  agent: string;
  action: string;
  tool: string;
  summary: string;
  args: Record<string, unknown>;
  cypher: string;
  params: Record<string, unknown>[];
  queries: Query[];
  result_preview: string | null;
  highlight: { nodes: string[]; edges: EdgeEl[] };
  cited: Source[];
  writes: { nodes: NodeEl[]; edges: EdgeEl[] };
  elements: Elements;
  mode: string;
  ms?: number;
  llm_call?: number;
};

export type Report = Record<string, any>;

export type Run = {
  runId: string;
  beatId: string;
  mode: "replay" | "mock" | "live";
  steps: StepEvent[];
  report: Report | null;
  incidentKey?: string | null;
  status?: string;
  totals?: Record<string, number>;
  alert?: { service_id: string; symptom: string } | null;
};

export type Beat = {
  id: string;
  label: string;
  kind: "team" | "resolve";
  title: string;
  caption: string;
  replay: string;
  alert?: { service_id: string; symptom: string };
  continues?: string;
  memory?: boolean;
  resolver?: { ids: string[]; name: string };
  summary?: string;
};

export type Story = { tenant: string; name: string; has_story: boolean; beats: Beat[]; intro?: string };
export type Meta = {
  version: string;
  tenants: { id: string; name: string; has_story: boolean }[];
  llm_modes: string[];
  default_llm_mode: string;
  writes_need_code: boolean;
  code_configured: boolean;
};

export type CompareColumn = {
  key: string;
  title: string;
  source: string;
  alert_service: string | null;
  incident: string | null;
  cause_found: boolean;
  cause: string | null;
  investigator_tool_calls_until_cause: number | null;
  tool_calls_until_cause: number | null;
  llm_calls_until_cause: number | null;
  llm_calls_total: number | null;
  recalled_incident: { id: string; key: string; fixed_by: string[]; fix: string | null } | null;
  contact: string | null;
  industry_match: string | null;
  confidence: string | null;
};
export type Compare = { tenant: string; source: string; columns: CompareColumn[]; metric: string };

export const edgeKey = (e: EdgeEl) => `${e.source}|${e.type}|${e.target}`;
