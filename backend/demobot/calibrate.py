"""Stage 2: a metric table plane and a per-frame camera track from the four glued markers, with
no ruler (docs/04 §2). The phone is handheld, so the camera moves; the markers do not.

1. Detect markers in every analysis frame and measure sharpness (blur flag).
2. Joint bundle fit over up to 30 sharp frames: shared in-plane poses of markers 1–3 (marker 0 is
   the origin) and one homography per frame, from the known 6 cm marker size alone.
3. Every frame with ≥ 3 markers gets its own homography; the track is smoothed over time and
   frames with < 3 markers or blur are interpolated from their neighbours.
4. Focal length, per-frame camera pose, the reference (last clean) frame, the work area, and a
   stabilised display video warped to the first frame's view.
"""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import least_squares
from scipy.sparse import lil_matrix

from demobot.camera import (
    F64,
    Camera,
    K_matrix,
    focal_from_homography,
    pose_from_homography,
)
from demobot.config import settings
from demobot.errors import DemoBotError
from demobot.schemas import Calibration, CameraPose, CameraTrack, FrameCam, MarkerPose, Rect

MARKER_IDS = (0, 1, 2, 3)
MARKER_CM = 6.0
MAX_JOINT_FRAMES = 30
MIN_MARKERS = 3
BLUR_RATIO = 0.45
OUTLIER_PX = 3.0
SMOOTH_SIGMA = 0.5  # frames at 10 fps
SMOOTH_SLACK_PX = 0.75  # a smoothed frame may fit its own markers at most this much worse
WORK_AREA_SHRINK_CM = 4.0
ROBOT_BEHIND_FRONT_CM = 28.0
RECT_PX_PER_CM = 10.0
RECT_MARGIN_CM = 6.0
DEFAULT_HFOV_DEG = 64.0  # long-side FOV of a phone 1× lens in video mode (the human: 63.7°)
MIN_TILT_FOR_FOCAL_DEG = 12.0

_S = MARKER_CM / 2
# ArUco corner order TL, TR, BR, BL in the marker's own frame (y down, as printed)
LOCAL = np.array([[-_S, -_S], [_S, -_S], [_S, _S], [-_S, _S]], float)


@dataclass
class Obs:
    """Detections in one frame."""

    corners: dict[int, F64]  # id -> (4, 2) image corners
    sharpness: float


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


def sharpness(frame: np.ndarray, corners: dict[int, F64]) -> float:
    """Variance of the Laplacian inside the marker regions (the whole frame if none)."""
    grey = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    lap = cv2.Laplacian(grey, cv2.CV_32F)
    if not corners:
        return float(lap.var())
    vals = []
    h, w = grey.shape
    for c in corners.values():
        x0, y0 = np.clip(c.min(axis=0).astype(int) - 2, 0, None)
        x1, y1 = c.max(axis=0).astype(int) + 3
        vals.append(lap[y0 : min(y1, h), x0 : min(x1, w)].ravel())
    return float(np.concatenate(vals).var())


def observe(frame: np.ndarray) -> Obs:
    c = detect_markers(frame)
    return Obs(c, sharpness(frame, c))


def blurred_flags(obs: list[Obs]) -> list[bool]:
    med = float(np.median([o.sharpness for o in obs])) if obs else 0.0
    return [o.sharpness < BLUR_RATIO * med for o in obs]


def check_all_seen(obs: list[Obs]) -> None:
    missing = [i for i in MARKER_IDS if not any(i in o.corners for o in obs)]
    if missing:
        raise DemoBotError(
            "NO_MARKERS",
            f"marker{'s' if len(missing) > 1 else ''} {', '.join(map(str, missing))} not found: "
            "all four markers must be in view",
            stage="calibrate",
        )


# ---------- marker geometry ----------
def _marker_corners(pose: F64) -> F64:
    x, y, th = pose
    c, s = np.cos(th), np.sin(th)
    return LOCAL @ np.array([[c, s], [-s, c]]) + np.array([x, y])  # rotate then translate


def _project(G: F64, pts: F64) -> F64:
    h = np.column_stack([pts, np.ones(len(pts))]) @ G.T
    return h[:, :2] / h[:, 2:3]


def _pose_of(corners_table: F64) -> F64:
    centre = corners_table.mean(axis=0)
    edge = corners_table[1] - corners_table[0]
    return np.array([*centre, np.arctan2(edge[1], edge[0])])


def _init_poses(frames: list[dict[int, F64]]) -> dict[int, F64]:
    """Marker poses in marker 0's frame, chained across frames when one view lacks a marker."""
    f0 = max((f for f in frames if 0 in f), key=len)
    H0, _ = cv2.findHomography(f0[0], LOCAL)
    poses = {0: np.zeros(3)}
    for i, c in f0.items():
        if i:
            poses[i] = _pose_of(cv2.perspectiveTransform(c[None], H0)[0])
    for _ in range(3):
        for f in frames:
            known = [i for i in f if i in poses]
            if not known or all(i in poses for i in f):
                continue
            src = np.concatenate([f[i] for i in known])
            dst = np.concatenate([_marker_corners(poses[i]) for i in known])
            Hf, _ = cv2.findHomography(src, dst)
            for i, c in f.items():
                if i not in poses:
                    poses[i] = _pose_of(cv2.perspectiveTransform(c[None], Hf)[0])
    return poses


def _fit_G(corners: dict[int, F64], poses: dict[int, F64]) -> F64:
    """Table -> image homography from the visible markers' corners (least squares)."""
    ids = [i for i in corners if i in poses]
    src = np.concatenate([_marker_corners(poses[i]) for i in ids])
    dst = np.concatenate([corners[i] for i in ids])
    G, _ = cv2.findHomography(src, dst, 0)
    return G / G[2, 2]


def _rms(G: F64, corners: dict[int, F64], poses: dict[int, F64]) -> float:
    ids = [i for i in corners if i in poses]
    pts = np.concatenate([_marker_corners(poses[i]) for i in ids])
    err = _project(G, pts) - np.concatenate([corners[i] for i in ids])
    return float(np.sqrt((err**2).sum(axis=1).mean()))


def joint_fit(frames: list[dict[int, F64]]) -> tuple[dict[int, F64], list[F64], float]:
    """Shared marker poses (marker-0 frame) and one table->image homography per frame."""
    poses0 = _init_poses(frames)
    Gs0 = [_fit_G(f, poses0) for f in frames]
    n = len(frames)
    p0 = np.concatenate([*(poses0[i] for i in (1, 2, 3)), *(G.ravel()[:8] for G in Gs0)])
    rows = [(k, i) for k, f in enumerate(frames) for i in MARKER_IDS if i in f]
    target = np.concatenate([frames[k][i] for k, i in rows]).ravel()

    def unpack(p: F64) -> tuple[dict[int, F64], list[F64]]:
        poses = {0: np.zeros(3), 1: p[0:3], 2: p[3:6], 3: p[6:9]}
        Gs = [np.append(p[9 + 8 * k : 17 + 8 * k], 1.0).reshape(3, 3) for k in range(n)]
        return poses, Gs

    def resid(p: F64) -> F64:
        poses, Gs = unpack(p)
        out = [_project(Gs[k], _marker_corners(poses[i])) for k, i in rows]
        return np.concatenate(out).ravel() - target

    sparsity = lil_matrix((len(rows) * 8, len(p0)), dtype=int)
    for r, (k, i) in enumerate(rows):
        if i:
            sparsity[r * 8 : r * 8 + 8, 3 * (i - 1) : 3 * i] = 1
        sparsity[r * 8 : r * 8 + 8, 9 + 8 * k : 17 + 8 * k] = 1
    sol = least_squares(resid, p0, method="trf", jac_sparsity=sparsity, x_scale="jac", max_nfev=200)
    poses, Gs = unpack(sol.x)
    rms = float(np.sqrt((sol.fun.reshape(-1, 2) ** 2).sum(axis=1).mean()))
    return poses, Gs, rms


def _align(poses: dict[int, F64]) -> F64:
    """2D transform A (3×3) taking marker-0 frame to the table frame: marker 0 at the origin,
    marker 1 on +x, marker 3 on the +y side."""
    phi = np.arctan2(poses[1][1], poses[1][0])
    c, s = np.cos(-phi), np.sin(-phi)
    A = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])
    m3 = A @ np.array([poses[3][0], poses[3][1], 1.0])
    if m3[1] < 0:
        A = np.diag([1.0, -1.0, 1.0]) @ A
    return A


def _aligned_poses(poses: dict[int, F64], A: F64) -> dict[int, F64]:
    out = {}
    for i, q in poses.items():
        corners = (A @ np.column_stack([_marker_corners(q), np.ones(4)]).T).T[:, :2]
        out[i] = _pose_of(corners)
    return out


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
    return float(max(width, height) / 2 / np.tan(np.radians(DEFAULT_HFOV_DEG / 2)))


def _tilt_deg(R: F64) -> float:
    return float(np.degrees(np.arccos(np.clip(R[2, 2], -1, 1))))


def solve_focal(
    Gs: list[F64], width: int, height: int
) -> tuple[float, float, float, str, list[str]]:
    """(f, cx, cy, source, warnings): intrinsics, else the median of per-frame Zhang estimates
    on frames tilted ≥ 12°, else a typical phone field of view."""
    intr = load_intrinsics(width, height)
    if intr:
        return (*intr, "intrinsics", [])
    cx, cy = width / 2, height / 2
    est = []
    for G in Gs:
        f = focal_from_homography(G, cx, cy)
        if f is not None and 0.3 * max(width, height) < f < 3 * max(width, height):
            R, _ = pose_from_homography(G, K_matrix(f, cx, cy))
            if _tilt_deg(R) >= MIN_TILT_FOR_FOCAL_DEG:
                est.append(f)
    if est:
        return float(np.median(est)), cx, cy, "homography", []
    warn = "near top-down view: focal length from a typical phone field of view"
    return default_focal(width, height), cx, cy, "default_fov", [warn]


def camera_pose(R: F64, t: F64, K: F64, source: str) -> CameraPose:
    C = -R.T @ t
    look = R[2]  # optical axis in world (x, y, z_down)
    rvec, _ = cv2.Rodrigues(R)
    return CameraPose(
        focal_px=float(K[0, 0]),
        principal_px=(float(K[0, 2]), float(K[1, 2])),
        focal_source=source,
        position_cm=(float(C[0]), float(C[1]), float(-C[2])),
        look_dir=(float(look[0]), float(look[1]), float(-look[2])),
        tilt_deg=_tilt_deg(R),
        nadir_cm=(float(C[0]), float(C[1])),
        rvec=tuple(float(v) for v in rvec.ravel()),
        tvec=tuple(float(v) for v in t),
    )


def camera_of(cal: Calibration) -> Camera:
    R = np.asarray(cv2.Rodrigues(np.array(cal.camera.rvec))[0], float)
    K = K_matrix(cal.camera.focal_px, *cal.camera.principal_px)
    return Camera(K, R, np.array(cal.camera.tvec), *cal.image_size)


# ---------- the track ----------
def _norm(H: np.ndarray) -> F64:
    return H / H[2, 2]


def smooth_and_fill(
    Hs: list[F64 | None], sigma: float = SMOOTH_SIGMA
) -> tuple[list[F64], list[bool]]:
    """Gaussian smoothing over the valid frames' normalised entries, then linear interpolation
    across invalid frames (held constant at the ends). Returns H per frame and the
    'interpolated' flags."""
    n = len(Hs)
    valid = [k for k, H in enumerate(Hs) if H is not None]
    if not valid:
        raise DemoBotError("NO_MARKERS", "no frame shows at least 3 markers", stage="calibrate")
    vals = np.array([_norm(Hs[k]).ravel() for k in valid])  # type: ignore[arg-type]
    idx = np.array(valid, float)
    smooth = np.empty_like(vals)
    for j, k in enumerate(valid):
        w = np.exp(-0.5 * ((idx - k) / sigma) ** 2) if sigma > 0 else (idx == k).astype(float)
        w[np.abs(idx - k) > 3 * max(sigma, 1e-9)] = 0
        smooth[j] = (w[:, None] * vals).sum(axis=0) / w.sum()
    pos = {k: j for j, k in enumerate(valid)}
    out = []
    for k in range(n):
        if k in pos:
            out.append(smooth[pos[k]].reshape(3, 3))
            continue
        before = [v for v in valid if v < k]
        after = [v for v in valid if v > k]
        if not before or not after:
            out.append(smooth[pos[before[-1] if before else after[0]]].reshape(3, 3))
            continue
        a, b = before[-1], after[0]
        f = (k - a) / (b - a)
        out.append(((1 - f) * smooth[pos[a]] + f * smooth[pos[b]]).reshape(3, 3))
    return [_norm(H) for H in out], [k not in pos for k in range(n)]


def _correct_with_visible(H: F64, corners: dict[int, F64], poses: dict[int, F64]) -> F64:
    """An interpolated frame that still shows 1–2 markers: fit a 2D similarity (in-image shift,
    rotation, scale) from the interpolated prediction of those markers to where they are seen,
    and apply it. Small handheld motion between frames is mostly that."""
    ids = [i for i in corners if i in poses]
    G = _norm(np.linalg.inv(H))
    pred = np.concatenate([_project(G, _marker_corners(poses[i])) for i in ids])
    seen = np.concatenate([corners[i] for i in ids])
    S, _ = cv2.estimateAffinePartial2D(pred, seen, method=cv2.LMEDS)
    if S is None:
        return H
    G2 = _norm(np.vstack([S, [0.0, 0.0, 1.0]]) @ G)
    if _rms(G2, {i: corners[i] for i in ids}, poses) > OUTLIER_PX:
        return H
    return _norm(np.linalg.inv(G2))


def build_track(
    obs: list[Obs], width: int, height: int, fps: float
) -> tuple[Calibration, CameraTrack]:
    """Calibration (reference = last clean frame) and the per-frame camera track."""
    check_all_seen(obs)
    blurred = blurred_flags(obs)
    full = [k for k, o in enumerate(obs) if len(o.corners) == 4 and not blurred[k]]
    pool = full or [k for k, o in enumerate(obs) if len(o.corners) >= MIN_MARKERS]
    if not pool:
        raise DemoBotError("NO_MARKERS", "no frame shows at least 3 markers", stage="calibrate")
    pick = sorted(
        {pool[int(i)] for i in np.linspace(0, len(pool) - 1, min(MAX_JOINT_FRAMES, len(pool)))}
    )
    poses, _, rms = joint_fit([obs[k].corners for k in pick])
    poses = _aligned_poses(poses, _align(poses))

    # per-frame homographies (image -> table) from ≥ 3 markers, outliers dropped
    raw: list[F64 | None] = []
    reproj: list[float | None] = []
    for k, o in enumerate(obs):
        if len(o.corners) < MIN_MARKERS or blurred[k]:
            raw.append(None)
            reproj.append(None)
            continue
        G = _fit_G(o.corners, poses)
        e = _rms(G, o.corners, poses)
        ok = e <= OUTLIER_PX
        raw.append(_norm(np.linalg.inv(G)) if ok else None)
        reproj.append(e if ok else None)
    Hs, interp = smooth_and_fill(raw, SMOOTH_SIGMA)
    for k, (H_raw, e_raw) in enumerate(zip(raw, reproj, strict=True)):
        # smoothing removes jitter but must not lag real hand motion
        if H_raw is None or e_raw is None:
            continue
        if _rms(_norm(np.linalg.inv(Hs[k])), obs[k].corners, poses) > e_raw + SMOOTH_SLACK_PX:
            Hs[k] = H_raw
    for k in range(len(obs)):
        if interp[k] and 0 < len(obs[k].corners) < MIN_MARKERS and not blurred[k]:
            Hs[k] = _correct_with_visible(Hs[k], obs[k].corners, poses)
    Gs = [_norm(np.linalg.inv(H)) for H in Hs]
    f, cx, cy, source, warnings = solve_focal(
        [G for G, r in zip(Gs, raw, strict=True) if r is not None], width, height
    )
    K = K_matrix(f, cx, cy)

    frames: list[FrameCam] = []
    for k, (H, G) in enumerate(zip(Hs, Gs, strict=True)):
        R, t = pose_from_homography(G, K)
        C = -R.T @ t
        rvec, _ = cv2.Rodrigues(R)
        frames.append(
            FrameCam(
                t=round(k / fps, 3),
                H_img_to_table=H.tolist(),
                rvec=tuple(float(v) for v in rvec.ravel()),
                tvec=tuple(float(v) for v in t),
                nadir_cm=(float(C[0]), float(C[1])),
                height_cm=float(-C[2]),
                markers_seen=len(obs[k].corners),
                reproj_px=None if interp[k] else reproj[k],
                sharpness=round(obs[k].sharpness, 1),
                blurred=blurred[k],
                interpolated=interp[k],
            )
        )
    clean = [k for k in range(len(obs)) if not interp[k] and not blurred[k]]
    ref = max(clean) if clean else len(obs) - 1
    track = CameraTrack(fps=fps, focal_px=f, principal_px=(cx, cy), frames=frames)
    cal = _calibration(poses, obs, ref, track, K, source, rms, len(pick), (width, height), warnings)
    return cal, track


def _calibration(poses: dict[int, F64], obs: list[Obs], ref: int, track: CameraTrack, K: F64,
                 source: str, rms: float, used: int, size: tuple[int, int],
                 warnings: list[str]) -> Calibration:  # fmt: skip
    fr = track.frames[ref]
    H = np.array(fr.H_img_to_table)
    G = _norm(np.linalg.inv(H))
    R, t = pose_from_homography(G, K)
    markers = []
    for i in MARKER_IDS:
        corners = _marker_corners(poses[i])
        px = obs[ref].corners.get(i)
        if px is None:
            px = _project(G, corners)
        markers.append(
            MarkerPose(
                id=i,
                center_cm=(float(poses[i][0]), float(poses[i][1])),
                theta_rad=float(poses[i][2]),
                corners_cm=[(float(x), float(y)) for x, y in corners],
                corners_px=[(float(x), float(y)) for x, y in px],
            )
        )
    cx = [m.center_cm[0] for m in markers]
    cy = [m.center_cm[1] for m in markers]
    s = WORK_AREA_SHRINK_CM
    work = Rect(x0=min(cx) + s, y0=min(cy) + s, x1=max(cx) - s, y1=max(cy) - s)
    if rms > 1.5:
        warnings = [*warnings, f"marker reprojection {rms:.2f} px is high: are the markers flat?"]
    centre = np.array([[(work.x0 + work.x1) / 2, (work.y0 + work.y1) / 2]])
    drift = np.array([_project(_norm(np.linalg.inv(np.array(f.H_img_to_table))), centre)[0]
                      for f in track.frames])  # fmt: skip
    motion = float(np.linalg.norm(drift - drift.mean(axis=0), axis=1).max())
    n_interp = sum(f.interpolated for f in track.frames)
    if n_interp > 0.3 * len(track.frames):
        warnings.append(f"{n_interp} of {len(track.frames)} frames lacked 3 sharp markers")
    m = RECT_MARGIN_CM
    return Calibration(
        image_size=size,
        H_img_to_table=H.tolist(),
        markers=markers,
        work_area=work,
        robot_base_cm=((work.x0 + work.x1) / 2, work.y1 + ROBOT_BEHIND_FRONT_CM),
        camera=camera_pose(R, t, K, source),
        method="markers_plus_intrinsics" if source == "intrinsics" else "markers_bundle",
        reprojection_px=rms,
        frames_used=used,
        rectify_px_per_cm=RECT_PX_PER_CM,
        rectify_origin_cm=(min(cx) - _S - m, min(cy) - _S - m),
        rectify_size=(
            round((max(cx) - min(cx) + 2 * (_S + m)) * RECT_PX_PER_CM),
            round((max(cy) - min(cy) + 2 * (_S + m)) * RECT_PX_PER_CM),
        ),
        reference_t=fr.t,
        frames_total=len(track.frames),
        frames_blurred=sum(f.blurred for f in track.frames),
        frames_interpolated=n_interp,
        max_motion_px=round(motion, 2),
        warnings=warnings,
    )


def calibrate_corners(img: dict[int, F64], width: int, height: int) -> Calibration:
    """Calibration from a single frame's corners (a still image)."""
    cal, _ = build_track([Obs(img, 1.0)], width, height, 10.0)
    return cal


def H_at(track: CameraTrack, t: float) -> F64:
    """Image -> table homography at time t (linear between analysis frames)."""
    k = t * track.fps
    a = int(np.clip(np.floor(k), 0, len(track.frames) - 1))
    b = min(a + 1, len(track.frames) - 1)
    f = float(np.clip(k - a, 0, 1))
    Ha, Hb = np.array(track.frames[a].H_img_to_table), np.array(track.frames[b].H_img_to_table)
    return _norm((1 - f) * Ha + f * Hb)


# ---------- images ----------
def rectify_matrix(cal: Calibration, H: F64 | None = None) -> F64:
    """Image pixels -> rectified pixels (10 px/cm, table-aligned, +y down)."""
    s = cal.rectify_px_per_cm
    ox, oy = cal.rectify_origin_cm
    S = np.array([[s, 0, -ox * s], [0, s, -oy * s], [0, 0, 1.0]])
    return S @ (np.array(cal.H_img_to_table) if H is None else H)


def rectify(frame: np.ndarray, cal: Calibration, H: F64 | None = None) -> np.ndarray:
    return cv2.warpPerspective(
        frame, rectify_matrix(cal, H), cal.rectify_size, flags=cv2.INTER_LINEAR
    )


def overlay_layer(cal: Calibration, track: CameraTrack) -> dict[str, object]:
    """Debug overlay for the UI in stabilised display pixels (the first frame's view): marker
    outlines, the table axes and the work area."""
    G0 = _norm(np.linalg.inv(np.array(track.frames[0].H_img_to_table)))
    wa = cal.work_area
    axes = _project(G0, np.array([[0.0, 0.0], [10.0, 0.0], [0.0, 10.0]]))
    work = _project(G0, np.array([[wa.x0, wa.y0], [wa.x1, wa.y0], [wa.x1, wa.y1], [wa.x0, wa.y1]]))
    return {
        "markers": [
            {"id": m.id, "corners_px": _project(G0, np.array(m.corners_cm)).tolist()}
            for m in cal.markers
        ],
        "axes_px": {
            "origin": axes[0].tolist(),
            "x10cm": axes[1].tolist(),
            "y10cm": axes[2].tolist(),
        },
        "work_area_px": work.tolist(),
    }


def stabilise(raw: Path, track: CameraTrack, out: Path) -> list[list[list[float]]]:
    """Warp every frame of display_raw.mp4 into the first frame's view (M_t = G_0 · H_t), keep
    the audio, and return M_t per display frame."""
    cap = cv2.VideoCapture(str(raw))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    G0 = _norm(np.linalg.inv(np.array(track.frames[0].H_img_to_table)))
    tmp = out.with_suffix(".video.mp4")
    ff = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
         "-r", f"{fps}", "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
         "-pix_fmt", "yuv420p", str(tmp)], stdin=subprocess.PIPE,
    )  # fmt: skip
    Ms = []
    i = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            M = _norm(G0 @ H_at(track, i / fps))
            Ms.append([[round(v, 7) for v in row] for row in M.tolist()])
            warped = cv2.warpPerspective(
                frame, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                borderValue=(24, 24, 28),
            )  # fmt: skip
            assert ff.stdin is not None
            ff.stdin.write(warped.tobytes())
            i += 1
    finally:
        cap.release()
        assert ff.stdin is not None
        ff.stdin.close()
        ff.wait()
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(tmp), "-i", str(raw), "-map", "0:v",
         "-map", "1:a?", "-c:v", "copy", "-c:a", "copy", "-movflags", "+faststart", str(out)],
        check=True,
    )  # fmt: skip
    tmp.unlink()
    return Ms


def run(video: Path, out_dir: Path, display_raw: Path | None = None) -> Calibration:
    """Calibrate from the analysis clip; writes calibration.json, camera_track.json, rectified
    first/last frames, the overlay, and (given display_raw) the stabilised display.mp4."""
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 10.0
    obs: list[Obs] = []
    first = None
    size = (0, 0)
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if first is None:
            first = frame
            size = (frame.shape[1], frame.shape[0])
        obs.append(observe(frame))
    if first is None:
        cap.release()
        raise DemoBotError("NOT_A_VIDEO", "could not read frames", stage="calibrate")
    cal, track = build_track(obs, size[0], size[1], fps)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "calibration.json").write_text(cal.model_dump_json(indent=1))
    (out_dir / "camera_track.json").write_text(track.model_dump_json())
    (out_dir / "calibration_overlay.json").write_text(json.dumps(overlay_layer(cal, track)))
    cv2.imwrite(str(out_dir / "rectified_first.png"),
                rectify(first, cal, np.array(track.frames[0].H_img_to_table)))  # fmt: skip
    cap.set(cv2.CAP_PROP_POS_FRAMES, round(cal.reference_t * fps))
    ok, last = cap.read()
    cap.release()
    if ok:
        cv2.imwrite(str(out_dir / "rectified_last.png"), rectify(last, cal))
        cv2.imwrite(str(out_dir / "reference_frame.jpg"), last)
    if display_raw is not None and display_raw.exists():
        Ms = stabilise(display_raw, track, out_dir / "display.mp4")
        (out_dir / "stabilise.json").write_text(json.dumps({"M": Ms}))
    return cal
