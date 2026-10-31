"""Renders (docs/06 "Rendering"), CPU TinyRenderer so they work in Docker and on Modal.

- top-down: near-orthographic from high above, 10 px/cm, framed like the rectified real image;
- camera pose: the real phone's viewpoint from the calibration, at the analysis resolution, so
  the sim and the real final frame compare side by side and SAM can segment it.
"""

import math
from pathlib import Path

import cv2
import numpy as np
import pybullet as p

from demobot.schemas import Calibration, Layout, Rect
from demobot.sim.scene import Scene

TOP_PX_PER_CM = 10.0
TOP_MARGIN_CM = 10.0
TOP_EYE_M = 8.0


def _image(cid: int, w: int, h: int, view: list[float], proj: list[float]) -> np.ndarray:
    _, _, rgb, _, _ = p.getCameraImage(
        w, h, view, proj, renderer=p.ER_TINY_RENDERER, shadow=1,
        lightDirection=[0.3, -0.4, 1.0], lightAmbientCoeff=0.55, lightDiffuseCoeff=0.5,
        lightSpecularCoeff=0.05, physicsClientId=cid,
    )  # fmt: skip
    arr = np.asarray(rgb, np.uint8).reshape(h, w, 4)[:, :, :3]
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def top_down(scene: Scene, frame: Rect, px_per_cm: float = TOP_PX_PER_CM) -> np.ndarray:
    """Table rectangle `frame` (cm) at px_per_cm; image right = +x, image down = +y."""
    w = round(frame.w * px_per_cm)
    h = round(frame.h * px_per_cm)
    cx, cy = (frame.x0 + frame.x1) / 200, -(frame.y0 + frame.y1) / 200
    view = p.computeViewMatrix([cx, cy, TOP_EYE_M], [cx, cy, 0], [0, 1, 0])
    fov = math.degrees(2 * math.atan(frame.h / 200 / TOP_EYE_M))
    proj = p.computeProjectionMatrixFOV(fov, w / h, TOP_EYE_M - 1, TOP_EYE_M + 1)
    return _image(scene.client, w, h, view, proj)


def top_frame(layout: Layout) -> Rect:
    wa, m = layout.work_area, TOP_MARGIN_CM
    return Rect(x0=wa.x0 - m, y0=wa.y0 - m, x1=wa.x1 + m, y1=wa.y1 + m)


def view_proj(
    R: np.ndarray, t: np.ndarray, f: float, w: int, h: int
) -> tuple[list[float], list[float]]:
    """PyBullet view and projection matrices for a pinhole camera given in the (x, y, z_down)
    table-cm frame (W -> sim: (x, −y, −z)/100). Assumes a centred principal point."""
    C = -R.T @ t
    to_sim = np.array([1.0, -1.0, -1.0])
    eye = C * to_sim / 100
    fwd = R[2] * to_sim
    up = -R[1] * to_sim
    view = p.computeViewMatrix(eye.tolist(), (eye + fwd).tolist(), up.tolist())
    fov = math.degrees(2 * math.atan(h / 2 / f))
    proj = p.computeProjectionMatrixFOV(fov, w / h, 0.02, 10)
    return list(view), list(proj)


def camera_view(scene: Scene, cal: Calibration) -> np.ndarray:
    """The view from the calibrated phone camera."""
    R = np.asarray(cv2.Rodrigues(np.array(cal.camera.rvec))[0], float)
    w, h = cal.image_size
    view, proj = view_proj(R, np.asarray(cal.camera.tvec, float), cal.camera.focal_px, w, h)
    # the human's real frame has no robot in it: move the arm out of view for this render
    cid = scene.client
    pos, orn = p.getBasePositionAndOrientation(scene.robot, physicsClientId=cid)
    p.resetBasePositionAndOrientation(scene.robot, [pos[0], pos[1], -50], orn, physicsClientId=cid)
    try:
        return _image(cid, w, h, view, proj)
    finally:
        p.resetBasePositionAndOrientation(scene.robot, pos, orn, physicsClientId=cid)


def render_all(
    scene: Scene, layout: Layout, out_dir: Path, tag: str, calibration_json: str | None
) -> dict[str, str]:
    out: dict[str, str] = {}
    top = out_dir / f"top_{tag}.png"
    cv2.imwrite(str(top), top_down(scene, top_frame(layout)))
    out["top"] = str(top)
    if calibration_json:
        cam = out_dir / f"camera_{tag}.png"
        cv2.imwrite(str(cam), camera_view(scene, Calibration.model_validate_json(calibration_json)))
        out["camera"] = str(cam)
    return out
