"""PyBullet scene (docs/06 "Scene"): table, Panda and stand-ins, one DIRECT client per scene.

Ported from the first repo. Table cm -> sim metres: X = x/100, Y = −y/100, Z up (the table
frame is left-handed with z up; see docs/decisions.md). Yaw flips sign for the same reason.
"""

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self

import pybullet as p
import pybullet_data

from demobot.schemas import Layout, Rect, SceneObject, Vec2
from demobot.sim import constants as C

XYZ = tuple[float, float, float]


def to_sim(xy_cm: Iterable[float]) -> tuple[float, float]:
    x, y = list(xy_cm)[:2]
    return x / 100.0, -y / 100.0


def to_table(xy_m: Iterable[float]) -> tuple[float, float]:
    x, y = list(xy_m)[:2]
    return x * 100.0, -y * 100.0


def hex_rgba(color: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    c = color.lstrip("#")
    if len(c) == 6:
        try:
            return int(c[0:2], 16) / 255, int(c[2:4], 16) / 255, int(c[4:6], 16) / 255, alpha
        except ValueError:
            pass
    return C.COLOURS.get(color.strip().lower(), C.DEFAULT_RGBA)


@dataclass
class SimObject:
    spec: SceneObject  # as laid out (sizes, kind, role)
    body: int

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def height_m(self) -> float:
        return self.spec.h / 100.0


@dataclass
class TwinRecorder:
    """Joint angles and object poses at 30 fps, plus grasp and release events."""

    scene: "Scene"
    frames: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)

    def capture(self) -> None:
        cid, robot = self.scene.client, self.scene.robot
        q = [
            s[0]
            for s in p.getJointStates(robot, [*C.ARM_JOINTS, *C.FINGER_JOINTS], physicsClientId=cid)
        ]
        poses = {}
        for name, obj in self.scene.objects.items():
            pos, orn = p.getBasePositionAndOrientation(obj.body, physicsClientId=cid)
            poses[name] = [round(v, 5) for v in (*pos, *orn)]
        self.frames.append(
            {"t": round(self.scene.time_s, 4), "q": [round(v, 5) for v in q], "poses": poses}
        )

    def event(self, type: str, obj: str | None = None, **extra: Any) -> None:
        self.events.append({"t": round(self.scene.time_s, 4), "type": type, "object": obj, **extra})


@dataclass
class Scene:
    """One PyBullet DIRECT client with its table, robot and stand-ins."""

    client: int
    robot: int
    table: int
    robot_base_cm: Vec2
    work_area: Rect
    objects: dict[str, SimObject]
    on_step: list[Callable[[], None]] = field(default_factory=list)
    steps_taken: int = 0
    recorder: TwinRecorder | None = None

    @property
    def time_s(self) -> float:
        return self.steps_taken * C.TIME_STEP

    def step(self, n: int = 1) -> None:
        for _ in range(n):
            p.stepSimulation(physicsClientId=self.client)
            self.steps_taken += 1
            for hook in self.on_step:
                hook()
            if self.recorder and self.steps_taken % C.STEPS_PER_TWIN_FRAME == 0:
                self.recorder.capture()

    def record(self) -> TwinRecorder:
        self.recorder = TwinRecorder(self)
        self.recorder.capture()
        return self.recorder

    def pose_cm(self, name: str) -> XYZ:
        """Body centre in table cm (z up from the table top)."""
        pos, _ = p.getBasePositionAndOrientation(
            self.objects[name].body, physicsClientId=self.client
        )
        x, y = to_table(pos)
        return x, y, pos[2] * 100.0

    def yaw_deg(self, name: str) -> float:
        _, orn = p.getBasePositionAndOrientation(
            self.objects[name].body, physicsClientId=self.client
        )
        return -math.degrees(p.getEulerFromQuaternion(orn)[2])

    def snapshot(self, name: str) -> SceneObject:
        x, y, z = self.pose_cm(name)
        return self.objects[name].spec.model_copy(
            update={
                "x": round(x, 2),
                "y": round(y, 2),
                "z": round(z, 2),
                "yaw": round(self.yaw_deg(name), 1),
            }
        )

    def state(self) -> list[SceneObject]:
        return [self.snapshot(n) for n in self.objects]

    def name_of(self, body: int) -> str | None:
        for obj in self.objects.values():
            if obj.body == body:
                return obj.name
        return None

    def close(self) -> None:
        if p.isConnected(self.client):
            p.disconnect(self.client)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _container_parts(
    o: SceneObject,
) -> tuple[list[int], list[list[float]], list[list[float]], list[list[float]]]:
    """(types, half extents, positions, orientations) of an open box or open cylinder: a floor
    and thin walls, origin at the centre of the bounding box."""
    w, d, h = o.w / 100.0, o.d / 100.0, o.h / 100.0
    t = C.CONTAINER_WALL_M
    floor_z = -h / 2 + t / 2
    if o.shape == "cylinder":
        r = max(w, d) / 2
        n = C.CYLINDER_WALLS
        side = 2 * r * math.tan(math.pi / n) + t
        types = [p.GEOM_CYLINDER] + [p.GEOM_BOX] * n
        half: list[list[float]] = [[r, r, t / 2]]
        pos: list[list[float]] = [[0, 0, floor_z]]
        orn: list[list[float]] = [[0, 0, 0, 1]]
        for k in range(n):
            a = 2 * math.pi * k / n
            half.append([t / 2, side / 2, h / 2])
            pos.append([(r - t / 2) * math.cos(a), (r - t / 2) * math.sin(a), 0])
            orn.append(list(p.getQuaternionFromEuler([0, 0, a])))
        return types, half, pos, orn
    types = [p.GEOM_BOX] * 5
    half = [
        [w / 2, d / 2, t / 2],
        [t / 2, d / 2, h / 2],
        [t / 2, d / 2, h / 2],
        [w / 2, t / 2, h / 2],
        [w / 2, t / 2, h / 2],
    ]
    pos = [
        [0, 0, floor_z],
        [-w / 2 + t / 2, 0, 0],
        [w / 2 - t / 2, 0, 0],
        [0, -d / 2 + t / 2, 0],
        [0, d / 2 - t / 2, 0],
    ]
    return types, half, pos, [[0, 0, 0, 1]] * 5


def _shapes(o: SceneObject, cid: int) -> tuple[int, int]:
    rgba = hex_rgba(o.color)
    if o.is_open:
        types, half, pos, orn = _container_parts(o)
        radii = [h[0] for h in half]
        lengths = [2 * h[2] for h in half]
        col = p.createCollisionShapeArray(
            shapeTypes=types,
            halfExtents=half,
            radii=radii,
            lengths=lengths,
            collisionFramePositions=pos,
            collisionFrameOrientations=orn,
            physicsClientId=cid,
        )
        vis = p.createVisualShapeArray(
            shapeTypes=types,
            halfExtents=half,
            radii=radii,
            lengths=lengths,
            visualFramePositions=pos,
            visualFrameOrientations=orn,
            rgbaColors=[rgba] * len(types),
            physicsClientId=cid,
        )
        return col, vis
    w, d, h = o.w / 100.0, o.d / 100.0, o.h / 100.0
    if o.shape == "sphere":
        r = max(w, d, h) / 2
        col = p.createCollisionShape(p.GEOM_SPHERE, radius=r, physicsClientId=cid)
        vis = p.createVisualShape(p.GEOM_SPHERE, radius=r, rgbaColor=rgba, physicsClientId=cid)
        return col, vis
    if o.shape == "cylinder":
        r = max(w, d) / 2
        col = p.createCollisionShape(p.GEOM_CYLINDER, radius=r, height=h, physicsClientId=cid)
        vis = p.createVisualShape(
            p.GEOM_CYLINDER, radius=r, length=h, rgbaColor=rgba, physicsClientId=cid
        )
        return col, vis
    box = [w / 2, d / 2, h / 2]
    col = p.createCollisionShape(p.GEOM_BOX, halfExtents=box, physicsClientId=cid)
    vis = p.createVisualShape(p.GEOM_BOX, halfExtents=box, rgbaColor=rgba, physicsClientId=cid)
    return col, vis


def mass_kg(o: SceneObject) -> float:
    vol = (o.w / 100) * (o.d / 100) * (o.h / 100)
    if o.shape == "cylinder":
        vol *= math.pi / 4
    elif o.shape == "sphere":
        vol *= math.pi / 6
    return min(C.OBJECT_MASS_MAX_KG, max(C.OBJECT_MASS_MIN_KG, vol * C.OBJECT_DENSITY_KG_M3))


def _add_object(o: SceneObject, cid: int) -> int:
    col, vis = _shapes(o, cid)
    body = _make_body(o, col, vis, cid)
    if o.texture and Path(o.texture).is_file():  # the real object's top-down crop
        tex = p.loadTexture(o.texture, physicsClientId=cid)
        p.changeVisualShape(
            body, -1, textureUniqueId=tex, rgbaColor=[1, 1, 1, 1], physicsClientId=cid
        )
    return body


def _make_body(o: SceneObject, col: int, vis: int, cid: int) -> int:
    x, y = to_sim((o.x, o.y))
    body = p.createMultiBody(
        baseMass=0.0 if o.is_open else mass_kg(o),
        baseCollisionShapeIndex=col,
        baseVisualShapeIndex=vis,
        basePosition=[x, y, o.h / 200.0 + 0.0005],
        baseOrientation=p.getQuaternionFromEuler([0, 0, -math.radians(o.yaw)]),
        physicsClientId=cid,
    )
    p.changeDynamics(body, -1, lateralFriction=C.LATERAL_FRICTION, restitution=C.RESTITUTION,
                     physicsClientId=cid)  # fmt: skip
    if o.shape == "sphere":  # a ball on a desk settles instead of rolling away
        p.changeDynamics(body, -1, rollingFriction=C.BALL_ROLLING_FRICTION,
                         spinningFriction=C.BALL_ROLLING_FRICTION, physicsClientId=cid)  # fmt: skip
    return body


def _add_table(work: Rect, cid: int, texture: str | None) -> int:
    m = C.TABLE_MARGIN_M
    x0, y0 = to_sim((work.x0, work.y1))  # sim min corner (Y flips)
    x1, y1 = to_sim((work.x1, work.y0))
    half = [(x1 - x0) / 2 + m, (y1 - y0) / 2 + m + 0.15, C.TABLE_THICKNESS_M / 2]
    centre = [(x0 + x1) / 2, (y0 + y1) / 2 - 0.15, -C.TABLE_THICKNESS_M / 2]
    col = p.createCollisionShape(p.GEOM_BOX, halfExtents=half, physicsClientId=cid)
    vis = p.createVisualShape(
        p.GEOM_BOX, halfExtents=half, rgbaColor=C.TABLE_RGBA, physicsClientId=cid
    )
    table = p.createMultiBody(baseMass=0, baseCollisionShapeIndex=col, baseVisualShapeIndex=vis,
                              basePosition=centre, physicsClientId=cid)  # fmt: skip
    p.changeDynamics(table, -1, lateralFriction=C.LATERAL_FRICTION, restitution=C.RESTITUTION,
                     physicsClientId=cid)  # fmt: skip
    if texture:
        tex = p.loadTexture(texture, physicsClientId=cid)
        p.changeVisualShape(
            table, -1, textureUniqueId=tex, rgbaColor=[1, 1, 1, 1], physicsClientId=cid
        )
    return table


def _add_robot(base_cm: Vec2, cid: int) -> int:
    x, y = to_sim(base_cm)
    robot = p.loadURDF(C.PANDA_URDF, [x, y, 0], p.getQuaternionFromEuler([0, 0, C.PANDA_YAW]),
                       useFixedBase=True, physicsClientId=cid)  # fmt: skip
    for j, q in zip(C.ARM_JOINTS, C.REST_POSE, strict=True):
        p.resetJointState(robot, j, q, physicsClientId=cid)
    for j in C.FINGER_JOINTS:
        p.resetJointState(robot, j, C.FINGER_OPEN, physicsClientId=cid)
    p.setJointMotorControlArray(robot, C.ARM_JOINTS, p.POSITION_CONTROL,
                                targetPositions=C.REST_POSE, forces=[C.ARM_FORCE] * 7,
                                physicsClientId=cid)  # fmt: skip
    p.setJointMotorControlArray(robot, C.FINGER_JOINTS, p.POSITION_CONTROL,
                                targetPositions=[C.FINGER_OPEN] * 2, forces=[C.FINGER_FORCE] * 2,
                                physicsClientId=cid)  # fmt: skip
    return robot


def build_scene(
    layout: Layout, settle_steps: int = C.SCENE_SETTLE_STEPS, table_texture: str | None = None
) -> Scene:
    """Build a scene from a layout; every object starts resting on the table."""
    cid = p.connect(p.DIRECT)
    try:
        p.setAdditionalSearchPath(pybullet_data.getDataPath(), physicsClientId=cid)
        p.setGravity(0, 0, C.GRAVITY, physicsClientId=cid)
        p.setTimeStep(C.TIME_STEP, physicsClientId=cid)
        table = _add_table(layout.work_area, cid, table_texture)
        robot = _add_robot(layout.robot_base_cm, cid)
        objs: dict[str, SimObject] = {}
        # containers first, so anything laid inside one rests on its floor
        for o in sorted(layout.objects, key=lambda o: not o.is_open):
            if o.name in objs:
                raise ValueError(f"duplicate object name {o.name!r}")
            objs[o.name] = SimObject(o, _add_object(o, cid))
        scene = Scene(cid, robot, table, layout.robot_base_cm, layout.work_area,
                      {o.name: objs[o.name] for o in layout.objects})  # fmt: skip
        scene.step(settle_steps)
        return scene
    except BaseException:
        p.disconnect(cid)
        raise
