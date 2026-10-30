"""The digital-twin trajectory for the browser (docs/06 "Digital-twin export").

Positions are metres in the PyBullet world (Z up); the frontend converts to three.js (Y up).
"""

import json
import math
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from demobot.schemas import Layout
from demobot.sim import constants as C
from demobot.sim.scene import Scene, TwinRecorder, to_sim

URDF_URL = "/assets/franka_panda/panda.urdf"


class TwinObject(BaseModel):
    name: str
    kind: str
    role: str
    shape: str
    size: tuple[float, float, float]  # cm: w, d, h
    container: bool
    texture: str | None = None
    color: str


class TwinFrame(BaseModel):
    t: float
    q: list[float]  # 7 arm joints + 2 fingers
    poses: dict[str, list[float]]  # name -> [x, y, z, qx, qy, qz, qw]


class TwinEvent(BaseModel):
    t: float
    type: str
    object: str | None = None


class TwinTrajectory(BaseModel):
    fps: int
    robot: dict[str, Any]
    table: dict[str, Any]
    objects: list[TwinObject]
    frames: list[TwinFrame]
    events: list[TwinEvent]
    duration_s: float


def build_twin(scene: Scene, recorder: TwinRecorder, layout: Layout) -> TwinTrajectory:
    bx, by = to_sim(layout.robot_base_cm)
    wa = layout.work_area
    return TwinTrajectory(
        fps=C.TWIN_FPS,
        robot={"urdf": URDF_URL, "base": [bx, by, 0.0, C.PANDA_YAW]},
        table={
            "work_area_cm": [wa.x0, wa.y0, wa.x1, wa.y1],
            "top_z": 0.0,
            "margin_m": C.TABLE_MARGIN_M,
        },
        objects=[
            TwinObject(
                name=o.name,
                kind=o.kind,
                role=o.role,
                shape=o.shape,
                size=(o.w, o.d, o.h),
                container=o.is_container,
                texture=o.texture,
                color=o.color,
            )
            for o in layout.objects
        ],
        frames=[TwinFrame(**f) for f in recorder.frames],
        events=[
            TwinEvent(t=e["t"], type=e["type"], object=e.get("object")) for e in recorder.events
        ],
        duration_s=round(scene.time_s, 3),
    )


def write_twin(scene: Scene, recorder: TwinRecorder, layout: Layout, path: Path) -> Path:
    twin = build_twin(scene, recorder, layout)
    path.write_text(json.dumps(twin.model_dump(mode="json"), separators=(",", ":")))
    return path


def yaw_of(quat: list[float]) -> float:
    qx, qy, qz, qw = quat
    return math.degrees(math.atan2(2 * (qw * qz + qx * qy), 1 - 2 * (qy * qy + qz * qz)))
