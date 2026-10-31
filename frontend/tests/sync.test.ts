import { describe, expect, it } from "vitest";
import { buildAnchors, indexAt, robotToVideo, skillSpans, videoToRobot } from "../src/lib/sync";
import { intrinsicProjection, phoneCamera, projectW, type V3 } from "../src/lib/frames";
import { sampleTrajectory } from "../src/twin/sample";
import type { Contact, TwinEvent, TwinTrajectory } from "../src/lib/types";

const contacts: Contact[] = [
  { t: 3.43, type: "grasp", object: "teal pen" },
  { t: 5.33, type: "release", object: "teal pen" },
  { t: 7.6, type: "grasp", object: "teal pen 2" },
  { t: 9.5, type: "release", object: "teal pen 2" },
];
// The robot does the pens in the other order: matching is by step order, not by name.
const robot: TwinEvent[] = [
  { t: 2.4667, type: "grasp", object: "teal pen 2" },
  { t: 5.4833, type: "release", object: "teal pen 2" },
  { t: 8.7542, type: "grasp", object: "teal pen" },
  { t: 11.725, type: "release", object: "teal pen" },
];

describe("timeline <-> video <-> twin mapping", () => {
  const a = buildAnchors(contacts, robot, 13.3, 15.412);

  it("anchors every human contact to the matching robot contact, step by step", () => {
    expect(a.map((x) => x.v)).toEqual([0, 3.43, 5.33, 7.6, 9.5, 13.3]);
    expect(videoToRobot(a, 3.43)).toBeCloseTo(2.4667);
    expect(videoToRobot(a, 9.5)).toBeCloseTo(11.725);
    expect(videoToRobot(a, 13.3)).toBeCloseTo(15.412);
  });

  it("is monotonic and invertible", () => {
    let prev = -1;
    for (let v = 0; v <= 13.3; v += 0.1) {
      const r = videoToRobot(a, v);
      expect(r).toBeGreaterThanOrEqual(prev);
      expect(robotToVideo(a, r)).toBeCloseTo(v, 6);
      prev = r;
    }
  });

  it("clamps outside the clip", () => {
    expect(videoToRobot(a, -2)).toBe(0);
    expect(videoToRobot(a, 99)).toBeCloseTo(15.412);
  });

  it("falls back to a linear map without contacts", () => {
    const b = buildAnchors([], [], 10, 20);
    expect(videoToRobot(b, 5)).toBeCloseTo(10);
  });

  it("drops anchors that would make the map non-monotonic", () => {
    const b = buildAnchors(
      [
        { t: 2, type: "grasp", object: "a" },
        { t: 3, type: "release", object: "a" },
      ],
      [
        { t: 5, type: "grasp", object: "a" },
        { t: 4, type: "release", object: "a" },
      ],
      10,
      10,
    );
    for (let i = 1; i < b.length; i++) {
      expect(b[i].v).toBeGreaterThan(b[i - 1].v);
      expect(b[i].r).toBeGreaterThan(b[i - 1].r);
    }
  });
});

describe("skill spans and lookup", () => {
  it("turns skill calls into segments ending at the next call", () => {
    const s = skillSpans(
      [
        { skill: "pick", args: { object: "pen" }, ok: true, t: 0.5 },
        { skill: "home", args: {}, ok: true, t: 3 },
      ],
      5,
    );
    expect(s.map((x) => [x.t0, x.t1, x.label])).toEqual([
      [0.5, 3, "pick(pen)"],
      [3, 5, "home()"],
    ]);
  });

  it("indexAt finds the last frame at or before t", () => {
    const arr = [0, 1, 2, 3].map((t) => ({ t }));
    expect(indexAt(arr, -1, (x) => x.t)).toBe(-1);
    expect(indexAt(arr, 1.5, (x) => x.t)).toBe(1);
    expect(indexAt(arr, 9, (x) => x.t)).toBe(3);
  });
});

describe("twin trajectory sampling", () => {
  const traj = {
    fps: 30,
    frames: [
      { t: 0, q: [0, 0], poses: { a: [0, 0, 0, 0, 0, 0, 1] } },
      { t: 1, q: [1, 2], poses: { a: [1, 0, 0, 0, 0, Math.SQRT1_2, Math.SQRT1_2] } },
    ],
  } as unknown as TwinTrajectory;

  it("interpolates joints and poses between frames", () => {
    const s = sampleTrajectory(traj, 0.5)!;
    expect(s.q).toEqual([0.5, 1]);
    expect(s.poses.a[0]).toBeCloseTo(0.5);
    // halfway through a 90° yaw is a 45° yaw
    expect(s.poses.a[5]).toBeCloseTo(Math.sin(Math.PI / 8));
  });

  it("holds the first and last frames outside the trajectory", () => {
    expect(sampleTrajectory(traj, -1)!.q).toEqual([0, 0]);
    expect(sampleTrajectory(traj, 5)!.q).toEqual([1, 2]);
  });
});

describe("real camera view", () => {
  // The fixture run's calibrated camera (twin_scene.json).
  const rvec: V3 = [-0.652794448208506, -0.026577497524565164, -0.0035079077525425745];
  const tvec: V3 = [-33.567248653495874, -20.908696775973905, 102.95441759118482];
  const f = 1029.1670228835642;
  const c: [number, number] = [657.8652031899854, 371.43657784132586];

  it("puts the camera where calibration says (position_cm = [31.0, 79.5, 69.8])", () => {
    const cam = phoneCamera(rvec, tvec);
    // three.js: (x, height, y) in metres
    expect(cam.position[0]).toBeCloseTo(0.31, 2);
    expect(cam.position[1]).toBeCloseTo(0.698, 2);
    expect(cam.position[2]).toBeCloseTo(0.795, 2);
  });

  it("projects table points to the same pixels as OpenCV", () => {
    const cam = phoneCamera(rvec, tvec);
    const P = intrinsicProjection(f, c[0], c[1], 1280, 720, 1280, 720);
    for (const [x, y] of [
      [0, 0],
      [60.27, 0],
      [30, 20],
      [59.9, 40.9],
    ]) {
      const ocv = projectW(rvec, tvec, f, c, [x, y, 0]);
      const w: V3 = [x / 100, 0, y / 100]; // three.js world
      const d = [w[0] - cam.position[0], w[1] - cam.position[1], w[2] - cam.position[2]];
      const dot = (u: V3) => d[0] * u[0] + d[1] * u[1] + d[2] * u[2];
      const xc = dot(cam.right);
      const yc = dot(cam.up);
      const zc = dot(cam.back);
      // column-major: clip = P * [xc, yc, zc, 1]
      const cx = P[0] * xc + P[4] * yc + P[8] * zc + P[12];
      const cy = P[1] * xc + P[5] * yc + P[9] * zc + P[13];
      const cwv = P[3] * xc + P[7] * yc + P[11] * zc + P[15];
      const u = ((cx / cwv + 1) / 2) * 1280;
      const v = ((1 - cy / cwv) / 2) * 720;
      expect(u).toBeCloseTo(ocv[0], 3);
      expect(v).toBeCloseTo(ocv[1], 3);
    }
  });

  it("matches the marker detections (marker 0 centre)", () => {
    const [u, v] = projectW(rvec, tvec, f, c, [0, 0, 0]);
    // the mean of marker 0's detected corners in twin_scene.json
    expect(Math.abs(u - 321.5)).toBeLessThan(3);
    expect(Math.abs(v - 163.2)).toBeLessThan(3);
  });
});
