// Coordinate frames (docs/02, docs/decisions.md):
//  - table frame: cm, origin marker 0, +x right, +y towards the robot and camera (2D).
//  - W (camera maths): (x, y, z_down) in cm. OpenCV rvec/tvec map W -> camera.
//  - PyBullet / twin: metres, X = x/100, Y = -y/100, Z up.
//  - three.js world: Y up. The twin puts everything inside a group rotated -90° about X, so
//    PyBullet coordinates are used as-is inside it: (X, Y, Z)_pb -> (X, Z, -Y)_three.

export type V3 = [number, number, number];
export type M3 = [V3, V3, V3];

export const tableToPb = (x: number, y: number, zCm = 0): V3 => [x / 100, -y / 100, zCm / 100];
export const pbToTable = (X: number, Y: number): [number, number] => [X * 100, -Y * 100];
export const pbToThree = ([x, y, z]: V3): V3 => [x, z, -y];
export const wToPb = ([x, y, z]: V3): V3 => [x / 100, -y / 100, -z / 100];

/** Rodrigues: rotation vector -> 3×3 matrix (rows). */
export function rodrigues(r: V3): M3 {
  const th = Math.hypot(r[0], r[1], r[2]);
  if (th < 1e-12)
    return [
      [1, 0, 0],
      [0, 1, 0],
      [0, 0, 1],
    ];
  const [kx, ky, kz] = [r[0] / th, r[1] / th, r[2] / th];
  const c = Math.cos(th);
  const s = Math.sin(th);
  const v = 1 - c;
  return [
    [c + kx * kx * v, kx * ky * v - kz * s, kx * kz * v + ky * s],
    [ky * kx * v + kz * s, c + ky * ky * v, ky * kz * v - kx * s],
    [kz * kx * v - ky * s, kz * ky * v + kx * s, c + kz * kz * v],
  ];
}

export interface CameraFrame {
  /** Camera centre in three.js world metres. */
  position: V3;
  /** Camera basis in three.js world: right, up, back (three cameras look along -Z). */
  right: V3;
  up: V3;
  back: V3;
}

/** The calibrated phone camera as a three.js camera frame. */
export function phoneCamera(rvec: V3, tvec: V3): CameraFrame {
  const R = rodrigues(rvec);
  // C = -R^T t (W, cm)
  const C: V3 = [0, 1, 2].map((j) => -(R[0][j] * tvec[0] + R[1][j] * tvec[1] + R[2][j] * tvec[2])) as V3;
  const toThree = (w: V3) => pbToThree(wToPb(w));
  const dirToThree = (w: V3): V3 => pbToThree([w[0], -w[1], -w[2]]);
  const camX = R[0]; // OpenCV x (right) in W
  const camY = R[1]; // OpenCV y (down) in W
  const camZ = R[2]; // OpenCV z (forward) in W
  const right = dirToThree(camX);
  const down = dirToThree(camY);
  const fwd = dirToThree(camZ);
  return {
    position: toThree(C),
    right,
    up: [-down[0], -down[1], -down[2]],
    back: [-fwd[0], -fwd[1], -fwd[2]],
  };
}

/** A column-major 4×4 projection matrix (three.js `elements` order) for a pinhole camera with
 * focal f and principal point (cx, cy) in an image of size (W, H), drawn "contain"-fitted into a
 * canvas of size (cw, ch) — the same way the video element shows display.mp4. */
export function intrinsicProjection(
  f: number,
  cx: number,
  cy: number,
  W: number,
  H: number,
  cw: number,
  ch: number,
  near = 0.01,
  far = 20,
): number[] {
  const s = Math.min(cw / W, ch / H);
  const ox = (cw - s * W) / 2;
  const oy = (ch - s * H) / 2;
  const p00 = (2 * s * f) / cw;
  const p11 = (2 * s * f) / ch;
  const p02 = 1 - (2 * (s * cx + ox)) / cw;
  const p12 = (2 * (s * cy + oy)) / ch - 1;
  const p22 = -(far + near) / (far - near);
  const p23 = (-2 * far * near) / (far - near);
  // row-major [[p00,0,p02,0],[0,p11,p12,0],[0,0,p22,p23],[0,0,-1,0]] -> column-major
  return [p00, 0, 0, 0, 0, p11, 0, 0, p02, p12, p22, -1, 0, 0, p23, 0];
}

/** Project a W point (cm) to image pixels with the OpenCV model (used by tests). */
export function projectW(rvec: V3, tvec: V3, f: number, c: [number, number], w: V3): [number, number] {
  const R = rodrigues(rvec);
  const X = [0, 1, 2].map((i) => R[i][0] * w[0] + R[i][1] * w[1] + R[i][2] * w[2] + tvec[i]);
  return [f * (X[0] / X[2]) + c[0], f * (X[1] / X[2]) + c[1]];
}
