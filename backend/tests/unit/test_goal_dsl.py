"""Goal DSL, with the edge cases ported from the first repo's predicate tests."""

from demobot import goal_dsl as g
from demobot.schemas import GoalClause, SceneObject, Selector


def o(name: str, x: float, y: float, w: float = 4, d: float = 4, h: float = 2, kind: str = "",
      role: str = "moved", z: float = 1.0, shape: str = "box") -> SceneObject:  # fmt: skip
    return SceneObject(name=name, kind=kind or name, role=role, shape=shape, x=x, y=y, z=z, w=w,
                       d=d, h=h)  # type: ignore[arg-type]  # fmt: skip


def st(*objs: SceneObject) -> dict[str, SceneObject]:
    return {x.name: x for x in objs}


def clause(**kw) -> GoalClause:  # type: ignore[no-untyped-def]
    return GoalClause(**kw)


MUG = o("mug", 30, 20, 10, 10, 10, role="container", shape="cylinder")


def inside_pens(state, sim=False):  # type: ignore[no-untyped-def]
    c = clause(quant="all", select=Selector(kind="pen"), pred="inside", target=Selector(name="mug"))
    return g.evaluate_clause(c, state, state, sim)


def test_inside_centre_and_exactly_on_shrunk_border() -> None:
    assert inside_pens(st(MUG, o("p", 30, 20, kind="pen"))).holds
    assert inside_pens(st(MUG, o("p", 34, 20, kind="pen"))).holds  # 5 − 1 = 4 cm
    r = inside_pens(st(MUG, o("p", 34.2, 20, kind="pen")))
    assert not r.holds and r.measured["margin_cm"] < 0


def test_inside_rim_check_only_in_sim() -> None:
    on_rim = st(MUG, o("p", 30, 20, kind="pen", z=12.5))
    assert inside_pens(on_rim).holds and not inside_pens(on_rim, sim=True).holds
    assert inside_pens(st(MUG, o("p", 30, 20, kind="pen", z=8)), sim=True).holds


def rel(a: SceneObject, b: SceneObject, pred: str) -> bool:
    c = clause(quant="the", select=Selector(name=a.name), pred=pred, target=Selector(name=b.name))
    return g.evaluate_clause(c, st(a, b), st(a, b)).holds


def test_relations_gap_window_and_lateral_limit() -> None:
    b = o("b", 30, 20)
    assert rel(o("a", 24, 20), b, "left_of")  # gap 2
    assert rel(o("a", 27, 20), b, "left_of")  # gap −1 (touching) passes
    assert not rel(o("a", 27.5, 20), b, "left_of")  # overlap
    assert rel(o("a", 18, 20), b, "left_of")  # gap 8 passes
    assert not rel(o("a", 17.5, 20), b, "left_of")  # too far
    assert rel(o("a", 24, 25), b, "left_of") and not rel(o("a", 24, 25.5), b, "left_of")
    assert not rel(o("a", 36, 20), b, "left_of") and rel(o("a", 36, 20), b, "right_of")
    assert rel(o("a", 30, 14), b, "behind") and rel(o("a", 30, 26), b, "in_front_of")


def test_near_point_and_target() -> None:
    c = clause(quant="the", select=Selector(name="a"), pred="near", point_cm=(10, 10))
    assert g.evaluate_clause(c, st(o("a", 13, 12)), {}).holds
    assert not g.evaluate_clause(c, st(o("a", 15, 10)), {}).holds


def line(pred_kw: dict, *objs: SceneObject) -> bool:
    c = clause(quant="all", select=Selector(role="moved"), pred="collinear", **pred_kw)
    return g.evaluate_clause(c, st(*objs), st(*objs)).holds


def test_collinear_order_reverse_residual_and_axis() -> None:
    a, b, c = o("a", 10, 20), o("b", 20, 21), o("c", 30, 20)
    assert line({"order": ["a", "b", "c"]}, a, b, c)
    assert line({"order": ["c", "b", "a"]}, a, b, c)  # reverse passes
    assert not line({"order": ["b", "a", "c"]}, a, b, c)
    assert not line({}, a, o("b", 20, 24), c)  # residual > 2 cm
    assert line({}, o("a", 10, 10), o("b", 25, 30))  # 2 objects always pass
    assert line({"order_by": "x"}, a, b, c) and not line({"order_by": "y"}, a, b, c)
    assert line({"order_by": "y"}, o("a", 20, 5), o("b", 21, 15), o("c", 20, 25))


def swap_clause() -> GoalClause:
    return clause(quant="pair", select=Selector(names=["a", "b"]), pred="swapped")


def test_swapped_uses_the_initial_state_and_rejects_one_sided() -> None:
    init = st(o("a", 10, 10), o("b", 30, 20))
    assert g.evaluate_clause(swap_clause(), st(o("a", 31, 21), o("b", 11, 9)), init).holds
    assert not g.evaluate_clause(swap_clause(), st(o("a", 31, 21), o("b", 30, 20)), init).holds


def test_empty_selection_rules() -> None:
    state = st(MUG, o("eraser", 10, 10))
    r = inside_pens(state)
    assert r.holds and "vacuous" in r.detail  # no pens at all: legitimately empty
    c = clause(quant="the", select=Selector(name="pen"), pred="inside", target=Selector(name="mug"))
    assert g.evaluate_clause(c, state, state).code == "EMPTY_SELECTION"
    gone = g.evaluate_clause(
        clause(quant="all", select=Selector(kind="pen"), pred="inside", target=Selector(name="mug")),
        state, st(MUG, o("p", 1, 1, kind="pen")),
    )  # fmt: skip
    assert not gone.holds and gone.code == "EMPTY_SELECTION"


def test_kind_target_means_any_container_of_that_kind() -> None:
    m2 = o("mug2", 50, 20, 10, 10, 10, kind="mug", role="container")
    state = st(MUG, m2, o("p", 50, 20, kind="pen"))
    c = clause(quant="all", select=Selector(kind="pen"), pred="inside", target=Selector(kind="mug"))
    assert g.evaluate_clause(c, state, state).holds


def test_rotated_footprint_extents() -> None:
    pen = o("pen", 0, 0, w=14, d=1.2)
    assert pen.extents() == (7, 0.6)
    ex, ey = pen.model_copy(update={"yaw": 90}).extents()
    assert abs(ex - 0.6) < 1e-9 and abs(ey - 7) < 1e-9
