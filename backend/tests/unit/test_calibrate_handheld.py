"""Calibration with a handheld (moving) camera: per-frame homographies, smoothing,
interpolation across frames without markers, the blur flag, and the stabilised display."""

import subprocess
from pathlib import Path

import cv2
import numpy as np

from demobot import calibrate
from demobot.camera import apply_h
from synth.demo import shaky_cameras
from synth.table import draw_texture, render_table, sample_camera, sample_markers

N = 40  # analysis frames at 10 fps


def sequence(seed: int, shake: float = 2.0, tilt: float = 25.0):  # type: ignore[no-untyped-def]
    rng = np.random.default_rng(seed)
    truth = draw_texture(sample_markers(rng), rng)
    cam = sample_camera(truth, rng, tilt_deg=tilt)
    cams = shaky_cameras(cam, N * 3, rng, shake)[::3]  # 30 fps shake sampled at 10 fps
    imgs = [render_table(truth, c, rng=rng) for c in cams]
    return truth, cams, imgs


def table_err(cal_H: np.ndarray, cam) -> float:  # type: ignore[no-untyped-def]
    """Max error (cm) mapping image points of known table points back through H."""
    pts = np.array([[5.0, 5.0], [30.0, 20.0], [55.0, 35.0], [10.0, 35.0]])
    back = apply_h(cal_H, apply_h(cam.table_to_image(), pts))
    return float(np.abs(back - pts).max())


def test_moving_camera_gives_accurate_per_frame_homographies() -> None:
    truth, cams, imgs = sequence(1, shake=1.0)
    obs = [calibrate.observe(im) for im in imgs]
    cal, track = calibrate.build_track(obs, 1280, 720, 10.0)
    for m in cal.markers:
        x, y, _ = truth.markers[m.id]
        assert np.hypot(m.center_cm[0] - x, m.center_cm[1] - y) < 0.8
    assert cal.reprojection_px < 1.5 and cal.max_motion_px > 3  # it really moved
    errs = [
        table_err(np.array(f.H_img_to_table), c) for f, c in zip(track.frames, cams, strict=True)
    ]
    assert max(errs) < 0.6
    # a single fixed homography would be wrong by more than a centimetre somewhere
    assert max(table_err(np.array(track.frames[0].H_img_to_table), c) for c in cams) > 0.8
    heights = [f.height_cm for f in track.frames]
    true_h = [-c.center[2] for c in cams]
    assert np.abs(np.array(heights) - np.array(true_h)).max() < 3.0


def test_frames_without_three_markers_are_interpolated() -> None:
    _, cams, imgs = sequence(2, shake=1.0)
    for k in (12, 13, 14):  # a hand covers two markers for three frames
        det = calibrate.detect_markers(imgs[k])
        for i in (0, 1):
            x, y = det[i].mean(axis=0).astype(int)
            imgs[k][y - 50 : y + 50, x - 50 : x + 50] = 120
    obs = [calibrate.observe(im) for im in imgs]
    assert obs[13].corners.keys() == {2, 3}
    _, track = calibrate.build_track(obs, 1280, 720, 10.0)
    for k in (12, 13, 14):
        f = track.frames[k]
        assert f.interpolated and f.reproj_px is None
        assert table_err(np.array(f.H_img_to_table), cams[k]) < 1.2
    assert not track.frames[11].interpolated


def test_blurred_frames_are_flagged_and_not_the_reference() -> None:
    _, _, imgs = sequence(3)
    imgs[-1] = cv2.GaussianBlur(imgs[-1], (0, 0), 4)
    obs = [calibrate.observe(im) for im in imgs]
    cal, track = calibrate.build_track(obs, 1280, 720, 10.0)
    assert track.frames[-1].blurred and cal.frames_blurred >= 1
    assert cal.reference_t == track.frames[-2].t  # the last clean frame


def test_stabilised_display_holds_markers_still(tmp_path: Path) -> None:
    _, _, imgs = sequence(4, shake=3.0)
    analysis = tmp_path / "analysis.mp4"
    raw = tmp_path / "display_raw.mp4"
    for path, fps, frames in (
        (analysis, 10, imgs),
        (raw, 30, [im for im in imgs for _ in range(3)]),
    ):
        vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (1280, 720))
        for im in frames:
            vw.write(im)
        vw.release()
    cal = calibrate.run(analysis, tmp_path / "out", raw)
    out = tmp_path / "out"
    for name in ("display.mp4", "camera_track.json", "stabilise.json", "rectified_last.png"):
        assert (out / name).exists(), name
    first = calibrate.detect_markers(imgs[0])
    cap = cv2.VideoCapture(str(out / "display.mp4"))
    worst_raw, worst_stab = 0.0, 0.0
    k = 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        if k % 9 == 0:
            det = calibrate.detect_markers(fr)
            raw_det = calibrate.detect_markers(imgs[k // 3])
            for i in det.keys() & first.keys():
                worst_stab = max(worst_stab, float(np.abs(det[i] - first[i]).max()))
            for i in raw_det.keys() & first.keys():
                worst_raw = max(worst_raw, float(np.abs(raw_det[i] - first[i]).max()))
        k += 1
    cap.release()
    assert k == 3 * N and worst_raw > 8 and worst_stab < 3.0
    assert cal.frames_total == N
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                          "csv=p=0", str(out / "display.mp4")], capture_output=True, text=True)  # fmt: skip
    assert abs(float(dur.stdout) - N / 10) < 0.2
