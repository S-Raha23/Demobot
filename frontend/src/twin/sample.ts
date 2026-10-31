// Sampling a twin trajectory at any time (joint values and object poses interpolated).

import type { TwinFrame, TwinTrajectory } from "../lib/types";
import { indexAt } from "../lib/sync";

export interface Sample {
  q: number[];
  poses: Record<string, number[]>;
}

function slerp(a: number[], b: number[], f: number): number[] {
  let [ax, ay, az, aw] = a;
  const [bx, by, bz, bw] = b;
  let dot = ax * bx + ay * by + az * bz + aw * bw;
  if (dot < 0) {
    ax = -ax;
    ay = -ay;
    az = -az;
    aw = -aw;
    dot = -dot;
  }
  if (dot > 0.9995) {
    const r = [ax + f * (bx - ax), ay + f * (by - ay), az + f * (bz - az), aw + f * (bw - aw)];
    const n = Math.hypot(...r) || 1;
    return r.map((x) => x / n);
  }
  const th = Math.acos(dot);
  const s = Math.sin(th);
  const wa = Math.sin((1 - f) * th) / s;
  const wb = Math.sin(f * th) / s;
  return [wa * ax + wb * bx, wa * ay + wb * by, wa * az + wb * bz, wa * aw + wb * bw];
}

export function sampleTrajectory(traj: TwinTrajectory, t: number): Sample | null {
  const fr = traj.frames;
  if (!fr.length) return null;
  const i = indexAt<TwinFrame>(fr, t, (f) => f.t);
  if (i < 0) return { q: fr[0].q, poses: fr[0].poses };
  if (i >= fr.length - 1) return { q: fr[fr.length - 1].q, poses: fr[fr.length - 1].poses };
  const a = fr[i];
  const b = fr[i + 1];
  const span = b.t - a.t;
  const f = span > 0 ? Math.min(1, Math.max(0, (t - a.t) / span)) : 0;
  const q = a.q.map((x, k) => x + f * ((b.q[k] ?? x) - x));
  const poses: Record<string, number[]> = {};
  for (const name of Object.keys(a.poses)) {
    const pa = a.poses[name];
    const pb = b.poses[name] ?? pa;
    poses[name] = [
      pa[0] + f * (pb[0] - pa[0]),
      pa[1] + f * (pb[1] - pa[1]),
      pa[2] + f * (pb[2] - pa[2]),
      ...slerp(pa.slice(3, 7), pb.slice(3, 7), f),
    ];
  }
  return { q, poses };
}

export const PANDA_JOINTS = [
  "panda_joint1",
  "panda_joint2",
  "panda_joint3",
  "panda_joint4",
  "panda_joint5",
  "panda_joint6",
  "panda_joint7",
  "panda_finger_joint1",
  "panda_finger_joint2",
];

export const PANDA_HOME = [0, -0.785, 0, -2.356, 0, 1.571, 0.785, 0.04, 0.04];
