import type { Health, Layout, RunDetail, RunEvent, RunMeta, SkillCard, TryLayoutResponse } from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) {
    let code = `HTTP_${r.status}`;
    let message = r.statusText;
    try {
      const body = await r.json();
      code = body.code ?? code;
      message = body.message ?? body.detail ?? message;
    } catch {
      /* not JSON */
    }
    throw new ApiError(r.status, code, String(message));
  }
  return (await r.json()) as T;
}

export const artifactUrl = (runId: string, path: string) =>
  `/api/runs/${encodeURIComponent(runId)}/artifacts/${path.replace(/^\/+/, "")}`;

const jsonCache = new Map<string, Promise<unknown>>();

/** Artifacts are immutable once announced, so JSON is cached per URL. */
export function fetchArtifactJson<T>(runId: string, path: string): Promise<T> {
  const url = artifactUrl(runId, path);
  let p = jsonCache.get(url);
  if (!p) {
    p = req<T>(url);
    p.catch(() => jsonCache.delete(url));
    jsonCache.set(url, p);
  }
  return p as Promise<T>;
}

export function fetchArtifactText(runId: string, path: string): Promise<string> {
  const url = artifactUrl(runId, path);
  let p = jsonCache.get(url);
  if (!p) {
    p = fetch(url).then((r) => {
      if (!r.ok) throw new ApiError(r.status, "NOT_FOUND", "no such artifact");
      return r.text();
    });
    p.catch(() => jsonCache.delete(url));
    jsonCache.set(url, p);
  }
  return p as Promise<string>;
}

export const api = {
  health: () => req<Health>("/api/health"),
  runs: () => req<RunMeta[]>("/api/runs"),
  run: (id: string) => req<RunDetail>(`/api/runs/${encodeURIComponent(id)}`),
  events: (id: string) => req<RunEvent[]>(`/api/runs/${encodeURIComponent(id)}/events.json`),
  skills: () => req<SkillCard[]>("/api/skills"),
  costs: () => req<CostsResponse>("/api/costs"),
  tryLayout: (id: string, objects: { name: string; x: number; y: number; yaw?: number }[]) =>
    req<TryLayoutResponse>(`/api/runs/${encodeURIComponent(id)}/try-layout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ objects }),
    }),
  shuffle: (id: string, seed: number) =>
    req<Layout>(`/api/runs/${encodeURIComponent(id)}/shuffle?seed=${seed}`, { method: "POST" }),
  createRun: (form: FormData) => req<{ run_id: string }>("/api/runs", { method: "POST", body: form }),
  createSampleRun: (sample: string) =>
    req<{ run_id: string }>("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sample }),
    }),
  correct: (id: string, body: FormData | { text: string }) =>
    req<{ run_id: string }>(`/api/runs/${encodeURIComponent(id)}/correct`, {
      method: "POST",
      ...(body instanceof FormData
        ? { body }
        : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
    }),
  samples: () => req<Sample[]>("/api/samples"),
  evalResults: () => req<{ markdown: string }>("/api/eval"),
};

export interface Sample {
  id: string;
  title: string;
  duration_s?: number;
  thumb?: string;
}

export interface LedgerRow {
  usd: number;
  calls: number;
  cache_hits: number;
  today_usd: number;
}

export interface CostsResponse {
  ledger: { by_provider: Record<string, LedgerRow>; by_model: Record<string, LedgerRow>; remaining?: unknown } | null;
  runs: ({ run_id: string; title?: string } & import("./types").CostsFile)[];
}
