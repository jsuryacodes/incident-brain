import type { Compare, Elements, Meta, RunGraph, Story } from "./types";

const CODE_KEY = "ib.code";

// The access code lives in sessionStorage only (gone when the tab closes), is sent as X-Access-Code, never logged.
export function getCode(): string {
  try {
    return sessionStorage.getItem(CODE_KEY) || "";
  } catch {
    return memCode;
  }
}
let memCode = "";
export function setCode(code: string) {
  memCode = code;
  try {
    if (code) sessionStorage.setItem(CODE_KEY, code);
    else sessionStorage.removeItem(CODE_KEY);
  } catch {
    /* memory only */
  }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(init.body ? { "Content-Type": "application/json" } : {}) };
  const code = getCode();
  if (code) headers["X-Access-Code"] = code;
  const r = await fetch(path, { ...init, headers: { ...headers, ...(init.headers as Record<string, string>) } });
  if (!r.ok) {
    let detail = r.statusText;
    try {
      detail = (await r.json()).detail || detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(r.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return r.json() as Promise<T>;
}

const q = (o: Record<string, string | number | undefined>) =>
  new URLSearchParams(Object.entries(o).filter(([, v]) => v !== undefined && v !== "") as [string, string][]).toString();

export const api = {
  meta: () => req<Meta>("/api/meta"),
  checkCode: (code: string) => req<{ ok: boolean }>("/api/access/check", { method: "POST", headers: { "X-Access-Code": code } }),
  story: (tenant: string) => req<Story>(`/api/story?${q({ tenant })}`),
  replay: (name: string) => req<any>(`/api/replay/${encodeURIComponent(name)}`),
  runGraph: (runId: string) => req<RunGraph>(`/api/run-graph/${encodeURIComponent(runId)}`),
  subgraph: (tenant: string, ids: string[], hops = 0) => req<Elements>(`/api/subgraph?${q({ tenant, ids: ids.join(","), hops })}`),
  compare: (tenant: string) => req<Compare>(`/api/compare/latest?${q({ tenant })}`),
  startBeat: (tenant: string, beat: string) =>
    req<{ stream: string; mode: string; mode_reason: string }>(`/api/story/${beat}/run`, { method: "POST", body: JSON.stringify({ tenant }) }),
  suggestions: (tenant: string) => req<{ questions: { kind: string; question: string }[] }>(`/api/brain/suggestions?${q({ tenant })}`),
  ask: (body: Record<string, unknown>) => req<any>("/api/brain/ask", { method: "POST", body: JSON.stringify(body) }),
  explorer: (tenant: string, labels: string[], origin?: string) =>
    req<any>(`/api/explorer?${q({ tenant, labels: labels.join(","), origin })}`),
  node: (tenant: string, id: string) => req<any>(`/api/node/${encodeURIComponent(id)}?${q({ tenant })}`),
};
