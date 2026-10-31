"""Synthetic demo clips with exact ground truth (docs/09 "Synthetic demo generator").

A random marker table (synth/table.py), 2–6 desk items, and a skin-toned arm that picks and
places them along scripted arcs, filmed by a random phone-like camera. Objects and the arm are
rendered by PyBullet through the same pinhole camera and composited over the table texture,
using PyBullet's segmentation mask, so masks and poses are exact.
"""

import json
import math
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pybullet as p

from demobot.camera import Camera
from demobot.goal_dsl import footprint_gap
from demobot.schemas import GoalClause, Layout, Rect, SceneObject, Selector
from demobot.sim.layouts import random_layout, reachable
from demobot.sim.render import view_proj
from demobot.sim.scene import _container_parts, hex_rgba
from demobot.sim.skills import insert_mode
from synth.objects import CATALOGUE
from synth.table import TableTruth, draw_texture, render_table, sample_camera, sample_markers

FPS = 30
W, H = 1280, 720
SKIN = (0.86, 0.66, 0.53, 1.0)
PALM = (8.0, 9.0, 2.6)  # cm: across, along the arm, thick
FOREARM_R, FOREARM_L = 3.3, 30.0
# (offset across the palm cm, length cm, splay degrees): four fingers and a thumb
FINGERS = ((-2.9, 5.5, 0), (-1.0, 6.3, 0), (1.0, 6.0, 0), (2.9, 5.0, 0), (0.0, 4.8, 55))
FAMILIES = ("place_in", "next_to", "line_up", "sort", "swap")
RELATIONS = ("left_of", "right_of", "in_front_of", "behind")


@dataclass
class Move:
    obj: str
    to: tuple[float, float]
    action: str  # place_in | place_next_to | place_at
    target: str | None = None
    relation: str | None = None


@dataclass
class Plan:
    family: str
    layout: Layout
    moves: list[Move]
    goal: list[GoalClause]
    summary: str
    narration: str
    meta: dict[str, Any] = field(default_factory=dict)


# ---------- task planning ----------
def _obj(kind: str, rng: np.random.Generator, role: str, taken: set[str]) -> SceneObject:
    item = CATALOGUE[kind]
    colors = [c for c in item.colors if f"{c[0]} {kind}" not in taken] or list(item.colors)
    word, hexcol = colors[int(rng.integers(len(colors)))]
    name, k = f"{word} {kind}", 2
    while name in taken:
        name, k = f"{word} {kind} {k}", k + 1
    taken.add(name)
    return SceneObject(name=name, kind=kind, role=role, shape=item.shape, x=0, y=0, w=item.w,  # type: ignore[arg-type]
                       d=item.d, h=item.h, color=hexcol, texture=item.texture(word))  # fmt: skip


def _frame(table: TableTruth) -> tuple[Rect, tuple[float, float]]:
    xs = [m[0] for m in table.markers.values()]
    ys = [m[1] for m in table.markers.values()]
    wa = Rect(x0=min(xs) + 4, y0=min(ys) + 4, x1=max(xs) - 4, y1=max(ys) - 4)
    return wa, ((wa.x0 + wa.x1) / 2, wa.y1 + 28.0)


def free_spot(objs: list[SceneObject], wa: Rect, base: tuple[float, float], size: tuple[float, float],
              near: tuple[float, float] | None = None, avoid: list[SceneObject] = (),  # type: ignore[assignment]
              gap: float = 4.0) -> tuple[float, float] | None:  # fmt: skip
    probe = SceneObject(name="_", kind="_", x=0, y=0, w=size[0], d=size[1], h=2)
    best, best_d = None, math.inf
    centre = near or ((wa.x0 + wa.x1) / 2, (wa.y0 + wa.y1) / 2)
    for x in np.arange(wa.x0 + size[0] / 2, wa.x1 - size[0] / 2, 1.0):
        for y in np.arange(wa.y0 + size[1] / 2, wa.y1 - size[1] / 2, 1.0):
            cand = probe.model_copy(update={"x": float(x), "y": float(y)})
            if not reachable(base, cand.x, cand.y):
                continue
            if any(footprint_gap(cand, o) < gap for o in [*objs, *avoid]):
                continue
            d = math.dist((cand.x, cand.y), centre)
            if d < best_d:
                best, best_d = (float(x), float(y)), d
    return best


def _layout(objs: list[SceneObject], table: TableTruth, seed: int) -> Layout:
    wa, base = _frame(table)
    return random_layout(Layout(objects=objs, work_area=wa, robot_base_cm=base), seed, "demo")


def plan_task(family: str, table: TableTruth, rng: np.random.Generator) -> Plan:
    """A task like the human's real clips, with the human's real objects (synth/objects.py)."""
    taken: set[str] = set()
    seed = int(rng.integers(1 << 30))
    S, C = Selector, GoalClause
    others = ["box cutter", "glue bottle", "tennis ball", "spoon"]

    def pick(n: int, pool: list[str]) -> list[str]:
        return [str(k) for k in rng.choice(pool, n, replace=False)]

    if family == "place_in":  # 01: the pens go in the container
        box = _obj(str(rng.choice(["box", "mug"], p=[0.7, 0.3])), rng, "container", taken)
        pens = [_obj("pen", rng, "moved", taken) for _ in range(2)]
        extra = [_obj(k, rng, "distractor", taken) for k in pick(int(rng.integers(1, 3)), others)]
        lay = _layout([box, *pens, *extra], table, seed)
        moves = [Move(i.name, (0, 0), "place_in", box.name) for i in pens]
        goal = [C(quant="all", select=S(kind="pen"), pred="inside", target=S(name=box.name))]
        return Plan(family, lay, moves, goal, f"Put both pens into the {box.name}.",
                    f"All the pens go in the {box.kind}.")  # fmt: skip
    if family == "next_to":  # 02: one item beside the container
        ref = _obj("box", rng, "reference", taken)
        item = _obj(
            str(rng.choice(["glue bottle", "box cutter", "tennis ball", "spoon"])),
            rng,
            "moved",
            taken,
        )
        extra = [_obj("pen", rng, "distractor", taken)]
        rel = str(rng.choice(RELATIONS, p=[0.3, 0.4, 0.15, 0.15]))
        lay = _layout([ref, item, *extra], table, seed)
        goal = [C(quant="the", select=S(name=item.name), pred=rel, target=S(name=ref.name))]  # type: ignore[arg-type]
        words = rel.replace("_", " ")
        return Plan(family, lay, [Move(item.name, (0, 0), "place_next_to", ref.name, rel)], goal,
                    f"Put the {item.name} {words} the {ref.name}.",
                    f"The {item.kind} goes {words} the {ref.kind}.", {"relation": rel})  # fmt: skip
    if family == "line_up":  # 03: three items in a row
        items = [_obj(k, rng, "moved", taken) for k in pick(3, [*others, "pen"])]
        lay = _layout(items, table, seed)
        goal = [C(quant="all", select=S(role="moved"), pred="collinear", order_by="x")]
        return Plan(family, lay, [], goal, "Line the items up in a row, left to right.",
                    "Line these up in a row.")  # fmt: skip
    if family == "sort":  # 04: pens into the mug, everything else into the box
        mug, box = _obj("mug", rng, "container", taken), _obj("box", rng, "container", taken)
        pens = [_obj("pen", rng, "moved", taken) for _ in range(2)]
        rest = [
            _obj(k, rng, "moved", taken) for k in pick(2, ["box cutter", "glue bottle", "spoon"])
        ]
        lay = _layout([mug, box, *pens, *rest], table, seed)
        moves = [Move(o.name, (0, 0), "place_in", mug.name) for o in pens]
        moves += [Move(o.name, (0, 0), "place_in", box.name) for o in rest]
        goal = [C(quant="all", select=S(kind="pen"), pred="inside", target=S(name=mug.name))]
        goal += [
            C(quant="all", select=S(kind=o.kind), pred="inside", target=S(name=box.name))
            for o in rest
        ]
        return Plan(family, lay, moves, goal, f"Pens into the {mug.name}, everything else into the {box.name}.",
                    "Pens go in the mug and the rest in the box.")  # fmt: skip
    # 05: swap two items through a free spot
    a, b = (
        _obj(k, rng, "moved", taken)
        for k in pick(2, ["glue bottle", "tennis ball", "box cutter", "spoon"])
    )
    extra = [_obj("pen", rng, "distractor", taken)]
    lay = _layout([a, b, *extra], table, seed)
    goal = [C(quant="pair", select=S(names=[a.name, b.name]), pred="swapped")]
    return Plan("swap", lay, [], goal, f"Swap the {a.name} and the {b.name}.",
                f"Swap the {a.kind} and the {b.kind}.")  # fmt: skip


def resolve_moves(plan: Plan) -> list[Move]:
    """Concrete target points for each move, given the evolving layout."""
    state = {o.name: o for o in plan.layout.objects}
    wa, base = plan.layout.work_area, plan.layout.robot_base_cm
    out: list[Move] = []

    def put(name: str, xy: tuple[float, float]) -> None:
        state[name] = state[name].model_copy(update={"x": xy[0], "y": xy[1]})

    if plan.family == "line_up":
        items = sorted((o for o in state.values() if o.role == "moved"), key=lambda o: o.x)
        widths = [o.extents()[0] * 2 for o in items]
        total = sum(widths) + 4 * (len(items) - 1)
        others = [o for o in state.values() if o.role != "moved"]
        for y in sorted(
            np.arange(wa.y0 + 5, wa.y1 - 5, 1.0), key=lambda v: abs(v - (wa.y0 + wa.y1) / 2)
        ):
            x = (wa.x0 + wa.x1) / 2 - total / 2
            slots = []
            for w in widths:
                slots.append((x + w / 2, float(y)))
                x += w + 4
            probe = [
                o.model_copy(update={"x": s[0], "y": s[1]})
                for o, s in zip(items, slots, strict=True)
            ]
            if all(footprint_gap(a, b) >= 3 for a in probe for b in others) and all(
                reachable(base, *s) for s in slots
            ):
                break
        # move items whose slot is occupied by another item last, via a buffer if needed
        for o, s in zip(items, slots, strict=True):
            blockers = [q for q in items if q.name != o.name
                        and footprint_gap(o.model_copy(update={"x": s[0], "y": s[1]}), state[q.name]) < 2]  # fmt: skip
            for q in blockers:
                buf = free_spot(list(state.values()), wa, base, (q.w + 1, q.w + 1), avoid=[
                    p_.model_copy(update={"x": ss[0], "y": ss[1]}) for p_, ss in zip(items, slots, strict=True)])  # fmt: skip
                if buf:
                    out.append(Move(q.name, buf, "place_at"))
                    put(q.name, buf)
            out.append(Move(o.name, s, "place_at"))
            put(o.name, s)
        return out
    if plan.family == "swap":
        a, b = plan.goal[0].select.names or []
        ax, ay, bx, by = state[a].x, state[a].y, state[b].x, state[b].y
        side = max(state[a].w, state[a].d) + 1
        buf = free_spot(list(state.values()), wa, base, (side, side)) or (
            (wa.x0 + wa.x1) / 2,
            wa.y0 + 6,
        )
        for m in (
            Move(a, buf, "place_at"),
            Move(b, (ax, ay), "place_at"),
            Move(a, (bx, by), "place_at"),
        ):
            out.append(m)
            put(m.obj, m.to)
        return out
    for m in plan.moves:
        o = state[m.obj]
        if m.action == "place_in":
            c = state[m.target or ""]
            out.append(Move(m.obj, (c.x, c.y), m.action, m.target))
            continue
        ref = state[m.target or ""]
        (ox, oy), (rx, ry) = o.extents(), ref.extents()
        gap = 3.0
        dx = {"left_of": -(rx + ox + gap), "right_of": rx + ox + gap}.get(m.relation or "", 0.0)
        dy = {"behind": -(ry + oy + gap), "in_front_of": ry + oy + gap}.get(m.relation or "", 0.0)
        to = (ref.x + dx, ref.y + dy)
        # clear anything in the way first
        target = o.model_copy(update={"x": to[0], "y": to[1]})
        for q in list(state.values()):
            if q.name not in (o.name, ref.name) and footprint_gap(target, q) < 2.5:
                buf = free_spot(list(state.values()), wa, base, (q.w + 1, q.w + 1), avoid=[target])
                if buf:
                    out.append(Move(q.name, buf, "place_at"))
                    put(q.name, buf)
        out.append(Move(m.obj, to, m.action, m.target, m.relation))
        put(m.obj, to)
    return out


# ---------- the animated scene ----------
def ease(a: float) -> float:
    a = min(1.0, max(0.0, a))
    return a * a * (3 - 2 * a)


def _to_sim(x: float, y: float, z: float) -> list[float]:
    return [x / 100, -y / 100, z / 100]


class Stage:
    """A render-only PyBullet world: visual bodies for objects and the arm."""

    def __init__(self, layout: Layout) -> None:
        self.cid = p.connect(p.DIRECT)
        self.bodies: dict[str, int] = {}
        for o in layout.objects:
            self.bodies[o.name] = self._body(o)
        palm = p.createVisualShape(p.GEOM_BOX, halfExtents=[PALM[0] / 200, PALM[1] / 200, PALM[2] / 200],
                                   rgbaColor=SKIN, physicsClientId=self.cid)  # fmt: skip
        arm = p.createVisualShape(p.GEOM_CAPSULE, radius=FOREARM_R / 100, length=FOREARM_L / 100,
                                  rgbaColor=SKIN, physicsClientId=self.cid)  # fmt: skip
        self.palm = p.createMultiBody(0, -1, palm, physicsClientId=self.cid)
        self.arm = p.createMultiBody(0, -1, arm, physicsClientId=self.cid)
        self.fingers = []
        for _, length, _ in FINGERS:
            f = p.createVisualShape(p.GEOM_CAPSULE, radius=0.85 / 100, length=length / 100,
                                    rgbaColor=SKIN, physicsClientId=self.cid)  # fmt: skip
            self.fingers.append(p.createMultiBody(0, -1, f, physicsClientId=self.cid))

    def _body(self, o: SceneObject) -> int:
        rgba = hex_rgba(o.color)
        if o.is_container:
            types, half, pos, orn = _container_parts(o)
            vis = p.createVisualShapeArray(
                shapeTypes=types, halfExtents=half, radii=[h[0] for h in half],
                lengths=[2 * h[2] for h in half], visualFramePositions=pos,
                visualFrameOrientations=orn, rgbaColors=[rgba] * len(types), physicsClientId=self.cid,
            )  # fmt: skip
        elif o.shape == "sphere":
            vis = p.createVisualShape(p.GEOM_SPHERE, radius=max(o.w, o.d) / 200, rgbaColor=rgba,
                                      physicsClientId=self.cid)  # fmt: skip
        elif o.shape == "cylinder":
            vis = p.createVisualShape(p.GEOM_CYLINDER, radius=max(o.w, o.d) / 200, length=o.h / 100,
                                      rgbaColor=rgba, physicsClientId=self.cid)  # fmt: skip
        else:
            vis = p.createVisualShape(p.GEOM_BOX, halfExtents=[o.w / 200, o.d / 200, o.h / 200],
                                      rgbaColor=rgba, physicsClientId=self.cid)  # fmt: skip
        body = p.createMultiBody(0, -1, vis, physicsClientId=self.cid)
        if o.texture and not o.is_container:
            tex = p.loadTexture(o.texture, physicsClientId=self.cid)
            p.changeVisualShape(
                body, -1, textureUniqueId=tex, rgbaColor=[1, 1, 1, 1], physicsClientId=self.cid
            )
        return body

    def pose(
        self, name: str, x: float, y: float, z: float, yaw: float, upright: str | None = None
    ) -> None:
        tilt = {"w": [0, math.pi / 2, 0], "d": [math.pi / 2, 0, 0]}.get(upright or "", [0, 0, 0])
        q = p.getQuaternionFromEuler([tilt[0], tilt[1], -math.radians(yaw)])
        p.resetBasePositionAndOrientation(
            self.bodies[name], _to_sim(x, y, z), q, physicsClientId=self.cid
        )

    def hand(self, x: float, y: float, z: float, toward: tuple[float, float]) -> None:
        """Palm centred at (x, y, z) cm; the forearm runs back and up towards `toward`."""
        dx, dy = toward[0] - x, toward[1] - y
        heading = math.atan2(dy, dx)
        yaw = -heading + math.pi / 2
        q = p.getQuaternionFromEuler([0, 0, yaw])
        p.resetBasePositionAndOrientation(self.palm, _to_sim(x, y, z), q, physicsClientId=self.cid)
        elev = math.radians(32)
        half = FOREARM_L / 2 + PALM[1] / 2
        cx = x + math.cos(heading) * math.cos(elev) * half
        cy = y + math.sin(heading) * math.cos(elev) * half
        cz = z + math.sin(elev) * half
        # capsule axis is local z: point it along the forearm direction
        d = np.array(
            [
                math.cos(heading) * math.cos(elev),
                -math.sin(heading) * math.cos(elev),
                math.sin(elev),
            ]
        )
        axis = np.cross([0, 0, 1], d)
        ang = math.acos(float(np.clip(d[2], -1, 1)))
        qa = p.getQuaternionFromAxisAngle(
            axis.tolist() if np.linalg.norm(axis) > 1e-6 else [1, 0, 0], ang
        )
        p.resetBasePositionAndOrientation(
            self.arm, _to_sim(cx, cy, cz), qa, physicsClientId=self.cid
        )
        # fingers point away from the forearm, curling down a little; the thumb points sideways
        fwd = np.array([-math.cos(heading), -math.sin(heading)])
        side = np.array([-fwd[1], fwd[0]])
        for body, (across, length, angle) in zip(self.fingers, FINGERS, strict=True):
            a = math.radians(angle)
            direction2 = fwd * math.cos(a) + side * math.sin(a)
            curl = math.radians(28)
            root = np.array([x, y]) + fwd * (PALM[1] / 2 - 0.6) + side * across
            if angle:  # thumb root sits at the side of the palm
                root = np.array([x, y]) + side * (PALM[0] / 2) + fwd * 0.5
            mid = root + direction2 * math.cos(curl) * length / 2
            mz = z - math.sin(curl) * length / 2
            d3 = np.array(
                [direction2[0] * math.cos(curl), -direction2[1] * math.cos(curl), -math.sin(curl)]
            )
            ax3 = np.cross([0, 0, 1], d3)
            ang3 = math.acos(float(np.clip(d3[2], -1, 1)))
            q3 = p.getQuaternionFromAxisAngle(ax3.tolist(), ang3)
            p.resetBasePositionAndOrientation(
                body, _to_sim(mid[0], mid[1], mz), q3, physicsClientId=self.cid
            )

    def close(self) -> None:
        p.disconnect(self.cid)


@dataclass
class Keyframe:
    hand: tuple[float, float, float]
    holding: str | None


def animate(
    plan: Plan, moves: list[Move], rng: np.random.Generator
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Per-frame poses {objects: {name: [x, y, z, yaw, upright]}, hand: [x, y, z]} and the
    step truth (times in seconds from the clip start)."""
    lay = plan.layout
    wa = lay.work_area
    state = {o.name: [o.x, o.y, o.h / 2, o.yaw, None] for o in lay.objects}
    specs = {o.name: o for o in lay.objects}
    rest = ((wa.x0 + wa.x1) / 2 + 8, wa.y0 - 30.0, 30.0)
    frames: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    hand = list(rest)
    holding: str | None = None
    hold_off = 0.0

    def emit(n: int, path: Any) -> None:
        nonlocal hand
        for i in range(n):
            hx, hy, hz = path((i + 1) / n)
            hand = [hx, hy, hz]
            if holding:
                s = state[holding]
                s[0], s[1], s[2] = hx, hy, hz - hold_off
            frames.append({"hand": [round(v, 2) for v in hand],
                           "objects": {k: [round(v, 3) if isinstance(v, float) else v for v in s] for k, s in state.items()}})  # fmt: skip

    def go(to: tuple[float, float, float], secs: float, lift: float = 0.0) -> None:
        start = tuple(hand)
        n = max(2, int(secs * FPS))
        emit(n, lambda a: (start[0] + (to[0] - start[0]) * ease(a), start[1] + (to[1] - start[1]) * ease(a),
                           start[2] + (to[2] - start[2]) * ease(a) + lift * math.sin(math.pi * ease(a))))  # fmt: skip

    def wait(secs: float) -> None:
        emit(max(1, int(secs * FPS)), lambda a: tuple(hand))

    wait(rng.uniform(1.6, 2.2))
    for m in moves:
        o = specs[m.obj]
        sx, sy, sz = state[m.obj][0], state[m.obj][1], state[m.obj][2]
        top = sz + o.h / 2
        t_start = len(frames) / FPS
        go((sx, sy, top + 12), rng.uniform(0.8, 1.2))
        go((sx, sy, top + PALM[2] / 2 + 0.3), rng.uniform(0.35, 0.5))
        wait(0.15)
        holding, hold_off = m.obj, PALM[2] / 2 + 0.3 + o.h / 2
        grasp_t = len(frames) / FPS
        go((sx, sy, top + 10), 0.4)
        upright = None
        if m.action == "place_in":
            c = specs[m.target or ""]
            mode = insert_mode(o, c)
            upright = (
                max(("w", o.w), ("d", o.d), key=lambda a: a[1])[0] if mode == "upright" else None
            )
            if mode == "diagonal":  # laid across the box, on top of whatever is inside
                inside = [state[n] for n in state if n not in (m.obj, c.name)
                          and abs(state[n][0] - c.x) < c.w / 2 and abs(state[n][1] - c.y) < c.d / 2]  # fmt: skip
                floor_top = max(
                    [s_[2] + specs[n_].h / 2 for n_, s_ in state.items() if s_ in inside] or [0.4]
                )
                diag = {
                    "to": (c.x, c.y),
                    "z": floor_top + o.h / 2,
                    "yaw": c.yaw + 45 + (0 if o.w >= o.d else 90),
                }
            else:
                diag = None
            land = c.h + 2.0 + o.h / 2 if upright else 0.4 + o.h / 2
        else:
            land = o.h / 2
            diag = None
        if diag is not None:
            land = specs[m.target or ""].h + 2.0 + o.h / 2
        go((m.to[0], m.to[1], max(top + 10, land + hold_off + 6)), rng.uniform(0.9, 1.4), lift=3)
        go((m.to[0], m.to[1], land + hold_off), 0.45)
        wait(0.12)
        holding = None
        release_t = len(frames) / FPS
        if upright:  # the object tips in and stands in the container
            c = specs[m.target or ""]
            long = max(o.w, o.d)
            s = state[m.obj]
            s0 = list(s)
            n = 8
            for i in range(n):
                a = (i + 1) / n
                s[0] = s0[0] + (c.x - s0[0]) * a
                s[1] = s0[1] + (c.y - s0[1]) * a
                s[2] = s0[2] + (0.4 + long / 2 - s0[2]) * a
                s[4] = upright if a > 0.5 else None
                emit(1, lambda _a: tuple(hand))
        elif m.action == "place_in" and diag is not None:
            s = state[m.obj]
            s0 = list(s)
            for i in range(8):
                a = (i + 1) / 8
                s[0] = s0[0] + (diag["to"][0] - s0[0]) * a
                s[1] = s0[1] + (diag["to"][1] - s0[1]) * a
                s[2] = s0[2] + (diag["z"] - s0[2]) * a
                s[3] = s0[3] + (diag["yaw"] - s0[3]) * a
                emit(1, lambda _a: tuple(hand))
        elif m.action == "place_in":
            state[m.obj][2] = 0.4 + o.h / 2
        go((m.to[0], m.to[1], land + 12), 0.35)
        steps.append({"action": m.action, "object": m.obj, "target": m.target, "relation": m.relation,
                      "t_start": round(t_start, 2), "t_end": round(len(frames) / FPS, 2),
                      "grasp_t": round(grasp_t, 2), "release_t": round(release_t, 2),
                      "from_cm": [round(sx, 2), round(sy, 2)], "to_cm": [round(m.to[0], 2), round(m.to[1], 2)]})  # fmt: skip
    go(rest, rng.uniform(0.9, 1.3))
    wait(rng.uniform(1.4, 2.0))
    return frames, steps


# ---------- handheld shake ----------
SHAKE_ROT_DEG = 0.8
SHAKE_TRANS_CM = 0.8


def _wobble(n: int, rng: np.random.Generator, amp: float) -> np.ndarray:
    """Smooth zero-mean motion: a few sinusoids between 0.3 and 2 Hz, peak about `amp`."""
    t = np.arange(n) / FPS
    out = np.zeros(n)
    for _ in range(3):
        f = rng.uniform(0.3, 2.0)
        out += rng.uniform(0.4, 1.0) * np.sin(2 * np.pi * f * t + rng.uniform(0, 2 * np.pi))
    return out * amp / max(1e-9, float(np.abs(out).max()))


def shaky_cameras(
    cam: Camera, n: int, rng: np.random.Generator, shake: float = 1.0
) -> list[Camera]:
    """The camera per frame: small rotations about its own centre plus a small drift."""
    if shake <= 0:
        return [cam] * n
    rot = np.stack([_wobble(n, rng, np.radians(SHAKE_ROT_DEG) * shake) for _ in range(3)], 1)
    tr = np.stack([_wobble(n, rng, SHAKE_TRANS_CM * shake) for _ in range(3)], 1)
    C = cam.center
    out = []
    for k in range(n):
        dR, _ = cv2.Rodrigues(rot[k])
        R = dR @ cam.R
        Ck = C + tr[k]
        out.append(Camera(cam.K, R, -R @ Ck, cam.width, cam.height))
    return out


# ---------- rendering ----------
def _shadow(img: np.ndarray, cam: Camera, plan: Plan, frame: dict[str, Any]) -> np.ndarray:
    """Soft contact shadows on the table under objects and the hand (light from above)."""
    mask = np.zeros(img.shape[:2], np.float32)
    specs = plan.layout.by_name()
    for name, (x, y, z, yaw, upright) in frame["objects"].items():
        o = specs[name]
        hw, hd = (o.w / 2 + 0.6, o.d / 2 + 0.6) if not upright else (0.9, 0.9)
        off = 0.25 * max(0.0, z - o.h / 2)
        c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        pts = [(x + off + c * u - s * v, y + off * 0.6 + s * u + c * v, 0.0)
               for u, v in ((-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd))]  # fmt: skip
        if o.shape in ("cylinder", "sphere"):
            r = max(o.w, o.d) / 2 + (0.6 if o.shape == "cylinder" else -0.8)
            pts = [
                (x + off + r * math.cos(a), y + off * 0.6 + r * math.sin(a), 0.0)
                for a in np.linspace(0, 2 * math.pi, 16)
            ]
        px = cam.project(np.array(pts)).astype(np.int32)
        cv2.fillPoly(mask, [px], 0.45 if z < o.h else 0.25)
    hx, hy, hz = frame["hand"]
    if hz < 40 and hy > plan.layout.work_area.y0 - 12:
        off = 0.25 * hz
        r = 5.0
        pts = [
            (hx + off + r * math.cos(a), hy + off * 0.6 + 1.3 * r * math.sin(a), 0.0)
            for a in np.linspace(0, 2 * math.pi, 16)
        ]
        cv2.fillPoly(
            mask, [cam.project(np.array(pts)).astype(np.int32)], 0.3 * max(0.2, 1 - hz / 40)
        )
    mask = cv2.GaussianBlur(mask, (0, 0), 6)
    return (img * (1 - mask[..., None])).astype(np.uint8)


def render_clip(plan: Plan, table: TableTruth, cams: list[Camera], frames: list[dict[str, Any]],
                out: Path, rng: np.random.Generator) -> dict[str, Any]:  # fmt: skip
    """Writes clip.mp4 (one camera per frame); returns per-object bounding boxes and mask
    polygons at 10 fps."""
    cam = cams[0]
    stage = Stage(plan.layout)
    ids = {b: n for n, b in stage.bodies.items()} | {stage.palm: "hand", stage.arm: "hand"}
    ids |= {f: "hand" for f in stage.fingers}
    wa = plan.layout.work_area
    rest_xy = ((wa.x0 + wa.x1) / 2 + 8, wa.y0 - 60.0)
    ff = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{cam.width}x{cam.height}",
         "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE,
    )  # fmt: skip
    tracks: dict[str, list[dict[str, Any]]] = {}
    gain = rng.uniform(0.92, 1.06)
    try:
        for i, fr in enumerate(frames):
            cam = cams[i]
            view, proj = view_proj(cam.R, cam.t, float(cam.K[0, 0]), cam.width, cam.height)
            base_img = render_table(table, cam, noise=0)
            for name, (x, y, z, yaw, upright) in fr["objects"].items():
                stage.pose(name, x, y, z, yaw, upright)
            stage.hand(*fr["hand"], toward=rest_xy)
            _, _, rgb, _, seg = p.getCameraImage(
                cam.width, cam.height, view, proj, renderer=p.ER_TINY_RENDERER, shadow=0,
                lightDirection=[0.3, -0.4, 1.0], lightAmbientCoeff=0.6, lightDiffuseCoeff=0.45,
                lightSpecularCoeff=0.05, physicsClientId=stage.cid,
            )  # fmt: skip
            rgb = cv2.cvtColor(
                np.asarray(rgb, np.uint8).reshape(cam.height, cam.width, 4)[:, :, :3],
                cv2.COLOR_RGB2BGR,
            )
            seg = np.asarray(seg).reshape(cam.height, cam.width)
            img = _shadow(base_img, cam, plan, fr)
            fg = seg >= 0
            img[fg] = rgb[fg]
            img = np.clip(
                img.astype(np.float32) * gain + rng.normal(0, 2.2, img.shape), 0, 255
            ).astype(np.uint8)
            _, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 82])
            img = cv2.imdecode(jpg, cv2.IMREAD_COLOR)
            assert ff.stdin is not None
            ff.stdin.write(img.tobytes())
            if i % (FPS // 10) == 0:
                body_of = (seg & ((1 << 24) - 1)) if seg.max() > 1 << 24 else seg
                for b, name in ids.items():
                    m = (body_of == b).astype(np.uint8)
                    entry = tracks.setdefault(name, [])
                    if name == "hand" and entry and entry[-1]["t"] == round(i / FPS, 2):
                        prev = entry.pop()
                        m |= prev.pop("_mask")
                    if not m.any():
                        entry.append(
                            {"t": round(i / FPS, 2), "bbox": None, "_mask": m}
                            if name == "hand"
                            else {"t": round(i / FPS, 2), "bbox": None}
                        )
                        continue
                    ys, xs = np.nonzero(m)
                    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    big = max(cs, key=cv2.contourArea)
                    poly = cv2.approxPolyDP(big, 1.5, True).reshape(-1, 2).tolist()
                    rec: dict[str, Any] = {"t": round(i / FPS, 2), "bbox": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
                                           "area": int(m.sum()), "poly": poly}  # fmt: skip
                    if name == "hand":
                        rec["_mask"] = m
                    entry.append(rec)
    finally:
        assert ff.stdin is not None
        ff.stdin.close()
        ff.wait()
        stage.close()
    for rec in tracks.get("hand", []):
        rec.pop("_mask", None)
    return tracks


def make_clip(family: str, seed: int, out_dir: Path, shake: float = 1.0) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    table = draw_texture(sample_markers(rng), rng)
    cam = sample_camera(table, rng, W, H)
    plan = plan_task(family, table, rng)
    moves = resolve_moves(plan)
    frames, steps = animate(plan, moves, rng)
    cams = shaky_cameras(cam, len(frames), rng, shake)
    out_dir.mkdir(parents=True, exist_ok=True)
    tracks = render_clip(plan, table, cams, frames, out_dir / "clip.mp4", rng)
    final = {n: s for n, s in frames[-1]["objects"].items()}
    C = cam.center
    truth = {
        "family": family,
        "seed": seed,
        "summary": plan.summary,
        "narration": plan.narration,
        "fps": FPS,
        "size": [cam.width, cam.height],
        "camera": {
            "K": cam.K.tolist(),
            "R": cam.R.tolist(),
            "t": cam.t.tolist(),
            "position_cm": [float(C[0]), float(C[1]), float(-C[2])],
            "tilt_deg": float(np.degrees(np.arccos(np.clip(cam.R[2, 2], -1, 1)))),
        },
        "markers": {str(k): list(v) for k, v in table.markers.items()},
        "work_area": plan.layout.work_area.model_dump(),
        "robot_base_cm": list(plan.layout.robot_base_cm),
        "objects": [
            {
                **o.model_dump(exclude={"texture"}),
                "texture": Path(o.texture).name if o.texture else None,
                "final": {
                    "x": final[o.name][0],
                    "y": final[o.name][1],
                    "z": final[o.name][2],
                    "upright": final[o.name][4],
                },
            }
            for o in plan.layout.objects
        ],
        "steps": steps,
        "goal": [g.model_dump(exclude_none=True) for g in plan.goal],
        "duration_s": round(len(frames) / FPS, 2),
        "shake": shake,
        "camera_track": [  # per 10 fps frame: world (x, y, z_down) -> camera
            {
                "t": round(k / FPS, 2),
                "R": [[round(v, 6) for v in r] for r in cams[k].R.tolist()],
                "t_vec": [round(v, 4) for v in cams[k].t.tolist()],
            }
            for k in range(0, len(frames), FPS // 10)
        ],
        "frames": frames[:: FPS // 10],  # 10 fps poses
        "tracks": tracks,  # 10 fps boxes and mask polygons, per object and the hand
    }
    (out_dir / "truth.json").write_text(json.dumps(truth, separators=(",", ":")))
    return truth
