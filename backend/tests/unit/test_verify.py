"""Verification logic without the network: failure classes and the perceptual rules."""

from pathlib import Path
from typing import Any

from demobot import verify
from demobot.perceive import Instance
from demobot.schemas import (
    Calibration,
    CameraPose,
    CheckResult,
    GoalClause,
    JudgeVerdict,
    Rect,
    SceneObject,
    Selector,
)  # fmt: skip

OK, BAD = CheckResult(ok=True), CheckResult(ok=False)


def test_failure_classes_in_priority_order() -> None:
    agree = JudgeVerdict(same_goal_achieved=True, confidence=0.9)
    dissent = JudgeVerdict(same_goal_achieved=False, confidence=0.9)
    unsure = JudgeVerdict(same_goal_achieved=False, confidence=0.3)
    assert verify.classify(OK, OK, OK, agree) is None
    assert verify.classify(OK, BAD, BAD, dissent) == "spec_mismatch"
    assert verify.classify(BAD, OK, BAD, dissent) == "program_bug"
    assert verify.classify(OK, OK, BAD, agree) == "perception_gap"
    assert verify.classify(OK, OK, OK, dissent) == "judge_dissent"
    assert verify.classify(OK, OK, OK, unsure) is None  # a low-confidence dissent is not a failure
    assert verify.classify(OK, OK, OK, None) is None  # no judge available: three checks decide


def calib() -> Calibration:
    """A top-down camera 100 cm above (30, 20), focal 1000: 10 px per cm at the table."""
    import cv2
    import numpy as np

    R = np.eye(3)
    t = -R @ np.array([30.0, 20.0, -100.0])
    rvec = cv2.Rodrigues(R)[0].ravel()
    H = [[0.1, 0, -34.0], [0, 0.1, -16.0], [0, 0, 1]]  # pixel -> cm for this camera
    return Calibration(image_size=(1280, 720), H_img_to_table=H, markers=[], work_area=Rect(x0=4, y0=4, x1=56, y1=36),
                       robot_base_cm=(30, 64), method="markers_bundle", reprojection_px=0.1, frames_used=1,
                       camera=CameraPose(focal_px=1000, principal_px=(640, 360), focal_source="default_fov",
                                         position_cm=(30, 20, 100), look_dir=(0, 0, -1), tilt_deg=0, nadir_cm=(30, 20),
                                         rvec=tuple(rvec), tvec=tuple(t)))  # type: ignore[arg-type]  # fmt: skip


def objs() -> list[SceneObject]:
    return [SceneObject(name="mug", kind="mug", role="container", shape="cylinder", x=40, y=20, w=9, d=9, h=10, z=5),
            SceneObject(name="pen", kind="pen", x=40, y=20, z=7, w=14, d=1.2, h=1.2)]  # fmt: skip


GOAL = [
    GoalClause(quant="all", select=Selector(kind="pen"), pred="inside", target=Selector(name="mug"))
]


def fake_sam(found: dict[str, Any]):  # type: ignore[no-untyped-def]
    async def sam(ctx: Any, image: Path, phrase: str) -> list[Instance]:
        return [found[phrase]] if phrase in found else []

    return sam


def inst(cal: Calibration, o: SceneObject, dx: float = 0) -> Instance:
    u, v = verify.project(cal, o)
    return Instance("0", (u - 5, v - 5, u + 5, v + 5), 100, (u + dx, v), [])


async def test_unseen_stand_ins_are_inconclusive_not_failures(monkeypatch) -> None:
    cal = calib()
    final = objs()
    monkeypatch.setattr(verify, "sam_image", fake_sam({"mug": inst(cal, final[0])}))
    res, _ = await verify.perceptual(
        None, Path("x"), final, final, {"mug": "mug", "pen": "pen"}, GOAL, cal, {"mug", "pen"}
    )  # type: ignore[arg-type]
    assert res.ok  # the pen is inside a mug SAM does see: it looks "inside"
    monkeypatch.setattr(verify, "sam_image", fake_sam({}))
    res, _ = await verify.perceptual(
        None, Path("x"), final, final, {"mug": "mug", "pen": "pen"}, GOAL, cal, {"mug", "pen"}
    )  # type: ignore[arg-type]
    assert res.ok and res.inconclusive and "inconclusive" in res.detail


async def test_a_seen_contradiction_fails(monkeypatch) -> None:
    cal = calib()
    final = objs()
    far = inst(cal, final[1], dx=300)  # SAM sees the pen 30 cm away from the mug
    monkeypatch.setattr(verify, "sam_image", fake_sam({"mug": inst(cal, final[0]), "pen": far}))
    res, _ = await verify.perceptual(
        None, Path("x"), final, final, {"mug": "mug", "pen": "pen"}, GOAL, cal, {"mug", "pen"}
    )  # type: ignore[arg-type]
    # beyond the 90 px match radius the pen counts as unseen; it is inside a mug SAM does see,
    # so it is "hidden from view", consistent with the goal
    assert res.ok and "hidden from view" in res.clauses[0].detail
    near = inst(cal, final[1], dx=80)  # 8 cm off: matched, and it contradicts "inside"
    monkeypatch.setattr(verify, "sam_image", fake_sam({"mug": inst(cal, final[0]), "pen": near}))
    res, _ = await verify.perceptual(
        None, Path("x"), final, final, {"mug": "mug", "pen": "pen"}, GOAL, cal, {"mug", "pen"}
    )  # type: ignore[arg-type]
    assert not res.ok


def test_clause_words() -> None:
    assert verify.clause_words(GOAL[0]) == "every pen are inside the mug"
