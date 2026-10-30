"""Layouts, the process sandbox, twin export and renders."""

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from demobot import calibrate
from demobot.program.sandbox import simulate
from demobot.sim.layouts import apply_user_edit, random_layout, reach_map, validate
from demobot.sim.twin_export import TwinTrajectory
from synth.table import draw_texture, render_table

from .programs import FAMILIES


def default_calibration() -> str:
    """A calibration of the nominal 60 × 40 cm marker rectangle seen by an oblique phone."""
    from demobot.camera import look_at

    rng = np.random.default_rng(0)
    truth = draw_texture({0: (0, 0, 0), 1: (60, 0, 0), 2: (60, 40, 0), 3: (0, 40, 0)}, rng)
    cam = look_at((30, 75, 62), (30, 20), 1000.0, 1280, 720)
    img = render_table(truth, cam)
    cal = calibrate.calibrate_corners(calibrate.detect_markers(img), 1280, 720, 1)
    return cal.model_dump_json()


def test_layout_validator_catches_problems() -> None:
    base = FAMILIES["place_in"][0]
    good = random_layout(base, 4)
    assert validate(good) == []
    names = [o.name for o in good.objects]
    a, b = good.objects[1], good.objects[2]
    overlap = apply_user_edit(good, {b.name: (a.x + 0.5, a.y)})
    assert any("overlap" in p for p in validate(overlap))
    outside = apply_user_edit(good, {names[1]: (80.0, 20.0)})
    assert any("outside" in p for p in validate(outside))
    far = good.model_copy(update={"robot_base_cm": (30.0, 140.0)})
    assert any("reach" in p for p in validate(far))
    with pytest.raises(ValueError):
        apply_user_edit(good, {"ghost": (1.0, 1.0)})


def test_random_layouts_are_seeded_and_valid() -> None:
    base = FAMILIES["sort"][0]
    a, b = random_layout(base, 11), random_layout(base, 11)
    assert a == b and random_layout(base, 12) != a and not validate(a)


def test_reach_map_marks_far_cells() -> None:
    base = FAMILIES["place_in"][0]
    m = reach_map(base.work_area, base.robot_base_cm)
    cells = m["cells"]
    assert isinstance(cells, list) and all(all(row) for row in cells)  # default area: all reachable
    m2 = reach_map(base.work_area, (30.0, 100.0))
    assert not all(all(row) for row in m2["cells"])  # type: ignore[union-attr]


async def test_sandboxed_run_exports_a_valid_twin_and_renders() -> None:
    base, goal, programs = FAMILIES["place_in"]
    layout = random_layout(base, 1)
    res = await simulate(programs[0], layout, goal, render=True,
                         calibration_json=default_calibration())  # fmt: skip
    assert res.goal_ok, res.error
    twin = TwinTrajectory.model_validate(json.loads(Path(res.twin_trajectory or "").read_text()))
    assert twin.fps == 30 and len(twin.frames) > 100 and len(twin.frames[0].q) == 9
    assert {e.type for e in twin.events} == {"grasp", "release"}
    assert set(twin.frames[-1].poses) == {o.name for o in layout.objects}
    top = cv2.imread(res.renders["top"])
    cam = cv2.imread(res.renders["camera"])
    assert top.shape[:2] == (520, 720) and cam.shape[:2] == (720, 1280)
    assert top.std() > 10 and cam.std() > 10  # not blank
    again = await simulate(programs[0], layout, goal, render=True,
                           calibration_json=default_calibration())  # fmt: skip
    assert again == res  # cached


async def test_sandbox_reports_errors_and_stops_runaway_programs() -> None:
    base, goal, _ = FAMILIES["place_in"]
    layout = random_layout(base, 2)
    bad = await simulate(
        "def run(scene, robot):\n    robot.pick(scene.get('ghost'))\n", layout, goal
    )
    assert not bad.ok and bad.error_type == "NoSuchObject" and "ghost" in (bad.error or "")
    loop = await simulate("def run(scene, robot):\n    while True:\n        pass\n", layout, goal)
    assert loop.error_type == "LoopLimit"
    hog = "def run(scene, robot):\n    x = sum(i * i for i in range(10 ** 10))\n"
    stopped = await simulate(hog, layout, goal, cpu_limit_s=2)
    assert stopped.error_type == "Timeout" and not stopped.ok
    guard = await simulate("import os\ndef run(scene, robot):\n    pass\n", layout, goal)
    assert guard.error_type == "GuardError"
