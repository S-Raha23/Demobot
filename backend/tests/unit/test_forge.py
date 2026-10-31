"""Skill Forge regressions: coder-triggered forges must name their target (so test layouts are
sparse), and push test layouts must offer a clear push corridor (F1)."""

from demobot.program import forge
from demobot.program.synth import TOOLS
from demobot.schemas import Layout, SceneObject
from demobot.sim.layouts import default_frame


def _layout(*objs: SceneObject) -> Layout:
    work, base = default_frame()
    return Layout(objects=list(objs), work_area=work, robot_base_cm=base, id="t")


def _o(name: str, x: float, y: float, w: float = 4, d: float = 4) -> SceneObject:
    return SceneObject(name=name, kind=name, x=x, y=y, w=w, d=d, h=2)


def test_request_new_skill_schema_threads_target() -> None:
    tool = next(t for t in TOOLS if t["name"] == "request_new_skill")
    assert "target" in tool["parameters"]["properties"]
    req = forge.ForgeRequest(name="push", signature="push(robot, scene, obj, dx_cm, dy_cm)",
                             purpose="slide", evidence="TooWide", target="white tub")  # fmt: skip
    assert req.target == "white tub"


def test_sparse_keeps_target_plus_two_smallest() -> None:
    base = _layout(_o("white tub", 30, 20, 14, 14), _o("big", 10, 10, 10, 10),
                   _o("s1", 45, 10, 2, 2), _o("s2", 45, 30, 3, 3))  # fmt: skip
    out = forge.sparse(base, "white tub")
    assert [o.name for o in out.objects] == ["white tub", "s1", "s2"]
    assert forge.sparse(base, "") is base


def test_push_corridor_blocked_and_clear_directions() -> None:
    # blocker 6 cm behind the tub on +x: pushing +x is blocked, -x is clear
    lay = _layout(_o("white tub", 30, 20, 10, 10), _o("block", 38, 20, 4, 4))
    assert not forge.push_corridor_clear(lay, "white tub", (1.0, 0.0), 8.0)
    assert forge.push_corridor_clear(lay, "white tub", (-1.0, 0.0), 8.0)
    assert forge.layout_has_push_corridor(lay, "white tub")
    # boxed in on all four sides: no feasible push at all
    boxed = _layout(_o("white tub", 30, 20, 10, 10), _o("e", 38, 20), _o("w", 22, 20),
                    _o("n", 30, 28), _o("s", 30, 12))  # fmt: skip
    assert not forge.layout_has_push_corridor(boxed, "white tub")


def test_push_corridor_rejects_bad_inputs() -> None:
    lay = _layout(_o("white tub", 30, 20, 10, 10))
    assert not forge.push_corridor_clear(lay, "missing", (1.0, 0.0), 8.0)
    assert not forge.push_corridor_clear(lay, "white tub", (2.0, 0.0), 8.0)  # not a unit vector
    assert not forge.push_corridor_clear(lay, "white tub", (1.0, 0.0), 60.0)  # leaves the table
    assert forge.push_corridor_clear(lay, "white tub", (0.0, 1.0), 6.0)
