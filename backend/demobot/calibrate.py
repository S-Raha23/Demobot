"""Stage 2: a metric table plane from the four glued markers, with no ruler (docs/04 §2).

Marker positions are unknown. A bundle fit solves for the image->table homography and the
in-plane poses of markers 1–3 from the known 6 cm marker size alone.
"""

import json
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import least_squares

from demobot.camera import (
    F64,
    Camera,
    K_matrix,
    camera_from_homography,
    focal_from_homography,
)
from demobot.config import settings
from demobot.errors import DemoBotError
from demobot.schemas import Calibration, CameraPose, MarkerPose, Rect

MARKER_IDS = (0, 1, 2, 3)
MARKER_CM = 6.0
MAX_FRAMES = 30
WORK_AREA_SHRINK_CM = 4.0
ROBOT_BEHIND_FRONT_CM = 28.0
RECT_PX_PER_CM = 10.0
RECT_MARGIN_CM = 6.0
DEFAULT_HFOV_DEG = 64.0  # long-side FOV of a phone 1× lens in video mode (the human: 63.7°)
MIN_TILT_FOR_FOCAL_DEG = 12.0

_S = MARKER_CM / 2
# ArUco corner order TL, TR, BR, BL in the marker's own frame (y down, as printed)
LOCAL = np.array([[-_S, -_S], [_S, -_S], [_S, _S], [-_S, _S]], float)


def _detector() -> cv2.aruco.ArucoDetector:
    params = cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    params.cornerRefinementWinSize = 5
    params.cornerRefinementMaxIterations = 50
    params.cornerRefinementMinAccuracy = 0.01
    return cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50), params)


def detect_markers(frame: np.ndarray) -> dict[int, F64]:
    """{id: (4, 2) image corners} for the markers 0–3 found in one frame."""
    grey = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = _detector().detectMarkers(grey)
    out: dict[int, F64] = {}
    if ids is None:
        return out
    for c, i in zip(corners, ids.ravel(), strict=True):
        if int(i) in MARKER_IDS and int(i) not in out:
            out[int(i)] = c.reshape(4, 2).astype(float)
    return out


def sample_frames(video: Path, n: int = MAX_FRAMES) -> list[np.ndarray]:
    cap = cv2.VideoCapture(str(video))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    idx = sorted({int(i) for i in np.linspace(0, total - 1, min(n, total))})
    frames = []
    for i in idx:
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, frame = cap.read()
        if ok:
            frames.append(frame)
    cap.release()
    return frames


def median_corners(frames: list[np.ndarray]) -> tuple[dict[int, F64], int]:
    """Per-corner median over the frames where all four markers are visible (the camera is
    fixed). Falls back to per-marker medians over any frame. Raises NO_MARKERS naming the IDs
    never seen."""
    per_frame = [detect_markers(f) for f in frames]
    full = [d for d in per_frame if len(d) == 4]
    pool = full or per_frame
    seen: dict[int, list[F64]] = {i: [] for i in MARKER_IDS}
    for d in pool:
        for i, c in d.items():
            seen[i].append(c)
    missing = [i for i in MARKER_IDS if not seen[i]]
    if missing:
        raise DemoBotError(
            "NO_MARKERS",
            f"marker{'s' if len(missing) > 1 else ''} {', '.join(map(str, missing))} not found: "
            "all four markers must be in view",
            stage="calibrate",
        )
    return {i: np.median(np.stack(cs), axis=0) for i, cs in seen.items()}, len(full)


# ---------- bundle fit ----------
def _marker_corners(pose: F64) -> F64:
    x, y, th = pose
    c, s = np.cos(th), np.sin(th)
    return LOCAL @ np.array([[c, s], [-s, c]]) + np.array([x, y])  # rotate then translate


def _project(G: F64, pts: F64) -> F64:
    h = np.column_stack([pts, np.ones(len(pts))]) @ G.T
    return h[:, :2] / h[:, 2:3]


def _unpack(p: F64) -> tuple[F64, list[F64]]:
    G = np.append(p[:8], 1.0).reshape(3, 3)
    poses = [np.zeros(3)] + [p[8 + 3 * k : 11 + 3 * k] for k in range(3)]
    return G, poses


def bundle_fit(img: dict[int, F64]) -> tuple[F64, list[F64], float]:
    """Returns (G table->image, marker poses (x, y, θ) in marker 0's frame, RMS px)."""
    H0, _ = cv2.findHomography(img[0], LOCAL)  # image -> marker-0 frame, exactly metric
    poses0 = []
    for i in (1, 2, 3):
        t = cv2.perspectiveTransform(img[i][None], H0)[0]
        centre = t.mean(axis=0)
        edge = t[1] - t[0]
        poses0.append(np.array([*centre, np.arctan2(edge[1], edge[0])]))
    G0 = np.linalg.inv(H0)
    G0 /= G0[2, 2]
    p0 = np.concatenate([G0.ravel()[:8], *poses0])
    target = np.concatenate([img[i] for i in MARKER_IDS])

    def resid(p: F64) -> F64:
        G, poses = _unpack(p)
        pts = np.concatenate([_marker_corners(q) for q in poses])
        return (_project(G, pts) - target).ravel()

    sol = least_squares(resid, p0, method="lm", x_scale="jac", max_nfev=5000)
    G, poses = _unpack(sol.x)
    rms = float(np.sqrt(np.mean(sol.fun.reshape(-1, 2) ** 2, axis=0).sum()))
    return G, poses, rms


def _align(poses: list[F64]) -> F64:
    """2D transform A (3×3) taking marker-0 frame to the table frame: marker 0 at the origin,
    marker 1 on +x, marker 3 on the +y side."""
    phi = np.arctan2(poses[1][1], poses[1][0])
    c, s = np.cos(-phi), np.sin(-phi)
    A = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])
    m3 = A @ np.array([poses[3][0], poses[3][1], 1.0])
    if m3[1] < 0:
        A = np.diag([1.0, -1.0, 1.0]) @ A
    return A


# ---------- camera ----------
def load_intrinsics(width: int, height: int) -> tuple[float, float, float] | None:
    """(f, cx, cy) from data/calibration/intrinsics.json scaled to this clip, or None."""
    path = settings.data_path / "calibration" / "intrinsics.json"
    if not path.exists():
        return None
    k = json.loads(path.read_text())
    kw, kh, fx, fy, cx, cy = k["width"], k["height"], k["fx"], k["fy"], k["cx"], k["cy"]
    if (kw > kh) != (width > height):  # portrait vs landscape: swap the axes
        kw, kh, fx, fy, cx, cy = kh, kw, fy, fx, cy, cx
    if abs(kw / kh - width / height) > 0.02:
        return None
    s = width / kw
    return (fx + fy) / 2 * s, cx * s, cy * s


def default_focal(width: int, height: int) -> float:
    return max(width, height) / 2 / np.tan(np.radians(DEFAULT_HFOV_DEG / 2))


def solve_camera(G: F64, width: int, height: int) -> tuple[Camera, str, list[str]]:
    warnings: list[str] = []
    intr = load_intrinsics(width, height)
    if intr:
        f, cx, cy = intr
        return camera_from_homography(G, f, cx, cy, width, height), "intrinsics", warnings
    cx, cy = width / 2, height / 2
    f_est = focal_from_homography(G, cx, cy)
    if f_est is not None and 0.3 * max(width, height) < f_est < 3 * max(width, height):
        cam = camera_from_homography(G, f_est, cx, cy, width, height)
        if _tilt_deg(cam) >= MIN_TILT_FOR_FOCAL_DEG:
            return cam, "homography", warnings
    warnings.append("near top-down view: focal length from a typical phone field of view")
    return (
        camera_from_homography(G, default_focal(width, height), cx, cy, width, height),
        "default_fov",
        warnings,
    )


def _tilt_deg(cam: Camera) -> float:
    return float(np.degrees(np.arccos(np.clip(cam.R[2, 2], -1, 1))))


def camera_pose(cam: Camera, source: str) -> CameraPose:
    C = cam.center
    look = cam.R[2]  # optical axis in world (x, y, z_down)
    rvec, _ = cv2.Rodrigues(cam.R)
    return CameraPose(
        focal_px=float(cam.K[0, 0]),
        principal_px=(float(cam.K[0, 2]), float(cam.K[1, 2])),
        focal_source=source,
        position_cm=(float(C[0]), float(C[1]), float(-C[2])),
        look_dir=(float(look[0]), float(look[1]), float(-look[2])),
        tilt_deg=_tilt_deg(cam),
        nadir_cm=(float(C[0]), float(C[1])),
        rvec=tuple(float(v) for v in rvec.ravel()),
        tvec=tuple(float(v) for v in cam.t),
    )


def camera_of(cal: Calibration) -> Camera:
    R = np.asarray(cv2.Rodrigues(np.array(cal.camera.rvec))[0], float)
    K = K_matrix(cal.camera.focal_px, *cal.camera.principal_px)
    return Camera(K, R, np.array(cal.camera.tvec), *cal.image_size)


# ---------- the stage ----------
def calibrate_corners(
    img: dict[int, F64], width: int, height: int, frames_used: int
) -> Calibration:
    G_fit, poses, rms = bundle_fit(img)
    A = _align(poses)
    H_img_to_table = A @ np.linalg.inv(G_fit)
    H_img_to_table /= H_img_to_table[2, 2]
    G = np.linalg.inv(H_img_to_table)
    G /= G[2, 2]
    markers = []
    for i, q in zip(MARKER_IDS, poses, strict=True):
        corners = (A @ np.column_stack([_marker_corners(q), np.ones(4)]).T).T[:, :2]
        centre = corners.mean(axis=0)
        edge = corners[1] - corners[0]
        markers.append(
            MarkerPose(
                id=i,
                center_cm=(float(centre[0]), float(centre[1])),
                theta_rad=float(np.arctan2(edge[1], edge[0])),
                corners_cm=[(float(x), float(y)) for x, y in corners],
                corners_px=[(float(x), float(y)) for x, y in img[i]],
            )
        )
    cx = [m.center_cm[0] for m in markers]
    cy = [m.center_cm[1] for m in markers]
    s = WORK_AREA_SHRINK_CM
    work = Rect(x0=min(cx) + s, y0=min(cy) + s, x1=max(cx) - s, y1=max(cy) - s)
    cam, source, warnings = solve_camera(G, width, height)
    if rms > 1.5:
        warnings.append(f"marker reprojection {rms:.2f} px is high: are the markers flat?")
    m = RECT_MARGIN_CM
    origin = (min(cx) - _S - m, min(cy) - _S - m)
    size = (
        round((max(cx) - min(cx) + 2 * (_S + m)) * RECT_PX_PER_CM),
        round((max(cy) - min(cy) + 2 * (_S + m)) * RECT_PX_PER_CM),
    )
    return Calibration(
        image_size=(width, height),
        H_img_to_table=H_img_to_table.tolist(),
        markers=markers,
        work_area=work,
        robot_base_cm=((work.x0 + work.x1) / 2, work.y1 + ROBOT_BEHIND_FRONT_CM),
        camera=camera_pose(cam, source),
        method="markers_plus_intrinsics" if source == "intrinsics" else "markers_bundle",
        reprojection_px=rms,
        frames_used=frames_used,
        rectify_px_per_cm=RECT_PX_PER_CM,
        rectify_origin_cm=origin,
        rectify_size=size,
        warnings=warnings,
    )


def rectify_matrix(cal: Calibration) -> F64:
    """Image pixels -> rectified pixels (10 px/cm, table-aligned, +y down)."""
    s = cal.rectify_px_per_cm
    ox, oy = cal.rectify_origin_cm
    S = np.array([[s, 0, -ox * s], [0, s, -oy * s], [0, 0, 1.0]])
    return S @ np.array(cal.H_img_to_table)


def rectify(frame: np.ndarray, cal: Calibration) -> np.ndarray:
    return cv2.warpPerspective(frame, rectify_matrix(cal), cal.rectify_size, flags=cv2.INTER_LINEAR)


def overlay_layer(cal: Calibration) -> dict[str, object]:
    """Debug overlay for the UI: marker outlines and the table axes, in image pixels."""
    G = np.linalg.inv(np.array(cal.H_img_to_table))
    axes = cv2.perspectiveTransform(np.array([[[0, 0], [10, 0], [0, 10]]], float), G)[0]
    wa = cal.work_area
    work = cv2.perspectiveTransform(
        np.array([[[wa.x0, wa.y0], [wa.x1, wa.y0], [wa.x1, wa.y1], [wa.x0, wa.y1]]], float), G
    )[0]
    return {
        "markers": [{"id": m.id, "corners_px": m.corners_px} for m in cal.markers],
        "axes_px": {
            "origin": axes[0].tolist(),
            "x10cm": axes[1].tolist(),
            "y10cm": axes[2].tolist(),
        },
        "work_area_px": work.tolist(),
    }


def run(video: Path, out_dir: Path) -> Calibration:
    """Calibrate from a clip; writes calibration.json, rectified first/last frames, overlay."""
    frames = sample_frames(video)
    if not frames:
        raise DemoBotError("NOT_A_VIDEO", "could not read frames", stage="calibrate")
    img, used = median_corners(frames)
    h, w = frames[0].shape[:2]
    cal = calibrate_corners(img, w, h, used)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "calibration.json").write_text(cal.model_dump_json(indent=1))
    (out_dir / "calibration_overlay.json").write_text(json.dumps(overlay_layer(cal)))
    cv2.imwrite(str(out_dir / "rectified_first.png"), rectify(frames[0], cal))
    cv2.imwrite(str(out_dir / "rectified_last.png"), rectify(frames[-1], cal))
    return cal
