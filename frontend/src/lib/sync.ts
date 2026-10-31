// Timeline <-> video <-> twin time mapping. The shared scrubber runs on video time; the robot's
// trajectory time is mapped "step by step": the k-th human grasp/release (SAM contacts) lines up
// with the k-th robot grasp/release (twin events), piecewise-linear in between.

import type { Contact, SkillCall, TwinEvent } from "./types";

export interface Anchor {
  v: number; // video seconds
  r: number; // robot (trajectory) seconds
}

export function buildAnchors(
  contacts: Contact[],
  robotEvents: TwinEvent[],
  videoDur: number,
  robotDur: number,
): Anchor[] {
  const pts: Anchor[] = [{ v: 0, r: 0 }];
  for (const type of ["grasp", "release"] as const) {
    const h = contacts.filter((c) => c.type === type).sort((a, b) => a.t - b.t);
    const r = robotEvents.filter((e) => e.type === type).sort((a, b) => a.t - b.t);
    const n = Math.min(h.length, r.length);
    for (let k = 0; k < n; k++) pts.push({ v: h[k].t, r: r[k].t });
  }
  pts.sort((a, b) => a.v - b.v);
  const out: Anchor[] = [];
  for (const p of pts) {
    const last = out[out.length - 1];
    if (!last || (p.v > last.v + 1e-6 && p.r > last.r + 1e-6)) out.push(p);
  }
  const end = { v: Math.max(videoDur, 1e-3), r: Math.max(robotDur, 1e-3) };
  while (out.length > 1 && (out[out.length - 1].v >= end.v || out[out.length - 1].r >= end.r)) out.pop();
  out.push(end);
  return out;
}

function interp(anchors: Anchor[], x: number, from: "v" | "r", to: "v" | "r"): number {
  if (!anchors.length) return x;
  if (x <= anchors[0][from]) return anchors[0][to];
  const last = anchors[anchors.length - 1];
  if (x >= last[from]) return last[to];
  for (let i = 1; i < anchors.length; i++) {
    const a = anchors[i - 1];
    const b = anchors[i];
    if (x <= b[from]) {
      const span = b[from] - a[from];
      const f = span > 0 ? (x - a[from]) / span : 1;
      return a[to] + f * (b[to] - a[to]);
    }
  }
  return last[to];
}

export const videoToRobot = (anchors: Anchor[], v: number) => interp(anchors, v, "v", "r");
export const robotToVideo = (anchors: Anchor[], r: number) => interp(anchors, r, "r", "v");

export interface SkillSpan {
  skill: string;
  label: string;
  t0: number;
  t1: number;
  ok: boolean;
}

export function skillSpans(calls: SkillCall[], duration: number): SkillSpan[] {
  return calls.map((c, i) => {
    const t1 = i + 1 < calls.length ? calls[i + 1].t : duration;
    const arg = Object.values(c.args ?? {})[0];
    return {
      skill: c.skill,
      label: arg ? `${c.skill}(${typeof arg === "string" ? arg : JSON.stringify(arg)})` : `${c.skill}()`,
      t0: c.t,
      t1: Math.max(c.t, t1),
      ok: c.ok,
    };
  });
}

/** Index of the last element with key <= t (binary search); -1 if before the first. */
export function indexAt<T>(arr: T[], t: number, key: (x: T) => number): number {
  let lo = 0;
  let hi = arr.length - 1;
  if (hi < 0 || t < key(arr[0])) return -1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (key(arr[mid]) <= t) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}
