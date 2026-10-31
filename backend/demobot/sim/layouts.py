"""Layouts (docs/06 "Layouts"): the demo layout, valid random rearrangements, user edits, and the
validator shared with the red team."""

import math

import numpy as np

from demobot.goal_dsl import footprint_gap
from demobot.schemas import Layout, Rect, SceneObject, Vec2
from demobot.sim import constants as C

MIN_GAP_CM = 1.0  # between any two footprints
RANDOM_GAP_CM = 3.0  # random layouts leave a little more room
BOUNDS_SLACK_CM = 0.5


def default_frame() -> tuple[Rect, Vec2]:
    """The work area and robot base for the nominal 60 × 40 cm marker rectangle."""
    x0, y0, x1, y1 = C.DEFAULT_WORK_AREA
    return Rect(x0=x0, y0=y0, x1=x1, y1=y1), ((x0 + x1) / 2, y1 + C.ROBOT_BEHIND_FRONT_CM)


def reachable(base: Vec2, x: float, y: float) -> bool:
    d = math.dist(base, (x, y)) / 100
    return C.REACH_MIN_M <= d <= C.REACH_MAX_M


def reach_map(work: Rect, base: Vec2, step_cm: float = 2.0) -> dict[str, object]:
    """A grid over the work area marking reachable cells (the UI's faint overlay)."""
    xs = np.arange(work.x0, work.x1 + 1e-6, step_cm)
    ys = np.arange(work.y0, work.y1 + 1e-6, step_cm)
    grid = [[reachable(base, float(x), float(y)) for x in xs] for y in ys]
    return {"x0": work.x0, "y0": work.y0, "step_cm": step_cm, "cells": grid}


def validate(layout: Layout) -> list[str]:
    """Problems that make a layout unfair or impossible: out of bounds, overlapping, unreachable,
    duplicate names. Empty means valid."""
    problems: list[str] = []
    wa = layout.work_area
    names = [o.name for o in layout.objects]
    if len(set(names)) != len(names):
        problems.append("duplicate object names")
    for o in layout.objects:
        ex, ey = o.extents()
        s = BOUNDS_SLACK_CM
        if (
            o.x - ex < wa.x0 - s
            or o.x + ex > wa.x1 + s
            or o.y - ey < wa.y0 - s
            or o.y + ey > wa.y1 + s
        ):
            problems.append(f"{o.name} is outside the work area")
        if not reachable(layout.robot_base_cm, o.x, o.y):
            problems.append(f"{o.name} is out of the robot's reach")
        if o.w <= 0 or o.d <= 0 or o.h <= 0:
            problems.append(f"{o.name} has a non-positive size")
    objs = layout.objects
    for i, a in enumerate(objs):
        for b in objs[i + 1 :]:
            if footprint_gap(a, b) < MIN_GAP_CM:
                problems.append(f"{a.name} and {b.name} overlap")
    return problems


def _place_one(o: SceneObject, placed: list[SceneObject], layout: Layout,
               rng: np.random.Generator) -> SceneObject | None:  # fmt: skip
    wa = layout.work_area
    for _ in range(400):
        yaw = (
            0.0
            if o.shape in ("cylinder", "sphere")
            else float(rng.choice([0.0, 90.0, rng.uniform(0, 180)]))
        )
        cand = o.model_copy(update={"yaw": round(yaw, 1)})
        ex, ey = cand.extents()
        if wa.x1 - wa.x0 < 2 * ex or wa.y1 - wa.y0 < 2 * ey:
            return None
        x = float(rng.uniform(wa.x0 + ex, wa.x1 - ex))
        y = float(rng.uniform(wa.y0 + ey, wa.y1 - ey))
        cand = cand.model_copy(update={"x": round(x, 1), "y": round(y, 1)})
        if not reachable(layout.robot_base_cm, cand.x, cand.y):
            continue
        if all(footprint_gap(cand, q) >= RANDOM_GAP_CM for q in placed):
            return cand
    return None


def random_layout(base: Layout, seed: int, layout_id: str | None = None) -> Layout:
    """A valid random rearrangement of the same objects (containers placed first)."""
    rng = np.random.default_rng(seed)
    order = sorted(base.objects, key=lambda o: (not o.is_open, -o.w * o.d))
    for _ in range(50):
        placed: list[SceneObject] = []
        for o in order:
            cand = _place_one(o, placed, base, rng)
            if cand is None:
                break
            placed.append(cand)
        else:
            by_name = {o.name: o for o in placed}
            out = base.model_copy(
                update={
                    "id": layout_id or f"random-{seed}",
                    "source": "random",
                    "seed": seed,
                    "objects": [by_name[o.name] for o in base.objects],
                    "description": f"random rearrangement (seed {seed})",
                }
            )
            assert not validate(out), validate(out)
            return out
    raise ValueError(f"could not lay out {len(order)} objects in the work area")


def apply_user_edit(layout: Layout, moves: dict[str, Vec2], layout_id: str = "user") -> Layout:
    """Move objects to new (x, y) positions, e.g. dragged by a judge in the 3D twin."""
    unknown = set(moves) - {o.name for o in layout.objects}
    if unknown:
        raise ValueError(f"unknown objects: {sorted(unknown)}")
    objs = [
        o.model_copy(update={"x": moves[o.name][0], "y": moves[o.name][1]})
        if o.name in moves
        else o
        for o in layout.objects
    ]
    return layout.model_copy(update={"id": layout_id, "source": "user", "objects": objs})
