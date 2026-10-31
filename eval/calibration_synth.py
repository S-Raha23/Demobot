"""Calibration accuracy on the synthetic set (M1 acceptance): ingest + calibrate each clip and
compare with the exact ground truth, including the per-frame handheld camera track.

    uv run python -m eval.calibration_synth data/synth/set7 [--json out.json]
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

from demobot import calibrate, media
from demobot.camera import Camera, apply_h

PROBE_CM = np.array([[10.0, 10.0], [30.0, 20.0], [50.0, 30.0], [15.0, 32.0], [45.0, 8.0]])


def check_clip(clip_dir: Path) -> dict[str, object]:
    truth = json.loads((clip_dir / "truth.json").read_text())
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        info = media.ingest(clip_dir / "clip.mp4", out)
        cal = calibrate.run(out / "analysis.mp4", out)
        track = json.loads((out / "camera_track.json").read_text())
    marker_err = max(
        float(
            np.hypot(
                m.center_cm[0] - truth["markers"][str(m.id)][0],
                m.center_cm[1] - truth["markers"][str(m.id)][1],
            )
        )
        for m in cal.markers
    )
    K = np.array(truth["camera"]["K"])
    cams = truth["camera_track"]
    errs = []
    for k, fr in enumerate(track["frames"]):
        j = round(info.trim_start_s * 10) + k
        if j >= len(cams):
            break
        cam = Camera(K, np.array(cams[j]["R"]), np.array(cams[j]["t_vec"]), *truth["size"])
        back = apply_h(np.array(fr["H_img_to_table"]), apply_h(cam.table_to_image(), PROBE_CM))
        errs.append(float(np.abs(back - PROBE_CM).max()))
    return {
        "clip": clip_dir.name,
        "tilt_deg": round(truth["camera"]["tilt_deg"], 1),
        "marker_err_cm": round(marker_err, 3),
        "reprojection_px": round(cal.reprojection_px, 3),
        "frame_err_cm_median": round(float(np.median(errs)), 3),
        "frame_err_cm_p95": round(float(np.percentile(errs, 95)), 3),
        "frames_interpolated": cal.frames_interpolated,
        "drift_px": cal.max_motion_px,
        "focal_source": cal.camera.focal_source,
        "pass": marker_err < 0.8 and cal.reprojection_px < 1.5,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("set_dir")
    ap.add_argument("--json")
    a = ap.parse_args()
    rows = [check_clip(d) for d in sorted(Path(a.set_dir).iterdir()) if (d / "truth.json").exists()]
    keys = list(rows[0])
    print(" | ".join(keys))
    for r in rows:
        print(" | ".join(str(r[k]) for k in keys))
    ok = sum(bool(r["pass"]) for r in rows)
    print(
        f"\n{ok}/{len(rows)} clips pass (marker error < 0.8 cm and reprojection < 1.5 px)",
        file=sys.stderr,
    )
    if a.json:
        Path(a.json).write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
