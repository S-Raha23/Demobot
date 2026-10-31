// Folds events into the state every panel renders from (stages, feed, costs, artifacts,
// in-flight model calls). Pure, so live runs, replays and "skip to result" all share it.

import { modelInfo, providerOf } from "../lib/models";
import type { ArtifactPayload, MetricPayload, RunEvent, StageEndPayload, StageStatus } from "../lib/types";
import { STAGES } from "../lib/types";
import { tsOf } from "./engine";

export interface StageInfo {
  status: StageStatus;
  startMs?: number;
  endMs?: number;
  summary?: string;
  ok?: boolean;
  durationS?: number;
  models: { id: string; provider: string }[];
  cost: number;
  calls: number;
}

export interface Inflight {
  key: string;
  model: string;
  purpose: string;
  stage: string;
  startMs: number;
}

export interface CostTotals {
  total: number;
  openWeight: number;
  calls: number;
  openCalls: number;
  cachedCalls: number;
  byModel: Record<string, number>;
  byProvider: Record<string, number>;
  callsByModel: Record<string, number>;
}

export interface RunView {
  events: RunEvent[];
  stages: Record<string, StageInfo>;
  current: string | null;
  artifacts: Record<string, ArtifactPayload>; // by path
  artifactList: ArtifactPayload[];
  inflight: Inflight[];
  metrics: Record<string, MetricPayload>;
  cost: CostTotals;
  firstMs: number | null;
  lastMs: number | null;
  ended: boolean;
}

export function emptyView(): RunView {
  const stages: Record<string, StageInfo> = {};
  for (const s of STAGES) stages[s] = { status: "todo", models: [], cost: 0, calls: 0 };
  return {
    events: [],
    stages,
    current: null,
    artifacts: {},
    artifactList: [],
    inflight: [],
    metrics: {},
    cost: {
      total: 0,
      openWeight: 0,
      calls: 0,
      openCalls: 0,
      cachedCalls: 0,
      byModel: {},
      byProvider: {},
      callsByModel: {},
    },
    firstMs: null,
    lastMs: null,
    ended: false,
  };
}

const inflightKey = (model: string, purpose: string) => `${model}::${purpose}`;

export function reduceEvents(prev: RunView, batch: RunEvent[]): RunView {
  if (!batch.length) return prev;
  const v: RunView = {
    ...prev,
    events: prev.events.concat(batch),
    stages: { ...prev.stages },
    artifacts: { ...prev.artifacts },
    artifactList: [...prev.artifactList],
    inflight: [...prev.inflight],
    metrics: { ...prev.metrics },
    cost: {
      ...prev.cost,
      byModel: { ...prev.cost.byModel },
      byProvider: { ...prev.cost.byProvider },
      callsByModel: { ...prev.cost.callsByModel },
    },
  };
  const stage = (s: string): StageInfo => {
    const cur = v.stages[s] ?? { status: "todo", models: [], cost: 0, calls: 0 };
    const copy = { ...cur, models: [...cur.models] };
    v.stages[s] = copy;
    return copy;
  };
  for (const e of batch) {
    const t = tsOf(e);
    v.firstMs ??= t;
    v.lastMs = t;
    switch (e.type) {
      case "stage_start": {
        const s = stage(e.stage);
        s.status = "running";
        s.startMs = t;
        v.current = e.stage;
        break;
      }
      case "stage_end": {
        const p = e.payload as unknown as StageEndPayload;
        const s = stage(e.stage);
        s.status = p.ok === false ? "failed" : "done";
        s.endMs = t;
        s.summary = p.summary;
        s.ok = p.ok;
        s.durationS = p.duration_s;
        if (v.current === e.stage) v.current = null;
        v.inflight = v.inflight.filter((i) => i.stage !== e.stage);
        break;
      }
      case "model_call": {
        const model = e.model ?? "unknown";
        const provider = providerOf(model, e.provider);
        const cost = e.cost_usd ?? 0;
        const s = stage(e.stage);
        if (!s.models.some((m) => m.id === model && m.provider === provider)) s.models.push({ id: model, provider });
        s.cost += cost;
        s.calls += 1;
        const open = Boolean((e.payload as { open_weight?: boolean }).open_weight ?? modelInfo(model).openWeight);
        v.cost.total += cost;
        v.cost.calls += 1;
        if (open) {
          v.cost.openWeight += cost;
          v.cost.openCalls += 1;
        }
        if (e.cached) v.cost.cachedCalls += 1;
        v.cost.byModel[model] = (v.cost.byModel[model] ?? 0) + cost;
        v.cost.callsByModel[model] = (v.cost.callsByModel[model] ?? 0) + 1;
        v.cost.byProvider[provider] = (v.cost.byProvider[provider] ?? 0) + cost;
        const purpose = String((e.payload as { purpose?: string }).purpose ?? "");
        v.inflight = v.inflight.filter((i) => i.key !== inflightKey(model, purpose));
        break;
      }
      case "log": {
        const p = e.payload as { heartbeat?: boolean; purpose?: string; model?: string; elapsed_s?: number };
        if (p.heartbeat && p.model) {
          const key = inflightKey(p.model, p.purpose ?? "");
          const startMs = t - (p.elapsed_s ?? 0) * 1000;
          const i = v.inflight.findIndex((x) => x.key === key);
          const item: Inflight = { key, model: p.model, purpose: p.purpose ?? "", stage: e.stage, startMs };
          if (i >= 0) v.inflight[i] = { ...item, startMs: Math.min(startMs, v.inflight[i].startMs) };
          else v.inflight.push(item);
        }
        break;
      }
      case "artifact": {
        const p = e.payload as unknown as ArtifactPayload;
        v.artifacts[p.path] = p;
        v.artifactList.push(p);
        break;
      }
      case "metric": {
        const p = e.payload as unknown as MetricPayload;
        v.metrics[p.name] = p;
        break;
      }
      default:
        break;
    }
  }
  return v;
}

/** The newest artifact of a kind (e.g. the latest robot trajectory). */
export function latestArtifact(v: RunView, kind: ArtifactPayload["kind"], name?: string): ArtifactPayload | null {
  for (let i = v.artifactList.length - 1; i >= 0; i--) {
    const a = v.artifactList[i];
    if (a.kind === kind && (!name || a.name === name)) return a;
  }
  return null;
}

export function hasArtifact(v: RunView, name: string): ArtifactPayload | null {
  for (let i = v.artifactList.length - 1; i >= 0; i--) if (v.artifactList[i].name === name) return v.artifactList[i];
  return null;
}
