"""SAM parsing on recorded outputs, and grounding on constructed tracks (no network)."""

from pathlib import Path

import numpy as np

from demobot import ground, perceive
from demobot.schemas import (
    CameraTrack,
    FrameCam,
    GoalClause,
    SceneObject,
    Selector,
    SpecObject,
    Step,
    TaskSpec,
    Track,
    TrackFrame,
)  # fmt: skip

SAM = Path(__file__).parents[1] / "fixtures" / "sam"


def test_parse_recorded_sam_video_and_image() -> None:
    frames = perceive.parse_sam((SAM / "video_red_cube.txt").read_text(), "video")
    assert sorted(frames) == list(range(30))
    i0 = frames[0][0]
    assert i0.object_id == "0" and i0.area > 100 and len(i0.poly) >= 4
    x0, y0, x1, y1 = i0.box
    assert x0 <= i0.centroid[0] <= x1 and y0 <= i0.centroid[1] <= y1
    tracks = perceive.split_tracks(frames, 30)
    assert perceive.quality(tracks["0"], 30) == 1.0
    img = perceive.parse_sam((SAM / "image_cube.txt").read_text(), "image")
    assert len(img[0]) == 2  # the probe found two cubes in the still


def test_base_phrase_and_ordinals() -> None:
    assert perceive.base_phrase("left teal pen") == perceive.base_phrase("teal pen 2") == "teal pen"
    names = ["right teal pen", "left teal pen"]
    assert sorted(names, key=perceive._ordinal_key) == ["left teal pen", "right teal pen"]


def identity_track(n: int, fps: float = 10.0) -> CameraTrack:
    """A camera whose pixel = 10 × cm (top-down, 1 px = 1 mm), 200 cm above the table."""
    H = [[0.1, 0, 0], [0, 0.1, 0], [0, 0, 1]]
    fr = [FrameCam(t=k / fps, H_img_to_table=H, rvec=(0, 0, 0), tvec=(0, 0, 200), nadir_cm=(30, 20),
                   height_cm=200, markers_seen=4, reproj_px=0.1, sharpness=1, blurred=False, interpolated=False)
          for k in range(n)]  # fmt: skip
    return CameraTrack(fps=fps, focal_px=1000, principal_px=(640, 360), frames=fr)


def obj_track(name: str, path: list[tuple[float, float] | None], size_px: float = 40) -> Track:
    frames = []
    for k, p in enumerate(path):
        if p is None:
            frames.append(TrackFrame(t=k / 10, bbox_px=None))
            continue
        x, y = p[0] * 10, p[1] * 10
        h = size_px / 2
        poly = [(x - h, y - h), (x + h, y - h), (x + h, y + h), (x - h, y + h)]
        frames.append(TrackFrame(t=k / 10, bbox_px=(x - h, y - h, x + h, y + h), centroid_px=(x, y),
                                 poly_px=poly, area_px=size_px**2))  # fmt: skip
    return Track(name=name, phrase=name, quality=1.0, frames=frames)


def scenario() -> tuple[TaskSpec, list[Track]]:
    """An eraser carried from (10, 10) to (40, 22) between t = 2 s and 4 s (hidden by the hand
    while carried), next to a static box at (40, 15)."""
    n = 70
    eraser: list[tuple[float, float] | None] = []
    hand: list[tuple[float, float] | None] = []
    for k in range(n):
        t = k / 10
        if t < 2.0:
            eraser.append((10, 10))
            hand.append(None if t < 1.4 else (10, 10))
        elif t <= 4.0:
            a = (t - 2.0) / 2.0
            eraser.append(None)  # occluded by the hand
            hand.append((10 + 30 * a, 10 + 12 * a))
        else:
            eraser.append((40, 22))
            hand.append((40, 22) if t < 4.5 else None)
    spec = TaskSpec(
        summary="eraser in front of the box",
        objects=[SpecObject(name="eraser", kind="eraser", role="moved", est_height_cm=1.5, est_size_cm=(4, 4)),
                 SpecObject(name="box", kind="box", role="reference", est_height_cm=6, est_size_cm=(10, 10))],
        steps=[Step(action="place_next_to", object="eraser", target="box", relation="in_front_of", t_start=1.8, t_end=4.2)],
        goal=[GoalClause(quant="the", select=Selector(name="eraser"), pred="in_front_of", target=Selector(name="box"))],
        generalization="",
    )  # fmt: skip
    tracks = [obj_track("eraser", eraser), obj_track("box", [(40, 15)] * n, size_px=60),
              obj_track("hand", hand, size_px=90)]  # fmt: skip
    return spec, tracks


def test_ground_finds_the_carry_contacts_and_match() -> None:
    from demobot.schemas import Calibration, CameraPose, Rect

    spec, tracks = scenario()
    cam = identity_track(len(tracks[0].frames))
    cal = Calibration(image_size=(1280, 720), H_img_to_table=cam.frames[0].H_img_to_table, markers=[],
                      work_area=Rect(x0=4, y0=4, x1=56, y1=36), robot_base_cm=(30, 64),
                      camera=CameraPose(focal_px=1000, principal_px=(640, 360), focal_source="default_fov",
                                        position_cm=(30, 20, 200), look_dir=(0, 0, -1), tilt_deg=0,
                                        nadir_cm=(30, 20), rvec=(0, 0, 0), tvec=(0, 0, 200)),
                      method="markers_bundle", reprojection_px=0.1, frames_used=1, reference_t=6.9)  # fmt: skip
    gd = ground.ground(spec, tracks, {}, cal, cam, 10.0)
    e0 = next(o for o in gd.initial if o.name == "eraser")
    e1 = next(o for o in gd.final if o.name == "eraser")
    assert abs(e0.x - 10) < 0.3 and abs(e1.x - 40) < 0.3 and abs(e1.y - 22) < 0.3
    seg = [s for s in gd.segments if s.object == "eraser"]
    assert (
        len(seg) == 1 and 1.2 <= seg[0].t0 <= 2.1 and 3.9 <= seg[0].t1 <= 4.6
    )  # hand covers it from 1.4 s
    kinds = [c.type for c in gd.contacts if c.object == "eraser"]
    assert kinds == ["grasp", "release"]
    assert gd.matches[0].segment == 0 and gd.matches[0].confidence > 0.5
    assert gd.real_world[0].holds  # in front of the box: gap 22 − 1.5... within the window
    box = next(o for o in gd.initial if o.name == "box")
    assert box.hollow and abs(box.w - 6) < 1  # the box mask is 6 cm wide


def test_untracked_objects_never_pass_vacuously() -> None:
    spec, tracks = scenario()
    spec.goal = [
        GoalClause(
            quant="all", select=Selector(kind="eraser"), pred="inside", target=Selector(name="box")
        )
    ]
    tracks[0] = Track(name="eraser", phrase="eraser", quality=0, flags=["not_found"], frames=[])
    cam = identity_track(len(tracks[1].frames))
    cal = _calib(cam)
    gd = ground.ground(spec, tracks, {}, cal, cam, 10.0)
    assert not gd.real_world[0].holds and gd.real_world[0].code == "NOT_TRACKED"


def _calib(cam: CameraTrack):  # type: ignore[no-untyped-def]
    from demobot.schemas import Calibration, CameraPose, Rect

    return Calibration(image_size=(1280, 720), H_img_to_table=cam.frames[0].H_img_to_table, markers=[],
                       work_area=Rect(x0=4, y0=4, x1=56, y1=36), robot_base_cm=(30, 64),
                       camera=CameraPose(focal_px=1000, principal_px=(640, 360), focal_source="default_fov",
                                         position_cm=(30, 20, 200), look_dir=(0, 0, -1), tilt_deg=0,
                                         nadir_cm=(30, 20), rvec=(0, 0, 0), tvec=(0, 0, 200)),
                       method="markers_bundle", reprojection_px=0.1, frames_used=1, reference_t=6.9)  # fmt: skip


def test_objects_put_in_a_container_end_inside_it() -> None:
    spec = TaskSpec(summary="", objects=[], generalization="", goal=[],
                    steps=[Step(action="place_in", object="pen", target="mug", t_start=0, t_end=1)])  # fmt: skip
    mug = SceneObject(
        name="mug", kind="mug", role="container", shape="cylinder", x=40, y=30, w=9, d=9, h=10
    )
    pen = SceneObject(
        name="pen", kind="pen", x=45, y=22, w=14, d=1.2, h=1.2
    )  # parallax put it outside
    out = {o.name: o for o in ground._settle_into_containers(spec, [mug, pen])}
    assert (out["pen"].x, out["pen"].y) == (40, 30)
    near = pen.model_copy(update={"x": 41.0, "y": 31.0})
    out = {o.name: o for o in ground._settle_into_containers(spec, [mug, near])}
    assert (out["pen"].x, out["pen"].y) == (41.0, 31.0)
    _ = np


def _box_track(name: str, x: float, quality: float = 1.0) -> Track:
    frames = [TrackFrame(t=k / 10, bbox_px=(x, 100.0, x + 40, 120.0), centroid_px=(x + 20, 110.0))
              for k in range(10)]  # fmt: skip
    return Track(name=name, phrase=name, quality=quality, frames=frames)


def test_dedupe_moves_a_duplicate_to_another_sam_instance(tmp_path: Path) -> None:
    from demobot.events import EventLog, RunContext

    ctx = RunContext("r", "dev", EventLog(tmp_path / "events.jsonl", "r"), "perceive")
    # both phrases matched the pen at x=100; SAM also returned the other pen (x=300) for the second
    tracks = [_box_track("smooth teal pen", 100), _box_track("ridged teal pen", 100, 0.9)]
    perceive._dedupe(ctx, tracks, {"ridged teal pen": [_box_track("ridged teal pen", 300, 0.8)]})
    assert [t.frames[0].centroid_px for t in tracks] == [(120.0, 110.0), (320.0, 110.0)]
    assert all("not_found" not in t.flags for t in tracks)
    # with no spare instance the weaker one is still left out
    tracks = [_box_track("smooth teal pen", 100), _box_track("ridged teal pen", 100, 0.9)]
    perceive._dedupe(ctx, tracks, {})
    assert "not_found" in tracks[1].flags and "duplicate_of:smooth teal pen" in tracks[1].flags
