"""Phone intrinsics from the checkerboard video (the optional calibration path, docs/04 §2).

    uv run python scripts/calibrate_camera.py [data/calibration/checkerboard.mp4]

9 × 6 inner corners, 25 mm squares. Writes data/calibration/intrinsics.json.
"""

import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PATTERN = (9, 6)
SQUARE_MM = 25.0
SAMPLES = 90
MAX_VIEWS = 40


def main() -> None:
    video = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/calibration/checkerboard.mp4"
    cap = cv2.VideoCapture(str(video))  # applies the rotation metadata
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    obj = np.zeros((PATTERN[0] * PATTERN[1], 3), np.float32)
    obj[:, :2] = np.mgrid[0 : PATTERN[0], 0 : PATTERN[1]].T.reshape(-1, 2) * SQUARE_MM
    views: list[np.ndarray] = []
    size = None
    for i in np.linspace(0, total - 1, SAMPLES).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, frame = cap.read()
        if not ok:
            continue
        grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        size = grey.shape[::-1]
        found, corners = cv2.findChessboardCornersSB(
            grey, PATTERN, flags=cv2.CALIB_CB_NORMALIZE_IMAGE
        )
        if found:
            views.append(corners.reshape(-1, 2))
    cap.release()
    if len(views) < 8 or size is None:
        sys.exit(f"only {len(views)} checkerboard views found; need at least 8")
    pick = np.linspace(0, len(views) - 1, min(MAX_VIEWS, len(views))).astype(int)
    imgs = [views[k].astype(np.float32) for k in pick]
    rms, K, dist, _, _ = cv2.calibrateCamera(
        [obj] * len(imgs), imgs, size, None, None, flags=cv2.CALIB_FIX_K3
    )
    out = {
        "width": size[0],
        "height": size[1],
        "fx": float(K[0, 0]),
        "fy": float(K[1, 1]),
        "cx": float(K[0, 2]),
        "cy": float(K[1, 2]),
        "dist": [float(d) for d in dist.ravel()],
        "rms_px": float(rms),
        "views": len(imgs),
        "source": video.name,
        "hfov_deg": float(np.degrees(2 * np.arctan(size[0] / 2 / K[0, 0]))),
    }
    dest = ROOT / "data/calibration/intrinsics.json"
    dest.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
