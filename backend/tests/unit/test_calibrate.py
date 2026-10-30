import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from demobot import calibrate
from demobot.camera import apply_h, focal_from_homography, look_at, parallax_correct
from demobot.config import settings
from demobot.errors import DemoBotError
from synth.table import draw_texture, render_table, sample_camera, sample_markers


def scene(seed: int, tilt: float | None = None):
    rng = np.random.default_rng(seed)
    truth = draw_texture(sample_markers(rng), rng)
    cam = sample_camera(truth, rng, tilt_deg=tilt)
    return truth, cam, render_table(truth, cam, rng=rng)


@pytest.mark.parametrize(("seed", "tilt"), [(1, 0.0), (2, 15.0), (3, 30.0), (4, 45.0), (5, None)])
def test_markers_within_tolerance_on_synthetic_tables(seed: int, tilt: float | None) -> None:
    """M1 acceptance: marker positions err < 0.8 cm, plane reprojection < 1.5 px."""
    truth, cam, img = scene(seed, tilt)
    cal = calibrate.calibrate_corners(calibrate.detect_markers(img), cam.width, cam.height, 1)
    for m in cal.markers:
        x, y, _ = truth.markers[m.id]
        assert np.hypot(m.center_cm[0] - x, m.center_cm[1] - y) < 0.8
    assert cal.reprojection_px < 1.5
    m1, m3 = cal.markers[1].center_cm, cal.markers[3].center_cm
    assert m1[0] > 0 and abs(m1[1]) < 1e-6 and m3[1] > 0  # the frame convention


def test_homography_maps_table_points_exactly() -> None:
    _, cam, img = scene(6, 25.0)
    cal = calibrate.calibrate_corners(calibrate.detect_markers(img), cam.width, cam.height, 1)
    pts = np.array([[10.0, 10.0], [40.0, 30.0], [55.0, 5.0]])
    px = apply_h(cam.table_to_image(), pts)
    back = apply_h(np.array(cal.H_img_to_table), px)
    assert np.abs(back - pts).max() < 0.6


def test_camera_pose_recovered_for_oblique_view() -> None:
    _, cam, img = scene(7, 30.0)
    cal = calibrate.calibrate_corners(calibrate.detect_markers(img), cam.width, cam.height, 1)
    C = cam.center
    assert cal.camera.focal_source == "homography"
    assert abs(cal.camera.focal_px - cam.K[0, 0]) / cam.K[0, 0] < 0.03
    assert abs(cal.camera.position_cm[2] - (-C[2])) < 2.0  # height
    assert np.hypot(cal.camera.nadir_cm[0] - C[0], cal.camera.nadir_cm[1] - C[1]) < 2.0
    assert 25 < cal.camera.tilt_deg < 35


def test_top_down_view_uses_default_focal_with_a_warning() -> None:
    _, cam, img = scene(8, 0.0)
    cal = calibrate.calibrate_corners(calibrate.detect_markers(img), cam.width, cam.height, 1)
    assert cal.camera.focal_source == "default_fov" and cal.warnings


def test_intrinsics_file_is_scaled_and_rotated(monkeypatch, tmp_path: Path) -> None:
    d = settings.data_path / "calibration"
    d.mkdir(parents=True)
    k = {"width": 1080, "height": 1920, "fx": 1540, "fy": 1548, "cx": 557, "cy": 987}
    (d / "intrinsics.json").write_text(json.dumps(k))
    f, cx, cy = calibrate.load_intrinsics(720, 1280)  # type: ignore[misc]
    assert f == pytest.approx(1544 * 720 / 1080) and cx == pytest.approx(557 * 720 / 1080)
    f, cx, cy = calibrate.load_intrinsics(1280, 720)  # type: ignore[misc]  # landscape clip
    assert cx == pytest.approx(987 * 1280 / 1920) and cy == pytest.approx(557 * 720 / 1080)
    assert calibrate.load_intrinsics(1000, 1000) is None  # aspect mismatch


def test_missing_marker_names_it() -> None:
    _, _, img = scene(9, 20.0)
    det = calibrate.detect_markers(img)
    x, y = det[2].mean(axis=0).astype(int)
    img[y - 60 : y + 60, x - 60 : x + 60] = 90  # cover marker 2
    with pytest.raises(DemoBotError) as err:
        calibrate.median_corners([img])
    assert err.value.code == "NO_MARKERS" and "2" in err.value.message


def test_focal_from_homography_exact_and_degenerate() -> None:
    cam = look_at((30, 70, 60), (30, 20), 1000.0, 1280, 720)
    assert focal_from_homography(cam.table_to_image(), 640, 360) == pytest.approx(1000, rel=1e-6)
    top = look_at((30, 20, 80), (30, 20), 1000.0, 1280, 720)
    assert focal_from_homography(top.table_to_image(), 640, 360) is None


def test_parallax_correction_matches_projection() -> None:
    cam = look_at((30, 70, 60), (30, 20), 1000.0, 1280, 720)
    top = np.array([[12.0, 18.0, -8.0]])  # 8 cm above the table
    px = cam.project(top)
    on_plane = apply_h(np.linalg.inv(cam.table_to_image()), px)[0]
    C = cam.center
    fixed = parallax_correct(on_plane, (C[0], C[1]), -C[2], 8.0)
    assert np.allclose(fixed, top[0, :2], atol=1e-6)


def test_run_writes_outputs_from_a_clip(tmp_path: Path) -> None:
    truth, cam, img = scene(10, 20.0)
    clip = tmp_path / "clip.mp4"
    vw = cv2.VideoWriter(str(clip), cv2.VideoWriter_fourcc(*"mp4v"), 10, (cam.width, cam.height))
    for _ in range(12):
        vw.write(img)
    vw.release()
    cal = calibrate.run(clip, tmp_path / "out")
    for name in ("calibration.json", "calibration_overlay.json", "rectified_first.png"):
        assert (tmp_path / "out" / name).exists()
    assert cal.frames_used >= 10
    rect = cv2.imread(str(tmp_path / "out" / "rectified_first.png"))
    assert rect.shape[1] == cal.rectify_size[0] and rect.shape[0] == cal.rectify_size[1]
    # the rectified image is metric: marker 1 sits where its table position says
    found = calibrate.detect_markers(rect)
    ox, oy = cal.rectify_origin_cm
    c1 = found[1].mean(axis=0) / cal.rectify_px_per_cm + np.array([ox, oy])
    assert np.hypot(*(c1 - np.array(truth.markers[1][:2]))) < 0.8
