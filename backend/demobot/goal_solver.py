"""Goal solver (docs/11 F3, no LLM): a deterministic planner that predicts how any goal-DSL
goal would be achieved on any layout, cheaply (pure geometry, no simulation).

It doubles as the F3 hypothesis filter's outcome predictor: a hypothesis is kept only if it
holds on the human's real final state, and a probe layout is useful only if different
hypotheses predict different final states on it. The robot program itself is still written
by the coder; this module never runs the robot.
"""

import math

from demobot import goal_dsl as g
from demobot.schemas import GoalClause, Layout, SceneObject

GAP_CM = 2.0  # relation gap inside the DSL window (-1..8 cm)


def _moved(o: SceneObject, x: float, y: float, yaw: float | None = None) -> SceneObject:
    return o.model_copy(update={"x": round(x, 2), "y": round(y, 2),
                                **({} if yaw is None else {"yaw": round(yaw % 360, 1)})})  # fmt: skip


def _relation_spot(o: SceneObject, t: SceneObject, pred: str) -> tuple[float, float]:
    (aw, ad), (bw, bd) = o.extents(), t.extents()
    if pred == "left_of":
        return t.x - bw - GAP_CM - aw, t.y
    if pred == "right_of":
        return t.x + bw + GAP_CM + aw, t.y
    if pred == "behind":  # -y (see goal_dsl.relation)
        return t.x, t.y - bd - GAP_CM - ad
    return t.x, t.y + bd + GAP_CM + ad  # in_front_of, +y


def solve(goal: list[GoalClause], layout: Layout) -> Layout:
    """The predicted final layout if `goal` is achieved on `layout` (objects not selected by
    any clause stay put; later clauses see earlier clauses' moves)."""
    state: dict[str, SceneObject] = {o.name: o for o in layout.objects}
    initial = dict(state)
    for clause in goal:
        objs = g.select(clause.select, state)
        if clause.pred == "swapped":
            names = clause.select.names or [o.name for o in objs]
            if len(names) == 2 and all(n in state for n in names):
                a, b = state[names[0]], state[names[1]]
                state[a.name] = _moved(a, initial[b.name].x, initial[b.name].y)
                state[b.name] = _moved(b, initial[a.name].x, initial[a.name].y)
            continue
        if clause.pred == "collinear" and objs:
            objs = sorted(objs, key=lambda o: o.name)
            order = [state[n] for n in clause.order] if clause.order else objs
            if clause.order_by == "y":  # a front-to-back column, not a row
                cx = sum(o.x for o in objs) / len(objs)
                total = sum(o.extents()[1] * 2 + GAP_CM for o in order) - GAP_CM
                y = sum(o.y for o in objs) / len(objs) - total / 2
                for o in order:
                    _, ey = o.extents()
                    y += ey
                    state[o.name] = _moved(o, cx, y)
                    y += ey + GAP_CM
            else:  # a left-to-right row (order_by "x" or unset)
                cy = sum(o.y for o in objs) / len(objs)
                total = sum(max(o.extents()) * 2 + GAP_CM for o in order) - GAP_CM
                x = sum(o.x for o in objs) / len(objs) - total / 2
                for o in order:
                    ex, _ = o.extents()
                    x += ex
                    state[o.name] = _moved(o, x, cy)
                    x += ex + GAP_CM
            continue
        targets = g.select(clause.target, state) if clause.target else []
        targets = [t for t in targets if t.name not in {o.name for o in objs}]
        for o in objs:
            if clause.pred == "turned":
                yaw = clause.yaw_deg if clause.yaw_deg is not None else o.yaw
                x, y = clause.point_cm if clause.point_cm else (o.x, o.y)
                state[o.name] = _moved(o, x, y, yaw)
            elif clause.pred == "inside" and targets:
                state[o.name] = _moved(o, targets[0].x, targets[0].y)
            elif clause.pred in g.RELATIONS and targets:
                x, y = _relation_spot(state[o.name], targets[0], clause.pred)
                state[o.name] = _moved(state[o.name], x, y)
            elif clause.pred == "near":
                if targets:
                    x, y = _relation_spot(state[o.name], targets[0], "right_of")
                    state[o.name] = _moved(state[o.name], x, y)
                elif clause.point_cm:
                    state[o.name] = _moved(o, clause.point_cm[0], clause.point_cm[1])
    return layout.model_copy(update={"objects": [state[o.name] for o in layout.objects]})


def consistent(goal: list[GoalClause], final: Layout, initial: Layout) -> bool:
    """Whether `goal` holds on `final` (the F3 keep-filter for hypotheses)."""
    return g.all_hold(g.evaluate(goal, g.to_state(final.objects), g.to_state(initial.objects)))


def outcomes_differ(a: Layout, b: Layout, pos_cm: float = 1.0, yaw_deg: float = 10.0) -> bool:
    """Whether two predicted outcomes differ materially (position or yaw of any object)."""
    other = {o.name: o for o in b.objects}
    for o in a.objects:
        t = other.get(o.name)
        if t is None or math.dist((o.x, o.y), (t.x, t.y)) > pos_cm:
            return True
        if abs(((o.yaw - t.yaw + 180) % 360) - 180) > yaw_deg:
            return True
    return False


def choose_probe(
    candidates: list[Layout], hypotheses: list[list[GoalClause]]
) -> tuple[Layout, int]:
    """The candidate layout separating the most hypothesis pairs (information-gain proxy);
    ties break toward the earliest candidate (simplest first). Returns (layout, pairs)."""
    best: tuple[Layout, int] | None = None
    for lay in candidates:
        outs = [solve(h, lay) for h in hypotheses]
        pairs = sum(1 for i in range(len(outs)) for j in range(i + 1, len(outs))
                    if outcomes_differ(outs[i], outs[j]))  # fmt: skip
        if best is None or pairs > best[1]:
            best = (lay, pairs)
    assert best is not None  # candidates is non-empty by contract
    return best


def separating_pairs(layout: Layout, hypotheses: list[list[GoalClause]]) -> int:
    outs = [solve(h, layout) for h in hypotheses]
    return sum(1 for i in range(len(outs)) for j in range(i + 1, len(outs))
               if outcomes_differ(outs[i], outs[j]))  # fmt: skip
