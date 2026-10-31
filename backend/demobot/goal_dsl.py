"""The declarative goal (docs/02 "Goal DSL"), shared by every verification path.

Pure geometry on table-cm states; no I/O. Tolerances are ported from the first repo:
- inside: the centre within the container footprint shrunk by 1 cm per side; in sim (z known)
  also z below the container height + 2 cm;
- relations: a gap of −1 to 8 cm and a lateral offset ≤ 3 cm + half the larger depth;
- near: ≤ 4 cm (centre to point, or footprint gap to a target);
- collinear: PCA residual ≤ 2 cm, order equal to `order` or its reverse; `order_by` = "x" or
  "y" requires the line to run within 30° of that axis;
- swapped: each object ≤ 4 cm from the other's initial position.
"""

import math
from collections.abc import Mapping, Sequence

import numpy as np

from demobot.schemas import ClauseResult, GoalClause, SceneObject, Selector

State = Mapping[str, SceneObject]

INSIDE_SHRINK_CM = 1.0
RIM_CLEARANCE_CM = 2.0
GAP_MIN_CM = -1.0
GAP_MAX_CM = 8.0
LATERAL_BASE_CM = 3.0
NEAR_CM = 4.0
COLLINEAR_RESIDUAL_CM = 2.0
COLLINEAR_AXIS_DEG = 30.0
SWAPPED_CM = 4.0
RELATIONS = ("left_of", "right_of", "in_front_of", "behind")
_EPS = 1e-9


# ---------- selection ----------
def select(sel: Selector, state: State) -> list[SceneObject]:
    """Objects matching a selector, sorted by name for determinism."""
    if sel.names:
        return [state[n] for n in sel.names if n in state]
    out = [
        o
        for o in state.values()
        if (sel.name is None or o.name == sel.name)
        and (sel.kind is None or o.kind == sel.kind)
        and (sel.role is None or o.role == sel.role)
    ]
    return sorted(out, key=lambda o: o.name)


def describe(sel: Selector) -> str:
    if sel.names:
        return " and ".join(sel.names)
    if sel.name:
        return sel.name
    if sel.kind:
        return f"every {sel.kind}"
    return f"every {sel.role} object"


# ---------- predicates on single objects ----------
def inside(a: SceneObject, c: SceneObject, sim: bool) -> tuple[bool, dict[str, float | bool]]:
    ex, ey = c.extents()
    mx = ex - INSIDE_SHRINK_CM - abs(a.x - c.x)
    my = ey - INSIDE_SHRINK_CM - abs(a.y - c.y)
    margin = min(mx, my)
    holds = margin >= -_EPS
    measured: dict[str, float | bool] = {"margin_cm": round(margin, 2)}
    if sim:
        below_rim = a.z < c.h + RIM_CLEARANCE_CM  # not resting on the rim
        measured["z_cm"] = round(a.z, 2)
        measured["below_rim"] = below_rim
        holds = holds and below_rim
    return holds, measured


def relation(a: SceneObject, b: SceneObject, r: str) -> tuple[bool, dict[str, float | bool]]:
    (aw, ad), (bw, bd) = a.extents(), b.extents()  # half-extents
    if r == "left_of":
        gap, lateral, span = (b.x - bw) - (a.x + aw), abs(a.y - b.y), max(ad, bd)
    elif r == "right_of":
        gap, lateral, span = (a.x - aw) - (b.x + bw), abs(a.y - b.y), max(ad, bd)
    elif r == "behind":  # −y
        gap, lateral, span = (b.y - bd) - (a.y + ad), abs(a.x - b.x), max(aw, bw)
    else:  # in_front_of, +y
        gap, lateral, span = (a.y - ad) - (b.y + bd), abs(a.x - b.x), max(aw, bw)
    limit = LATERAL_BASE_CM + span
    holds = GAP_MIN_CM - _EPS <= gap <= GAP_MAX_CM + _EPS and lateral <= limit + _EPS
    return holds, {
        "gap_cm": round(gap, 2),
        "lateral_cm": round(lateral, 2),
        "lateral_limit_cm": round(limit, 2),
    }


def footprint_gap(a: SceneObject, b: SceneObject) -> float:
    (aw, ad), (bw, bd) = a.extents(), b.extents()
    gx = abs(a.x - b.x) - aw - bw
    gy = abs(a.y - b.y) - ad - bd
    return max(gx, gy) if gx < 0 or gy < 0 else math.hypot(gx, gy)


def collinear(
    objs: Sequence[SceneObject], order: Sequence[str] | None, order_by: str | None
) -> tuple[bool, dict[str, float | bool | str]]:
    if len(objs) < 2:
        return True, {"residual_cm": 0.0}
    pts = np.array([(o.x, o.y) for o in objs], float)
    centred = pts - pts.mean(axis=0)
    if len(objs) == 2:
        direction = centred[1] - centred[0]
        norm = np.linalg.norm(direction)
        direction = direction / norm if norm > 0 else np.array([1.0, 0.0])
    else:
        direction = np.linalg.svd(centred, full_matrices=False)[2][0]
    proj = centred @ direction
    perp = centred - np.outer(proj, direction)
    residual = float(np.linalg.norm(perp, axis=1).max())
    names = [o.name for o in objs]
    got = [names[i] for i in sorted(range(len(objs)), key=lambda i: proj[i])]
    order_ok = True
    if order:
        want = [n for n in order if n in names]
        order_ok = got in (want, want[::-1])
    axis_ok = True
    angle = math.degrees(math.atan2(abs(direction[1]), abs(direction[0])))  # 0 = along x
    if order_by == "x":
        axis_ok = angle <= COLLINEAR_AXIS_DEG
    elif order_by == "y":
        axis_ok = angle >= 90 - COLLINEAR_AXIS_DEG
    holds = residual <= COLLINEAR_RESIDUAL_CM + _EPS and order_ok and axis_ok
    return holds, {
        "residual_cm": round(residual, 2),
        "order_ok": order_ok,
        "axis_ok": axis_ok,
        "order": ",".join(got),
    }


# ---------- clauses ----------
def _fail(clause: GoalClause, code: str, detail: str) -> ClauseResult:
    return ClauseResult(clause=clause, holds=False, code=code, detail=detail)


def evaluate_clause(
    clause: GoalClause, state: State, initial: State, sim: bool = False
) -> ClauseResult:
    """`state` is the final state to check; `initial` the starting state of the same layout
    (used by `swapped` and to tell a legitimately empty `all` from a missing object)."""
    objs = select(clause.select, state)
    what = describe(clause.select)
    if clause.pred == "swapped":
        names = clause.select.names or [o.name for o in objs]
        if clause.quant != "pair" or len(names) != 2:
            return _fail(clause, "INVALID_CLAUSE", "swapped needs a pair of two names")
        a, b = names
        if not all(n in state and n in initial for n in names):
            return _fail(clause, "EMPTY_SELECTION", f"{a} or {b} is not in this layout")
        d_a = math.dist((state[a].x, state[a].y), (initial[b].x, initial[b].y))
        d_b = math.dist((state[b].x, state[b].y), (initial[a].x, initial[a].y))
        holds = d_a <= SWAPPED_CM + _EPS and d_b <= SWAPPED_CM + _EPS
        detail = f"{a} is {d_a:.1f} cm and {b} {d_b:.1f} cm from each other's start"
        return ClauseResult(
            clause=clause,
            holds=holds,
            objects=names,
            measured={"a_to_b_start_cm": round(d_a, 2), "b_to_a_start_cm": round(d_b, 2)},
            detail=detail,
        )
    if not objs:
        if clause.quant == "all" and not select(clause.select, initial):
            return ClauseResult(clause=clause, holds=True, detail=f"no {what} here (vacuous)")
        return _fail(clause, "EMPTY_SELECTION", f"{what}: nothing matches")
    if clause.quant == "the" and len(objs) != 1:
        return _fail(clause, "AMBIGUOUS_SELECTION", f"{what}: {len(objs)} objects match")
    names = [o.name for o in objs]

    if clause.pred == "collinear":
        holds, measured = collinear(objs, clause.order, clause.order_by)
        return ClauseResult(
            clause=clause,
            holds=holds,
            objects=names,
            measured=measured,
            detail=f"{what} in a line: residual {measured['residual_cm']} cm",
        )

    targets: list[SceneObject] = []
    if clause.target is not None:
        targets = [t for t in select(clause.target, state) if t.name not in names]
        if not targets:
            return _fail(clause, "TARGET_MISSING", f"{describe(clause.target)} is not here")
    elif clause.pred != "near" or clause.point_cm is None:
        return _fail(clause, "INVALID_CLAUSE", f"{clause.pred} needs a target")

    failed: list[str] = []
    measured_all: dict[str, float | bool | str] = {}
    for o in objs:
        ok, one = _check_one(clause, o, targets, sim)
        if not ok:
            failed.append(o.name)
        for k, v in one.items():
            measured_all[f"{o.name}.{k}" if len(objs) > 1 else k] = v
    tname = describe(clause.target) if clause.target else str(clause.point_cm)
    rel = clause.pred.replace("_", " ")
    detail = f"{what} {rel} {tname}" if not failed else f"not {rel} {tname}: {', '.join(failed)}"
    return ClauseResult(
        clause=clause, holds=not failed, objects=names, measured=measured_all, detail=detail
    )


def _check_one(
    clause: GoalClause, o: SceneObject, targets: list[SceneObject], sim: bool
) -> tuple[bool, dict[str, float | bool]]:
    """Holds against any of the targets (a kind target means 'any container of that kind')."""
    best: tuple[bool, dict[str, float | bool]] = (False, {})
    if clause.pred == "near" and not targets:
        assert clause.point_cm is not None
        dist = math.dist((o.x, o.y), clause.point_cm)
        return dist <= NEAR_CM + _EPS, {"distance_cm": round(dist, 2)}
    for t in targets:
        if clause.pred == "inside":
            res = inside(o, t, sim)
        elif clause.pred == "near":
            gap = footprint_gap(o, t)
            res = (gap <= NEAR_CM + _EPS, {"gap_cm": round(gap, 2)})
        else:
            res = relation(o, t, clause.pred)
        if res[0]:
            return res
        if not best[1]:
            best = res
    return best


def evaluate(
    goal: Sequence[GoalClause], state: State, initial: State, sim: bool = False
) -> list[ClauseResult]:
    return [evaluate_clause(c, state, initial, sim) for c in goal]


def all_hold(results: Sequence[ClauseResult]) -> bool:
    return bool(results) and all(r.holds for r in results)


def to_state(objects: Sequence[SceneObject]) -> dict[str, SceneObject]:
    return {o.name: o for o in objects}
