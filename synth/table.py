"""The synthetic table: a desk texture with the four ArUco markers glued at random positions,
seen by a random phone-like camera. Ground truth is exact (docs/09 "Synthetic demo generator")."""

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from demobot.camera import Camera, look_at

TEX_PX_PER_CM = 12.0
MARKER_CM = 6.0
PAPER_MARGIN_CM = 1.0  # the white border of each printed marker
DESK_BGR = (120, 160, 196)  # light wood
WOOD = Path(__file__).resolve().parents[1] / "assets" / "textures" / "desk_wood.png"


@dataclass
class TableTruth:
    markers: dict[int, tuple[float, float, float]]  # id -> (x, y, θ) in the table frame
    extent: tuple[float, float, float, float]  # x0, y0, x1, y1 of the texture, cm
    texture: np.ndarray

    def tex_to_table(self) -> np.ndarray:
        """Texture pixel -> table cm."""
        x0, y0, _, _ = self.extent
        s = 1 / TEX_PX_PER_CM
        return np.array([[s, 0, x0], [0, s, y0], [0, 0, 1.0]])


def sample_markers(rng: np.random.Generator) -> dict[int, tuple[float, float, float]]:
    """Marker 0 at the origin, a 55–65 × 35–45 cm rectangle, each marker jittered and slightly
    rotated, and the whole rectangle rotated a few degrees. Then re-expressed in the table frame
    (marker 0 origin, marker 1 on +x), which is what calibration recovers."""
    w, h = rng.uniform(55, 65), rng.uniform(35, 45)
    rot = np.radians(rng.uniform(-4, 4))
    nominal = {0: (0.0, 0.0), 1: (w, 0.0), 2: (w, h), 3: (0.0, h)}
    raw: dict[int, tuple[float, float, float]] = {}
    c, s = np.cos(rot), np.sin(rot)
    for i, (x, y) in nominal.items():
        jx, jy = (0.0, 0.0) if i == 0 else tuple(rng.uniform(-2, 2, 2))
        xr, yr = c * (x + jx) - s * (y + jy), s * (x + jx) + c * (y + jy)
        raw[i] = (xr, yr, rot + np.radians(rng.uniform(-8, 8)))
    phi = np.arctan2(raw[1][1], raw[1][0])
    c, s = np.cos(-phi), np.sin(-phi)
    return {i: (c * x - s * y, s * x + c * y, th - phi) for i, (x, y, th) in raw.items()}


def draw_texture(
    markers: dict[int, tuple[float, float, float]], rng: np.random.Generator
) -> TableTruth:
    xs = [m[0] for m in markers.values()]
    ys = [m[1] for m in markers.values()]
    pad = 40.0
    extent = (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)
    W = int((extent[2] - extent[0]) * TEX_PX_PER_CM)
    H = int((extent[3] - extent[1]) * TEX_PX_PER_CM)
    tex = np.empty((H, W, 3), np.uint8)
    wood = WOOD.exists() and rng.uniform() < 0.7
    if wood:  # a Muse Image wood swatch, ~40 cm per tile, tiled with mirrored seams
        sw = cv2.imread(str(WOOD))
        side = int(40 * TEX_PX_PER_CM)
        sw = cv2.resize(sw, (side, side), interpolation=cv2.INTER_AREA)
        if rng.uniform() < 0.5:
            sw = cv2.rotate(sw, cv2.ROTATE_90_CLOCKWISE)
        row = np.concatenate([sw, sw[:, ::-1]], axis=1)
        tile = np.concatenate([row, row[::-1]], axis=0)
        reps = (H // tile.shape[0] + 1, W // tile.shape[1] + 1, 1)
        tex[:] = np.tile(tile, reps)[:H, :W]
    else:
        tex[:] = DESK_BGR
    grain = rng.normal(0, 6 if not wood else 2, (H // 8 + 1, W // 2 + 1)).astype(np.float32)
    grain = cv2.resize(grain, (W, H), interpolation=cv2.INTER_LINEAR)
    tex = np.clip(tex.astype(np.float32) + grain[..., None], 0, 255).astype(np.uint8)
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    side = int(MARKER_CM * TEX_PX_PER_CM)
    margin = int(PAPER_MARGIN_CM * TEX_PX_PER_CM)
    for i, (x, y, th) in markers.items():
        mk = cv2.aruco.generateImageMarker(dictionary, i, side)
        paper = np.full((side + 2 * margin, side + 2 * margin), 250, np.uint8)
        paper[margin : margin + side, margin : margin + side] = mk
        paper = cv2.cvtColor(paper, cv2.COLOR_GRAY2BGR)
        half = (side + 2 * margin) / 2
        c, s = np.cos(th), np.sin(th)
        cx = (x - extent[0]) * TEX_PX_PER_CM
        cy = (y - extent[1]) * TEX_PX_PER_CM
        # paper pixel -> texture pixel: rotate about the paper centre by θ, then translate
        M = np.array([[c, -s, cx - c * half + s * half], [s, c, cy - s * half - c * half]])
        mask = cv2.warpAffine(np.full(paper.shape[:2], 255, np.uint8), M, (W, H))
        warped = cv2.warpAffine(paper, M, (W, H), flags=cv2.INTER_AREA)
        tex[mask > 128] = warped[mask > 128]
    return TableTruth(markers, extent, tex)


def sample_camera(
    truth: TableTruth,
    rng: np.random.Generator,
    width: int = 1280,
    height: int = 720,
    tilt_deg: float | None = None,
) -> Camera:
    """A phone on the robot side (+y), 0–45° from vertical, looking at the rectangle centre."""
    xs = [m[0] for m in truth.markers.values()]
    ys = [m[1] for m in truth.markers.values()]
    target = (float(np.mean(xs)) + rng.uniform(-3, 3), float(np.mean(ys)) + rng.uniform(-3, 3))
    tilt = np.radians(rng.uniform(0, 45) if tilt_deg is None else tilt_deg)
    f = max(width, height) / 2 / np.tan(np.radians(rng.uniform(60, 70) / 2))
    # distance so the ~70 × 50 cm area fills most of the frame
    dist = 1.15 * max(np.ptp(xs) + 12, (np.ptp(ys) + 12) * width / height) * f / width
    height_cm = dist * np.cos(tilt)
    back = dist * np.sin(tilt)
    pos = (target[0] + rng.uniform(-4, 4), target[1] + back, height_cm)
    return look_at(pos, target, f, width, height)


def render_table(
    truth: TableTruth, cam: Camera, noise: float = 2.0, rng: np.random.Generator | None = None
) -> np.ndarray:
    G = cam.table_to_image() @ truth.tex_to_table()
    img = cv2.warpPerspective(
        truth.texture, G, (cam.width, cam.height), flags=cv2.INTER_AREA, borderValue=(60, 60, 60)
    )
    if noise and rng is not None:
        img = np.clip(img + rng.normal(0, noise, img.shape), 0, 255).astype(np.uint8)
    return img
