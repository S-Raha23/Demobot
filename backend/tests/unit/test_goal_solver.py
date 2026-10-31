"""Goal solver (F3): deterministic outcome prediction, consistency filter, probe choice."""

from demobot import goal_solver as gs
from demobot.schemas import GoalClause, Layout, SceneObject, Selector
from demobot.sim.layouts import default_frame


def _o(name: str, x: float, y: float, kind: str = "", role: str = "moved") -> SceneObject:
    return SceneObject(name=name, kind=kind or name, role=role, x=x, y=y, w=4, d=4, h=2)  # type: ignore[arg-type]


def _layout(*objs: SceneObject) -> Layout:
    work, base = default_frame()
    return Layout(objects=list(objs), work_area=work, robot_base_cm=base, id="t")


def _clause(sel: dict, pred: str, target: dict | None = None, **kw) -> GoalClause:  # type: ignore[no-untyped-def]
    return GoalClause(quant="the", select=Selector(**sel), pred=pred,  # type: ignore[arg-type]
                      target=Selector(**target) if target else None, **kw)  # fmt: skip


BOX = _o("box", 30, 20, kind="box", role="container")
PEN = _o("pen1", 10, 10, kind="pen")
CUTTER = _o("cutter", 45, 30, kind="cutter")


def test_solve_inside_moves_to_container_centre() -> None:
    lay = _layout(BOX, PEN)
    out = gs.solve([_clause({"name": "pen1"}, "inside", {"name": "box"})], lay)
    pen = {o.name: o for o in out.objects}["pen1"]
    assert (pen.x, pen.y) == (BOX.x, BOX.y)
    assert gs.consistent([_clause({"name": "pen1"}, "inside", {"name": "box"})], out, lay)


def test_solve_relations_and_consistency() -> None:
    lay = _layout(BOX, PEN)
    for pred in ("left_of", "right_of", "in_front_of", "behind"):
        goal = [_clause({"name": "pen1"}, pred, {"name": "box"})]
        assert gs.consistent(goal, gs.solve(goal, lay), lay), pred


def test_solve_swapped_exchanges_positions() -> None:
    a, b = _o("a", 10, 10), _o("b", 40, 30)
    lay = _layout(a, b)
    goal = [GoalClause(quant="pair", select=Selector(names=["a", "b"]), pred="swapped")]
    out = {o.name: o for o in gs.solve(goal, lay).objects}
    assert (out["a"].x, out["a"].y) == (b.x, b.y)
    assert (out["b"].x, out["b"].y) == (a.x, a.y)
    assert gs.consistent(goal, gs.solve(goal, lay), lay)


def test_solve_turned_and_collinear() -> None:
    lay = _layout(PEN, CUTTER, _o("pen2", 15, 25, kind="pen"))
    turned = [GoalClause(quant="the", select=Selector(name="cutter"), pred="turned", yaw_deg=90.0,
                         point_cm=(CUTTER.x, CUTTER.y))]  # fmt: skip
    out = {o.name: o for o in gs.solve(turned, lay).objects}
    assert out["cutter"].yaw == 90.0
    assert gs.consistent(turned, gs.solve(turned, lay), lay)
    line = [GoalClause(quant="all", select=Selector(kind="pen"), pred="collinear")]
    assert gs.consistent(line, gs.solve(line, lay), lay)


def test_solve_collinear_order_by_y_makes_a_column() -> None:
    pens = [
        _o("p1", 10, 10, kind="pen"),
        _o("p2", 30, 12, kind="pen"),
        _o("p3", 12, 30, kind="pen"),
    ]
    lay = _layout(*pens)
    col = [GoalClause(quant="all", select=Selector(kind="pen"), pred="collinear", order_by="y")]
    out = {o.name: o for o in gs.solve(col, lay).objects}
    assert len({o.x for o in out.values()}) == 1  # one x: a column, not a row
    assert [o.name for o in sorted(out.values(), key=lambda o: o.y)] == ["p1", "p2", "p3"]
    assert gs.consistent(col, gs.solve(col, lay), lay)
    # and the row form is unchanged
    row = [GoalClause(quant="all", select=Selector(kind="pen"), pred="collinear", order_by="x")]
    out_r = {o.name: o for o in gs.solve(row, lay).objects}
    assert len({o.y for o in out_r.values()}) == 1
    assert gs.consistent(row, gs.solve(row, lay), lay)


def test_hypotheses_differ_and_probe_separates() -> None:
    # "pens in box" (kind) vs "this pen in box" (name): a second pen separates them
    lay = _layout(BOX, PEN, _o("pen2", 12, 30, kind="pen"))
    by_kind = [GoalClause(quant="all", select=Selector(kind="pen"), pred="inside",
                          target=Selector(name="box"))]  # fmt: skip
    by_name = [_clause({"name": "pen1"}, "inside", {"name": "box"})]
    assert gs.separating_pairs(lay, [by_kind, by_name]) == 1
    probe, pairs = gs.choose_probe([lay], [by_kind, by_name])
    assert probe is lay and pairs == 1
    # identical hypotheses never separate
    assert gs.separating_pairs(lay, [by_name, by_name]) == 0
    assert not gs.outcomes_differ(gs.solve(by_name, lay), gs.solve(by_name, lay))
