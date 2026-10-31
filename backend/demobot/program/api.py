"""The skill API exposed to generated robot programs (docs/06). This is a contract: its
docstrings go into Muse Wonder's prompt and the exported `skill_api.md`.

Units: centimetres in the table frame (+x right, +y towards the robot), degrees.
A program defines `run(scene, robot)`. `scene` always reads the live state.
"""

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from demobot import goal_dsl
from demobot.schemas import SkillCall
from demobot.sim import constants as C
from demobot.sim.scene import Scene as SimScene
from demobot.sim.scene import to_table
from demobot.sim.skills import SkillError, Skills, container_slot


# ---------- errors (a program should let these surface; the simulator reports them) ----------
class SkillApiError(Exception):
    """Base class of every error the skill API raises."""


class NotReachable(SkillApiError):
    """The robot cannot reach that point (too near or too far from its base)."""


class NothingHeld(SkillApiError):
    """A place skill was called while the robot holds nothing."""


class AlreadyHolding(SkillApiError):
    """pick() was called while the robot already holds an object."""


class NoFreeSpot(SkillApiError):
    """free_spot() found no clear, reachable spot matching the request."""


class Collision(SkillApiError):
    """The robot knocked another object out of place."""


class NoSuchObject(SkillApiError):
    """No object has that name."""


class PlaceFailed(SkillApiError):
    """The object did not end up where it was placed (it fell or slid off)."""


class TooManySkillCalls(SkillApiError):
    """A program may make at most 40 robot calls."""


class TooWide(SkillApiError):
    """The object is wider than the gripper opens: it cannot be picked (a forged skill may move it)."""


class ForgeOnly(SkillApiError):
    """A forge-tier primitive was used outside a forged skill."""


SIDES = ("left_of", "right_of", "in_front_of", "behind")
GRIPPER_MAX_CM = 2 * C.FINGER_OPEN * 100  # the Panda's fingers open 8 cm
# low-level primitives a forged skill may use (docs/11 F1); normal programs cannot
FORGE_ATTRS = {"ee_pose", "move_ee", "grip", "wait", "pose", "in_contact", "gripper_width_max"}
TALL_CM = 5.0
TALL_EXTRA_CM = 6.0


@dataclass(frozen=True)
class Obj:
    """A read-only snapshot of one object. Get a fresh one from `scene` after moving things.

    name, kind, role ("moved" | "container" | "reference" | "distractor");
    x, y, z: centre in cm (z above the table); w, d, h: size in cm along x, y, z; yaw: degrees.
    """

    name: str
    kind: str
    role: str
    x: float
    y: float
    z: float
    w: float
    d: float
    h: float
    yaw: float


class Scene:
    """The table as it is now."""

    def __init__(self, sim: SimScene) -> None:
        self._sim = sim
        self._held: str | None = None
        self._forge: list[set[str]] = []  # stack of the running forged skills' target objects

    def _forge_only(self, what: str) -> None:
        if not self._forge:
            raise ForgeOnly(f"{what} is a forge-tier primitive: only forged skills may use it")

    # ---------- forge tier (inside forged skills only) ----------
    def pose(self, obj: Obj) -> tuple[float, float, float, float]:
        """(x, y, z, yaw) of `obj` now, in cm and degrees (forge tier)."""
        self._forge_only("scene.pose")
        o = self._snap(obj.name)
        return o.x, o.y, o.z, o.yaw

    def in_contact(self, a: Obj, b: Obj | str) -> bool:
        """True if `a` touches `b` (another object, or "robot") right now (forge tier)."""
        self._forge_only("scene.in_contact")
        import pybullet as pb

        body_a = self._sim.objects[a.name].body
        body_b = (
            self._sim.robot
            if b == "robot"
            else self._sim.objects[b.name if isinstance(b, Obj) else b].body
        )
        return bool(
            pb.getContactPoints(bodyA=body_a, bodyB=body_b, physicsClientId=self._sim.client)
        )

    def gripper_width_max(self) -> float:
        """How wide the gripper opens, in cm (about 8) (forge tier)."""
        self._forge_only("scene.gripper_width_max")
        return GRIPPER_MAX_CM

    def _snap(self, name: str) -> Obj:
        s = self._sim.snapshot(name)
        hx, hy = s.extents()
        return Obj(s.name, s.kind, s.role, s.x, s.y, s.z, 2 * hx, 2 * hy, s.h, s.yaw)

    def objects(self) -> list[Obj]:
        """Every object in this layout."""
        return [self._snap(n) for n in self._sim.objects]

    def get(self, name: str) -> Obj:
        """The object with this exact name; raises NoSuchObject."""
        if name not in self._sim.objects:
            raise NoSuchObject(f"no object named {name!r}; objects are {sorted(self._sim.objects)}")
        return self._snap(name)

    def of_kind(self, kind: str) -> list[Obj]:
        """Every object of this kind, sorted left to right (by x)."""
        return sorted((o for o in self.objects() if o.kind == kind), key=lambda o: o.x)

    def with_role(self, role: str) -> list[Obj]:
        """Every object with this role, sorted left to right."""
        return sorted((o for o in self.objects() if o.role == role), key=lambda o: o.x)

    def containers(self) -> list[Obj]:
        """Every container, sorted left to right."""
        return self.with_role("container")

    def bounds(self) -> tuple[float, float, float, float]:
        """The work area (x0, y0, x1, y1) in cm. Keep placements inside it."""
        wa = self._sim.work_area
        return wa.x0, wa.y0, wa.x1, wa.y1

    def free_spot(
        self,
        near: Obj | None = None,
        side: str | None = None,
        size: tuple[float, float] = (6, 6),
        clearance: float = 2.0,
        avoid: list[tuple[float, float, float, float]] | None = None,
    ) -> tuple[float, float]:
        """A clear, reachable (x, y) for an object of `size` (w, d) cm, at least `clearance` cm
        from everything else and inside the work area. Objects taller than 5 cm get 6 cm more
        room, because the gripper hand is wide. `avoid` lists extra regions (x, y, w, d) to keep
        clear, e.g. slots you are about to fill. With `near`, the closest such spot to that
        object; with `side` too ("left_of" | "right_of" | "in_front_of" | "behind"), only spots
        fully on that side of it. Without `near`, the clear spot nearest the work-area centre.
        Raises NoFreeSpot."""
        try:
            return self._spot(near, side, size, clearance, avoid)
        except NoFreeSpot as e:
            if size[0] != size[1]:
                try:
                    self._spot(near, side, (size[1], size[0]), clearance, avoid)
                except NoFreeSpot:
                    raise e from None
                raise NoFreeSpot(f"{e}; turned 90° it fits: free_spot(size=({size[1]:.0f}, {size[0]:.0f}), ...) "
                                 "then place_at(x, y, yaw=obj.yaw + 90)") from None  # fmt: skip
            raise

    def _spot(
        self,
        near: Obj | None,
        side: str | None,
        size: tuple[float, float],
        clearance: float,
        avoid: list[tuple[float, float, float, float]] | None,
    ) -> tuple[float, float]:
        if side is not None and side not in SIDES:
            raise ValueError(f"side must be one of {SIDES}")
        x0, y0, x1, y1 = self.bounds()
        hw, hd = size[0] / 2, size[1] / 2
        xs = np.arange(x0 + hw, x1 - hw + 1e-6, 1.0)
        ys = np.arange(y0 + hd, y1 - hd + 1e-6, 1.0)
        if not len(xs) or not len(ys):
            raise NoFreeSpot("the requested size does not fit in the work area")
        gx, gy = np.meshgrid(xs, ys)
        ok = np.ones_like(gx, bool)
        boxes = [
            (o.x, o.y, *o.extents(), clearance + (TALL_EXTRA_CM if o.h > TALL_CM else 0.0))
            for o in self._sim.state()
            if o.name != self._held
        ]
        boxes += [(ax, ay, aw / 2, ad / 2, clearance) for ax, ay, aw, ad in avoid or []]
        for ox, oy, ex, ey, need in boxes:
            dx = np.abs(gx - ox) - hw - ex
            dy = np.abs(gy - oy) - hd - ey
            gap = np.where((dx > 0) & (dy > 0), np.hypot(dx, dy), np.maximum(dx, dy))
            ok &= gap >= need
        bx, by = self._sim.robot_base_cm
        dist = np.hypot(gx - bx, gy - by) / 100
        ok &= (dist >= C.REACH_MIN_M) & (dist <= C.REACH_MAX_M)
        if near is not None:
            nx, ny = near.w / 2, near.d / 2
            if side == "left_of":
                ok &= (gx + hw <= near.x - nx) & (np.abs(gy - near.y) <= max(nx, ny))
            elif side == "right_of":
                ok &= (gx - hw >= near.x + nx) & (np.abs(gy - near.y) <= max(nx, ny))
            elif side == "behind":
                ok &= (gy + hd <= near.y - ny) & (np.abs(gx - near.x) <= max(nx, ny))
            elif side == "in_front_of":
                ok &= (gy - hd >= near.y + ny) & (np.abs(gx - near.x) <= max(nx, ny))
            score = np.hypot(gx - near.x, gy - near.y)
        else:
            score = np.hypot(gx - (x0 + x1) / 2, gy - (y0 + y1) / 2)
        if not ok.any():
            where = f" {side.replace('_', ' ')} {near.name}" if near and side else ""
            raise NoFreeSpot(f"no clear spot{where} for a {size[0]:.0f}×{size[1]:.0f} cm object")
        k = int(np.argmin(np.where(ok, score, np.inf)))
        return round(float(gx.flat[k]), 1), round(float(gy.flat[k]), 1)

    def is_inside(self, obj: Obj, container: Obj) -> bool:
        """True if obj (fresh snapshot) sits inside the container."""
        a, c = self._sim.snapshot(obj.name), self._sim.snapshot(container.name)
        return goal_dsl.inside(a, c, sim=True)[0]

    def distance(self, a: Obj, b: Obj) -> float:
        """Centre-to-centre distance in cm on the table plane."""
        return math.hypot(a.x - b.x, a.y - b.y)


class Robot:
    """A Franka Panda arm that picks from above and places gently."""

    def __init__(self, sim: SimScene, scene: Scene, calls: list[SkillCall]) -> None:
        self._sim = sim
        self._scene = scene
        self._skills = Skills(sim)
        self._calls = calls
        self._was_contained: set[str] = set()

    # ---------- bookkeeping ----------
    def _begin(self, skill: str, **args: Any) -> SkillCall:
        if len(self._calls) >= C.MAX_SKILL_CALLS:
            raise TooManySkillCalls(f"more than {C.MAX_SKILL_CALLS} robot calls")
        call = SkillCall(skill=skill, args=args, t=round(self._sim.time_s, 3))
        self._calls.append(call)
        return call

    def _fail(self, call: SkillCall, err: SkillApiError) -> SkillApiError:
        call.ok, call.error = False, f"{type(err).__name__}: {err}"
        return err

    def _contained(self) -> set[str]:
        """Objects inside some container right now."""
        state = self._sim.state()
        boxes = [o for o in state if o.is_open]
        return {
            o.name for o in state
            if any(goal_dsl.inside(o, c, sim=True)[0] for c in boxes if c.name != o.name)
        }  # fmt: skip

    def _snapshot_xy(self) -> dict[str, tuple[float, float]]:
        self._was_contained = self._contained()
        return {n: self._sim.pose_cm(n)[:2] for n in self._sim.objects}

    def _check_disturbed(
        self, call: SkillCall, before: dict[str, tuple[float, float]], ignore: set[str]
    ) -> None:
        settled_in = self._contained() & self._was_contained  # jostled inside a box is fine
        moved = [
            n for n, xy in before.items()
            if n not in ignore and n not in settled_in
            and math.dist(xy, self._sim.pose_cm(n)[:2]) > C.DISPLACED_CM
        ]  # fmt: skip
        if moved:
            raise self._fail(call, Collision(f"knocked {', '.join(sorted(moved))} out of place"))

    def can_reach(self, x: float, y: float) -> bool:
        """True if the gripper can reach (x, y) from above."""
        d = math.dist(self._sim.robot_base_cm, (x, y)) / 100
        return C.REACH_MIN_M <= d <= C.REACH_MAX_M

    # ---------- skills ----------
    def pick(self, obj: Obj) -> None:
        """Grasp `obj` from above and lift it. Raises AlreadyHolding or NotReachable."""
        call = self._begin("pick", object=obj.name)
        if self._scene._held is not None:
            raise self._fail(call, AlreadyHolding(f"already holding {self._scene._held}"))
        if obj.name not in self._sim.objects:
            raise self._fail(call, NoSuchObject(f"no object named {obj.name!r}"))
        x, y, _ = self._sim.pose_cm(obj.name)
        if not self.can_reach(x, y):
            raise self._fail(
                call, NotReachable(f"{obj.name} at ({x:.0f}, {y:.0f}) is out of reach")
            )
        spec = self._sim.objects[obj.name].spec
        if spec.shape != "sphere" and min(spec.w, spec.d) > GRIPPER_MAX_CM:
            raise self._fail(call, TooWide(f"{obj.name} is {min(spec.w, spec.d):.1f} cm wide; the gripper opens "
                                           f"{GRIPPER_MAX_CM:.0f} cm, so it cannot be picked (request a new skill to move it)"))  # fmt: skip
        if spec.is_open:
            raise self._fail(call, NotReachable(f"{obj.name} is a container; containers stay put"))
        before = self._snapshot_xy()
        try:
            self._skills.pick(obj.name)
        except SkillError as e:
            raise self._fail(call, NotReachable(f"cannot grasp {obj.name}: {e.reason}")) from None
        self._scene._held = obj.name
        self._check_disturbed(call, before, {obj.name})

    def _place(
        self,
        call: SkillCall,
        x: float,
        y: float,
        surface_z_m: float,
        ignore: set[str],
        container: str | None = None,
        slot: dict[str, float | str | None] | None = None,
    ) -> None:
        held = self._scene._held
        if held is None:
            raise self._fail(call, NothingHeld("nothing is held; call pick() first"))
        if not self.can_reach(x, y):
            raise self._fail(call, NotReachable(f"({x:.0f}, {y:.0f}) is out of reach"))
        before = self._snapshot_xy()
        try:
            self._skills.place((x, y), surface_z_m, container, slot)
        except SkillError as e:
            raise self._fail(
                call, NotReachable(f"cannot place at ({x:.0f}, {y:.0f}): {e.reason}")
            ) from None
        finally:
            if self._skills.held is None:
                self._scene._held = None
        if container is not None:  # contents jostled but still inside are fine
            c = self._sim.snapshot(container)
            ignore = ignore | {
                o.name for o in self._sim.state() if goal_dsl.inside(o, c, sim=True)[0]
            }
        self._check_disturbed(call, before, {held, *ignore})
        fx, fy, _ = self._sim.pose_cm(held)
        err = math.dist((fx, fy), (x, y))
        if err > C.DROPPED_CM:
            raise self._fail(
                call, PlaceFailed(f"{held} landed {err:.1f} cm from ({x:.0f}, {y:.0f})")
            )

    def place_at(self, x: float, y: float, yaw: float | None = None) -> None:
        """Put the held object down with its centre at (x, y) and let go. With `yaw` (degrees,
        like Obj.yaw) the gripper turns the object to that orientation first; without it the
        object keeps its orientation. Turning a long object 90° (yaw=obj.yaw + 90) swaps its
        footprint, which helps it fit a narrow gap."""
        call = self._begin(
            "place_at", x=round(x, 1), y=round(y, 1), yaw=None if yaw is None else round(yaw, 1)
        )
        slot: dict[str, float | str | None] | None = None
        if yaw is not None:
            slot = {"mode": "flat", "x": x, "y": y, "yaw": float(yaw), "base_cm": 0.0}
        self._place(call, x, y, 0.0, set(), slot=slot)

    def place_in(self, container: Obj) -> None:
        """Drop the held object into the container, centred over it."""
        call = self._begin("place_in", container=container.name)
        if container.name not in self._sim.objects:
            raise self._fail(call, NoSuchObject(f"no object named {container.name!r}"))
        c = self._sim.snapshot(container.name)
        held = self._scene._held
        if held is None:
            raise self._fail(call, NothingHeld("nothing is held; call pick() first"))
        contents = [
            o for o in self._sim.state()
            if o.name not in (held, c.name) and goal_dsl.inside(o, c, sim=True)[0]
        ]  # fmt: skip
        slot = container_slot(self._sim.objects[held].spec, c, contents)
        x, y = float(slot["x"] or c.x), float(slot["y"] or c.y)
        self._place(call, x, y, C.CONTAINER_WALL_M, {c.name}, container=c.name, slot=slot)

    def place_next_to(self, ref: Obj, side: str, gap: float = 2.0) -> None:
        """Put the held object `gap` cm beside `ref`: side is "left_of" (−x), "right_of" (+x),
        "in_front_of" (+y, towards the robot) or "behind" (−y)."""
        call = self._begin("place_next_to", ref=ref.name, side=side, gap=gap)
        if side not in SIDES:
            raise self._fail(call, NotReachable(f"side must be one of {SIDES}"))
        held = self._scene._held
        if held is None:
            raise self._fail(call, NothingHeld("nothing is held; call pick() first"))
        r = self._sim.snapshot(ref.name)
        hx, hy = self._sim.objects[held].spec.extents()
        rx, ry = r.extents()
        x, y = r.x, r.y
        if side == "left_of":
            x -= rx + hx + gap
        elif side == "right_of":
            x += rx + hx + gap
        elif side == "behind":
            y -= ry + hy + gap
        else:
            y += ry + hy + gap
        self._place(call, x, y, 0.0, set())

    def move(self, obj: Obj, x: float, y: float, yaw: float | None = None) -> None:
        """pick(obj) then place_at(x, y, yaw)."""
        self.pick(obj)
        self.place_at(x, y, yaw)

    def home(self) -> None:
        """Return the arm to its rest pose."""
        self._begin("home")
        self._skills.home()

    # ---------- forge tier (inside forged skills only) ----------
    def ee_pose(self) -> tuple[float, float, float, float]:
        """(x, y, z, yaw) of the gripper in table cm and degrees (forge tier)."""
        self._scene._forge_only("robot.ee_pose")
        pos = self._skills.ee_pos()
        x, y = to_table(pos)
        return round(x, 2), round(y, 2), round(pos[2] * 100, 2), round(self._skills.ee_yaw_deg(), 1)

    def move_ee(
        self, x: float, y: float, z: float, yaw: float | None = None, speed: float = 1.0
    ) -> None:
        """Move the gripper in a straight line to (x, y, z) cm (z above the table), turning to `yaw`
        degrees if given. Raises NotReachable, or Collision if anything but the skill's own objects
        moves more than 1 cm (forge tier)."""
        self._scene._forge_only("robot.move_ee")
        call = self._begin(
            "move_ee", x=round(x, 1), y=round(y, 1), z=round(z, 1), yaw=yaw, speed=speed
        )
        if not self.can_reach(x, y):
            raise self._fail(call, NotReachable(f"({x:.0f}, {y:.0f}) is out of reach"))
        before = self._snapshot_xy()
        try:
            self._skills.move_line((x, y, z), yaw, max(0.1, min(2.0, float(speed))))
        except SkillError as e:
            raise self._fail(
                call, NotReachable(f"cannot move to ({x:.0f}, {y:.0f}, {z:.0f}): {e.reason}")
            ) from None
        allowed = set().union(*self._scene._forge) | (
            {self._scene._held} if self._scene._held else set()
        )
        self._check_disturbed(call, before, allowed)

    def grip(self, state: str, width_cm: float | None = None) -> None:
        """ "close": close the fingers (to `width_cm` if given); an object between them is grasped.
        "open": open them (to `width_cm` if given) and let go of anything held (forge tier)."""
        self._scene._forge_only("robot.grip")
        call = self._begin("grip", state=state, width_cm=width_cm)
        if state not in ("open", "close"):
            raise self._fail(call, NotReachable('grip state must be "open" or "close"'))
        if state == "open":
            if self._scene._held is not None:
                self._skills.detach()
                self._skills.release()
                self._scene._held = None
            self._skills.set_fingers((width_cm or GRIPPER_MAX_CM) / 200)
            self._sim.step(30)
            return
        name = self._skills.between_fingers()
        if name is not None and self._scene._held is None:
            spec = self._sim.objects[name].spec
            if min(spec.w, spec.d) <= GRIPPER_MAX_CM or spec.shape == "sphere":
                self._skills.attach(name)
                self._scene._held = name
                return
        self._skills.set_fingers((width_cm or 0.0) / 200)
        self._sim.step(30)

    def wait(self, seconds: float) -> None:
        """Let the physics run for `seconds` (at most 3) so things settle (forge tier)."""
        self._scene._forge_only("robot.wait")
        self._sim.step(int(max(0.0, min(3.0, float(seconds))) / C.TIME_STEP))


def make_api(sim: SimScene, calls: list[SkillCall], logs: list[str]) -> dict[str, Any]:
    """The only names injected into a program, besides safe builtins."""
    scene = Scene(sim)
    robot = Robot(sim, scene, calls)

    def log(msg: str) -> None:
        """Write a line to the run log (shown in the UI)."""
        if len(logs) < 200:
            logs.append(str(msg)[:300])

    return {"scene": scene, "robot": robot, "log": log, "math": math}


API_ERRORS = (
    NotReachable, NothingHeld, AlreadyHolding, NoFreeSpot, Collision, NoSuchObject, PlaceFailed,
    TooManySkillCalls, TooWide, ForgeOnly,
)  # fmt: skip
