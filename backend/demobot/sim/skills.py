"""Skill library (docs/06 "Skills"): pick and place with the end effector pointing down.

Ported from the first repo, keeping its proven IK: PyBullet IK, then damped-least-squares
refinement seeded from a bank of sampled top-down poses, and a fixed-constraint grasp.
"""

import functools
import math
from collections.abc import Iterable

import numpy as np
import pybullet as p
import pybullet_data

from demobot.schemas import SceneObject
from demobot.sim import constants as C
from demobot.sim.scene import Scene, to_sim

XY = tuple[float, float]

Vec3 = tuple[float, float, float]


_REST = np.asarray(C.REST_POSE)
# IK stages: a canonical top-down posture first, then the full joint limits
_LIMITS = {
    "working": (np.asarray(C.IK_LL), np.asarray(C.IK_UL)),
    "full": (np.asarray(C.LL[:7]), np.asarray(C.UL[:7])),
}


@functools.cache
def _seed_bank(limits: str) -> tuple[np.ndarray, np.ndarray]:
    """Top-down arm poses sampled once per process: joint angles and EE position from the base."""
    lo, hi = _LIMITS[limits]
    cid = p.connect(p.DIRECT)
    try:
        p.setAdditionalSearchPath(pybullet_data.getDataPath(), physicsClientId=cid)
        robot = p.loadURDF(
            C.PANDA_URDF,
            [0, 0, 0],
            p.getQuaternionFromEuler([0, 0, C.PANDA_YAW]),
            useFixedBase=True,
            physicsClientId=cid,
        )
        rng = np.random.default_rng(C.IK_BANK_SEED)
        qs, pts = [], []
        for _ in range(C.IK_BANK_SAMPLES):
            q = rng.uniform(lo, hi)
            for j, v in zip(C.ARM_JOINTS, q, strict=True):
                p.resetJointState(robot, j, float(v), physicsClientId=cid)
            state = p.getLinkState(
                robot, C.EE_LINK, computeForwardKinematics=True, physicsClientId=cid
            )
            pointing_down = p.getMatrixFromQuaternion(state[5])[8] <= -0.9
            if pointing_down and -0.05 <= state[4][2] <= 0.35:
                qs.append(q)
                pts.append(state[4])
        return np.asarray(qs), np.asarray(pts)
    finally:
        p.disconnect(cid)


class SkillError(Exception):
    """A skill could not run; `reason` is ik_failed or out_of_reach."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _above(xy_cm: XY, z_m: float) -> Vec3:
    x, y = to_sim(xy_cm)
    return x, y, z_m


def base_distance_m(base_cm: XY, xy_cm: XY) -> float:
    return math.dist(base_cm, xy_cm) / 100.0


class Skills:
    """Runs skills on one scene and records which bodies touched a robot link."""

    def __init__(self, scene: Scene) -> None:
        self.scene = scene
        self.cid = scene.client
        self.robot = scene.robot
        self.orn = p.getQuaternionFromEuler(C.EE_DOWN_EULER)
        self._target_rot = np.asarray(p.getMatrixFromQuaternion(self.orn)).reshape(3, 3)
        self._base_pos, base_orn = p.getBasePositionAndOrientation(
            self.robot, physicsClientId=self.cid
        )
        self._base_rot = np.asarray(p.getMatrixFromQuaternion(base_orn)).reshape(3, 3)
        self.contacts: set[int] = set()
        self.held: str | None = None
        self._constraint: int | None = None
        scene.on_step.append(self._record_contacts)

    # ---------- low level ----------
    def _record_contacts(self) -> None:
        for c in p.getContactPoints(bodyA=self.robot, physicsClientId=self.cid):
            self.contacts.add(c[2])

    def _arm_q(self) -> list[float]:
        states = p.getJointStates(self.robot, C.ARM_JOINTS, physicsClientId=self.cid)
        return [s[0] for s in states]

    def ee_pos(self) -> Vec3:
        state = p.getLinkState(
            self.robot, C.EE_LINK, computeForwardKinematics=True, physicsClientId=self.cid
        )
        return tuple(state[4])

    def fk_error(self, q: list[float], pos: Vec3) -> float:
        """Distance in metres between `pos` and the end effector at joint angles `q`."""
        saved = p.getJointStates(self.robot, C.ARM_JOINTS, physicsClientId=self.cid)
        for j, v in zip(C.ARM_JOINTS, q, strict=True):
            p.resetJointState(self.robot, j, v, physicsClientId=self.cid)
        reached = self.ee_pos()
        for j, s in zip(C.ARM_JOINTS, saved, strict=True):
            p.resetJointState(self.robot, j, s[0], targetVelocity=s[1], physicsClientId=self.cid)
        return math.dist(reached, pos)

    def _pose_error(self, pos: Vec3) -> tuple[np.ndarray, np.ndarray]:
        """Position error (m) and orientation error (axis-angle, rad) of the current EE pose."""
        state = p.getLinkState(
            self.robot, C.EE_LINK, computeForwardKinematics=True, physicsClientId=self.cid
        )
        ep = np.asarray(pos) - np.asarray(state[4])
        r = self._target_rot @ np.asarray(p.getMatrixFromQuaternion(state[5])).reshape(3, 3).T
        angle = math.acos(max(-1.0, min(1.0, (np.trace(r) - 1) / 2)))
        if angle < 1e-9:
            return ep, np.zeros(3)
        axis = np.array([r[2, 1] - r[1, 2], r[0, 2] - r[2, 0], r[1, 0] - r[0, 1]])
        return ep, angle / (2 * math.sin(angle)) * axis

    def _set_arm(self, q: Iterable[float]) -> None:
        for j, v in zip(C.ARM_JOINTS, q, strict=True):
            p.resetJointState(self.robot, j, float(v), physicsClientId=self.cid)

    def _dls(self, pos: Vec3, seed: Iterable[float], orn_weight: float, limits: str) -> np.ndarray:
        """Damped least squares within `limits`, with a null-space pull to the rest pose."""
        lo, hi = _LIMITS[limits]
        q = np.clip(np.asarray(list(seed), dtype=float), lo, hi)
        for _ in range(C.IK_ITERATIONS):
            self._set_arm(q)
            ep, eo = self._pose_error(pos)
            if np.linalg.norm(ep) < C.IK_POS_DONE_M and np.linalg.norm(eo) < C.IK_ORN_DONE_RAD:
                break
            lin, ang = p.calculateJacobian(
                self.robot,
                C.EE_LINK,
                [0, 0, 0],
                [*q.tolist(), C.FINGER_OPEN, C.FINGER_OPEN],
                [0.0] * 9,
                [0.0] * 9,
                physicsClientId=self.cid,
            )
            # PyBullet gives the Jacobian of a fixed-base robot in the base frame
            jac = np.vstack([self._base_rot @ np.asarray(m)[:, :7] for m in (lin, ang)])
            err = np.concatenate([ep, orn_weight * eo])
            dq = jac.T @ np.linalg.solve(jac @ jac.T + C.IK_DAMPING**2 * np.eye(6), err)
            dq += (np.eye(7) - np.linalg.pinv(jac) @ jac) @ (C.IK_REST_GAIN * (_REST - q))
            biggest = np.abs(dq).max()
            if biggest > C.IK_MAX_STEP_RAD:
                dq *= C.IK_MAX_STEP_RAD / biggest
            q = np.clip(q + dq, lo, hi)
        return q

    def _seeds(self, pos: Vec3, limits: str) -> list[list[float]]:
        """The current pose, PyBullet's IK (spec 7.7) and the nearest bank poses, closest first."""
        q_now = self._arm_q()
        spec_ik = p.calculateInverseKinematics(
            self.robot,
            C.EE_LINK,
            pos,
            self.orn,
            lowerLimits=C.LL,
            upperLimits=C.UL,
            jointRanges=C.JR,
            restPoses=C.REST,
            maxNumIterations=100,
            residualThreshold=1e-4,
            physicsClientId=self.cid,
        )[:7]
        bank_q, bank_pos = _seed_bank(limits)
        rel = np.asarray(pos) - np.asarray(self._base_pos)
        nearest = bank_q[np.argsort(np.linalg.norm(bank_pos - rel, axis=1))[: C.IK_BANK_NEAREST]]
        nearest = nearest[np.argsort(np.linalg.norm(nearest - np.asarray(q_now), axis=1))]
        return [q_now, list(spec_ik), *nearest.tolist()]

    def _exact(self, pos: Vec3, limits: str) -> tuple[np.ndarray | None, np.ndarray]:
        """First exact top-down solution within `limits`, else None and the closest attempt."""
        best, best_score = None, math.inf
        for seed in self._seeds(pos, limits):
            q = self._dls(pos, seed, C.IK_ORN_WEIGHT, limits)
            self._set_arm(q)
            ep, eo = (float(np.linalg.norm(v)) for v in self._pose_error(pos))
            if ep < C.IK_POS_OK_M and eo < C.IK_ORN_OK_RAD:
                return q, q
            if ep + 0.05 * eo < best_score:
                best, best_score = q, ep + 0.05 * eo
        assert best is not None
        return None, best

    def ik(self, pos: Vec3) -> list[float]:
        """Arm angles that put the EE at `pos` pointing down; ik_failed beyond IK_TOLERANCE_M.

        Tries a canonical posture first, then the full joint limits, then a position-first solve
        (the hand may tilt) where the exact pose is out of reach, e.g. high up next to the base.
        """
        saved = p.getJointStates(self.robot, C.ARM_JOINTS, physicsClientId=self.cid)
        try:
            q, closest = self._exact(pos, "working")
            if q is None:
                q, wide = self._exact(pos, "full")
                if q is None:
                    q = self._dls(pos, closest, C.IK_ORN_WEIGHT_TILT, "working")
                    self._set_arm(q)
                    if np.linalg.norm(self._pose_error(pos)[0]) > C.IK_POS_OK_M:
                        q = self._dls(pos, wide, C.IK_ORN_WEIGHT_TILT, "full")
        finally:
            for j, s in zip(C.ARM_JOINTS, saved, strict=True):
                p.resetJointState(
                    self.robot, j, s[0], targetVelocity=s[1], physicsClientId=self.cid
                )
        if self.fk_error(q.tolist(), pos) > C.IK_TOLERANCE_M:
            raise SkillError("ik_failed")
        return q.tolist()

    def _drive_arm(self, target: list[float]) -> None:
        p.setJointMotorControlArray(
            self.robot,
            C.ARM_JOINTS,
            p.POSITION_CONTROL,
            targetPositions=target,
            forces=[C.ARM_FORCE] * 7,
            physicsClientId=self.cid,
        )

    def move_ee(self, pos: Vec3, steps: int) -> None:
        """Joint-space interpolation from the current arm pose to the IK solution for `pos`."""
        q = self.ik(pos)
        q_now = self._arm_q()
        for s in range(1, steps + 1):
            f = s / steps
            self._drive_arm([a + (b - a) * f for a, b in zip(q_now, q, strict=True)])
            self.scene.step()
        for _ in range(C.MOVE_HOLD_MAX_STEPS):
            if max(abs(a - b) for a, b in zip(self._arm_q(), q, strict=True)) < C.MOVE_HOLD_TOL_RAD:
                break
            self.scene.step()

    def set_fingers(self, opening_m: float) -> None:
        q = min(max(opening_m, 0.0), C.FINGER_OPEN)
        p.setJointMotorControlArray(
            self.robot,
            C.FINGER_JOINTS,
            p.POSITION_CONTROL,
            targetPositions=[q, q],
            forces=[C.FINGER_FORCE] * 2,
            physicsClientId=self.cid,
        )

    def _robot_collides_with(self, body: int, enabled: bool) -> None:
        for link in range(-1, p.getNumJoints(self.robot, physicsClientId=self.cid)):
            p.setCollisionFilterPair(
                self.robot, body, link, -1, int(enabled), physicsClientId=self.cid
            )

    def attach(self, name: str) -> None:
        """JOINT_FIXED constraint; its child frame is the object's pose relative to the EE."""
        obj = self.scene.objects[name]
        link = p.getLinkState(
            self.robot, C.EE_LINK, computeForwardKinematics=True, physicsClientId=self.cid
        )
        ee_pos, ee_orn = link[4], link[5]
        pos, orn = p.getBasePositionAndOrientation(obj.body, physicsClientId=self.cid)
        inv_pos, inv_orn = p.invertTransform(ee_pos, ee_orn)
        rel_pos, rel_orn = p.multiplyTransforms(inv_pos, inv_orn, pos, orn)
        self._robot_collides_with(obj.body, False)
        self._constraint = p.createConstraint(
            self.robot,
            C.EE_LINK,
            obj.body,
            -1,
            p.JOINT_FIXED,
            [0, 0, 0],
            rel_pos,
            [0, 0, 0],
            parentFrameOrientation=rel_orn,
            physicsClientId=self.cid,
        )
        p.changeConstraint(self._constraint, maxForce=1000, physicsClientId=self.cid)
        self.held = name
        if self.scene.recorder:
            self.scene.recorder.event("grasp", name)
        self.set_fingers(min(obj.spec.w, obj.spec.d) / 200.0)

    def detach(self) -> None:
        """Remove the grasp constraint and let go gently (no carried-over velocity)."""
        if self._constraint is not None:
            p.removeConstraint(self._constraint, physicsClientId=self.cid)
        self._constraint = None
        if self.held is not None:
            body = self.scene.objects[self.held].body
            p.resetBaseVelocity(body, [0, 0, 0], [0, 0, 0], physicsClientId=self.cid)
            if self.scene.recorder:
                self.scene.recorder.event("release", self.held)

    def release(self) -> None:
        """Re-enable collisions between the robot and the object it was holding."""
        if self.held is not None:
            self._robot_collides_with(self.scene.objects[self.held].body, True)
        self.held = None

    def check_reach(self, xy_cm: XY) -> None:
        d = base_distance_m(self.scene.robot_base_cm, xy_cm)
        if d > C.REACH_MAX_M or d < C.REACH_MIN_M:
            raise SkillError("out_of_reach")

    # ---------- skills ----------
    def pick(self, name: str) -> None:
        obj = self.scene.objects[name]
        x, y, z = self.scene.pose_cm(name)
        self.check_reach((x, y))
        top = (z + obj.spec.h / 2) / 100.0
        self.set_fingers(C.FINGER_OPEN)
        self.move_ee(_above((x, y), top + 0.10), 240)
        self.move_ee(_above((x, y), top + C.GRASP_OFFSET), 180)
        self.attach(name)
        self.move_ee(_above((x, y), max(C.Z_SAFE, top + 0.08)), 180)

    def place(
        self,
        target_xy_cm: XY,
        surface_z_m: float,
        container: str | None = None,
        slot: dict[str, float | str | None] | None = None,
    ) -> None:
        """Carry the held object over the target, lower it onto the surface and let go.
        Into a container it does not fit lying flat, it is let go just above the rim and slides
        in the way a person would put it: diagonally across a square box (a spoon, a cutter),
        or standing upright (pens into a mug)."""
        assert self.held is not None
        name = self.held
        obj = self.scene.objects[name]
        self.check_reach(target_xy_cm)
        mode = str(slot["mode"]) if slot else "flat"
        self.move_ee(_above(target_xy_cm, C.Z_SAFE), 300)
        if mode != "flat":
            assert container is not None
            rim = self.scene.objects[container].height_m
            self.move_ee(_above(target_xy_cm, rim + obj.height_m + C.GRASP_OFFSET + 0.015), 180)
        else:
            self.move_ee(
                _above(target_xy_cm, surface_z_m + obj.height_m + C.GRASP_OFFSET + 0.005), 180
            )
        self.detach()
        self.set_fingers(C.FINGER_OPEN)
        if mode != "flat":
            assert container is not None and slot is not None
            self._slide_in(name, container, slot)
        self.scene.step(C.SETTLE_STEPS)
        self.move_ee(_above(target_xy_cm, C.Z_SAFE), 120)
        self.release()

    def _slide_in(self, name: str, container: str, slot: dict[str, float | str | None],
                  steps: int = 24) -> None:  # fmt: skip
        """Kinematically lay the object diagonally in the container (resting on whatever is under
        that diagonal) or stand it upright on the floor, as `slot` says."""
        body = self.scene.objects[name].body
        spec = self.scene.objects[name].spec
        cbox = self.scene.objects[container]
        cpos, _ = p.getBasePositionAndOrientation(cbox.body, physicsClientId=self.cid)
        c_bottom = cpos[2] - cbox.height_m / 2
        pos0, orn0 = p.getBasePositionAndOrientation(body, physicsClientId=self.cid)
        x, y = to_sim((float(slot["x"] or 0), float(slot["y"] or 0)))
        base = c_bottom + float(slot["base_cm"] or 0) / 100
        if slot["mode"] == "upright":
            long_axis = max(("w", spec.w), ("d", spec.d), ("h", spec.h), key=lambda a: a[1])[0]
            tilt = {"w": [0, math.pi / 2, 0], "d": [math.pi / 2, 0, 0], "h": [0, 0, 0]}[long_axis]
            orn1 = p.getQuaternionFromEuler(tilt)
            pos1 = (x, y, base + max(spec.w, spec.d, spec.h) / 200 + 0.002)
        else:
            orn1 = p.getQuaternionFromEuler([0, 0, -math.radians(float(slot["yaw"] or 0))])
            pos1 = (x, y, base + spec.h / 200 + 0.002)
        # turn above everything inside first, then lower straight down
        clear = max(pos0[2], c_bottom + cbox.height_m + max(spec.w, spec.d, spec.h) / 200 + 0.01)
        for other in self.scene.objects.values():
            if other.name not in (name, container):
                opos, _ = p.getBasePositionAndOrientation(other.body, physicsClientId=self.cid)
                if math.dist(opos[:2], cpos[:2]) < max(cbox.spec.w, cbox.spec.d) / 200:
                    clear = max(clear, opos[2] + other.height_m / 2 + spec.h / 200 + 0.01)
        mid = (pos1[0], pos1[1], clear)
        half = steps // 2
        for s in range(1, steps + 1):
            if s <= half:
                f = s / half
                pos = [a + (b - a) * f for a, b in zip(pos0, mid, strict=True)]
                orn = p.getQuaternionSlerp(orn0, orn1, f)
            else:
                f = (s - half) / (steps - half)
                pos = [a + (b - a) * f for a, b in zip(mid, pos1, strict=True)]
                orn = orn1
            p.resetBasePositionAndOrientation(body, pos, orn, physicsClientId=self.cid)
            p.resetBaseVelocity(body, [0, 0, 0], [0, 0, 0], physicsClientId=self.cid)
            self.scene.step()

    def home(self) -> None:
        self.set_fingers(C.FINGER_OPEN)
        q_now = self._arm_q()
        for s in range(1, 241):
            f = s / 240
            self._drive_arm([a + (b - a) * f for a, b in zip(q_now, C.REST_POSE, strict=True)])
            self.scene.step()


def _inner(container: SceneObject) -> float:
    return min(container.w, container.d) - 2 * C.CONTAINER_WALL_M * 100 - 1.0


def fits_flat(obj: SceneObject, container: SceneObject) -> bool:
    """True if the object's footprint fits inside the container's opening with 1 cm to spare."""
    inner = _inner(container)
    hx, hy = obj.extents()
    if obj.shape == "sphere":
        return bool(2 * hx <= inner)
    if container.shape == "cylinder":
        return bool(math.hypot(hx, hy) * 2 <= inner)
    return bool(2 * hx <= inner and 2 * hy <= inner)


def insert_mode(obj: SceneObject, container: SceneObject) -> str:
    """How a person would put obj in container: "flat", "diagonal" (across a square box) or
    "upright"."""
    if fits_flat(obj, container):
        return "flat"
    if container.shape == "box" and obj.shape == "box":
        long, short = max(obj.w, obj.d), min(obj.w, obj.d)
        if long + short <= _inner(container) * math.sqrt(2):
            return "diagonal"
    return "upright"


def container_slot(
    obj: SceneObject, container: SceneObject, contents: list[SceneObject]
) -> dict[str, float | str | None]:
    """Where and how obj goes into the container, given what is already inside:
    mode (flat | diagonal | upright), centre x, y (table cm), yaw (degrees, or None to keep),
    and base_cm (the height it rests on). Flat items take the freest spot; diagonal items the
    diagonal farther from what is inside, resting on what is under that diagonal."""
    mode = insert_mode(obj, container)
    floor = C.CONTAINER_WALL_M * 100
    c = container
    ih = _inner(c) / 2
    hx, hy = obj.extents()
    small = mode == "flat" and c.shape == "box" and max(hx, hy) <= 0.6 * ih
    if mode == "upright" or (not contents and not small):
        yaw = None if mode != "diagonal" else c.yaw + 45 + (0 if obj.w >= obj.d else 90)
        return {"mode": mode, "x": c.x, "y": c.y, "yaw": yaw, "base_cm": floor}

    def radius(o: SceneObject) -> float:
        hx, hy = o.extents()
        return min(hx, hy) if o.shape == "box" and max(hx, hy) > 2 * min(hx, hy) else max(hx, hy)

    if mode == "flat":
        # small items go to the corners on one diagonal (rotated with the box), keeping the
        # other diagonal clear for long items
        a = math.radians(c.yaw)
        ca, sa = math.cos(a), math.sin(a)
        corners = [(-1, -1), (1, 1), (1, -1), (-1, 1)]
        cands = [] if small else [(c.x, c.y)]
        if c.shape != "box":  # round: points on the inner circle, on the same diagonals
            r_obj = max(hx, hy)
            for sx, sy in corners:
                if ih > r_obj:
                    k = (ih - r_obj) / math.sqrt(2)
                    cands.append((c.x + sx * k, c.y + sy * k))
        elif ih > hx and ih > hy:
            for sx, sy in corners:
                du, dv = sx * (ih - hx), sy * (ih - hy)
                cands.append((c.x + du * ca - dv * sa, c.y + du * sa + dv * ca))

        def room(xy: tuple[float, float]) -> float:
            if not contents:
                return 0.0
            return min(math.dist(xy, (o.x, o.y)) - radius(o) - max(hx, hy) for o in contents)

        x, y = max(cands, key=room) if cands else (c.x, c.y)  # ties keep the first corner
        return {"mode": mode, "x": x, "y": y, "yaw": None, "base_cm": floor}
    best: tuple[float, float, float] | None = None
    for turn in (45.0, -45.0):
        a = math.radians(c.yaw + turn)
        ux, uy = math.cos(a), math.sin(a)
        dists = [abs(-(o.x - c.x) * uy + (o.y - c.y) * ux) - radius(o) for o in contents]
        score = min(dists)
        under = [o for o, d in zip(contents, dists, strict=True) if d < min(obj.w, obj.d) / 2]
        base = max([o.z + o.h / 2 for o in under] or [floor])
        if best is None or score > best[0]:
            best = (score, turn, base)
    assert best is not None
    _, turn, base = best
    yaw = c.yaw + turn + (0 if obj.w >= obj.d else 90)
    return {"mode": mode, "x": c.x, "y": c.y, "yaw": yaw, "base_cm": base}
