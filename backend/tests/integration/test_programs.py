"""M2 acceptance: 20 hand-written programs (4 per task family) pass on 3 random layouts each."""

import pytest

from demobot.program.sandbox import execute, guard
from demobot.sim.layouts import random_layout, validate

from .programs import FAMILIES, PROGRAMS

SEEDS = (1, 2, 3)


@pytest.mark.parametrize(("family", "index"), PROGRAMS, ids=[f"{f}-{i}" for f, i in PROGRAMS])
def test_program_passes_on_random_layouts(family: str, index: int) -> None:
    base, goal, programs = FAMILIES[family]
    for seed in SEEDS:
        layout = random_layout(base, seed)
        assert not validate(layout)
        res = execute(programs[index], layout, goal)
        failed = [r.detail for r in res.goal_results if not r.holds]
        assert res.goal_ok, f"seed {seed}: {res.error_type} {res.error} {failed}"
        assert res.skill_calls and all(c.ok for c in res.skill_calls)


def test_twenty_programs_across_five_families() -> None:
    assert len(PROGRAMS) == 20 and len(FAMILIES) == 5
    for family, index in PROGRAMS:
        guard(FAMILIES[family][2][index])  # every valid program passes the guard


def test_the_humans_real_objects_sort_into_box_and_mug() -> None:
    """The human's objects: pens upright in the mug; cutter and spoon diagonally in the square
    box, the glue bottle in a corner (synth/objects.py)."""
    from demobot.schemas import GoalClause, Layout, SceneObject, Selector
    from demobot.sim.layouts import default_frame
    from synth.objects import CATALOGUE

    work, base = default_frame()

    def mk(kind: str, name: str, role: str) -> SceneObject:
        it = CATALOGUE[kind]
        return SceneObject(name=name, kind=kind, role=role, shape=it.shape, x=0, y=0, w=it.w,  # type: ignore[arg-type]
                           d=it.d, h=it.h, color=it.colors[0][1])  # fmt: skip

    objs = [mk("mug", "white mug", "container"), mk("box", "white box", "container"),
            mk("pen", "teal pen", "moved"), mk("pen", "teal pen 2", "moved"),
            mk("box cutter", "teal box cutter", "moved"), mk("spoon", "steel spoon", "moved"),
            mk("glue bottle", "white glue bottle", "moved")]  # fmt: skip
    layout = Layout(objects=objs, work_area=work, robot_base_cm=base)
    goal = [
        GoalClause(
            quant="all",
            select=Selector(kind="pen"),
            pred="inside",
            target=Selector(name="white mug"),
        ),
        GoalClause(
            quant="all",
            select=Selector(role="moved"),
            pred="inside",
            target=Selector(role="container"),
        ),
    ]
    code = """
def run(scene, robot):
    mug, box = scene.get("white mug"), scene.get("white box")
    for item in scene.with_role("moved"):
        robot.pick(item)
        robot.place_in(mug if item.kind == "pen" else box)
"""
    for seed in SEEDS:
        res = execute(code, random_layout(layout, seed), goal)
        assert res.goal_ok, (
            f"seed {seed}: {res.error} {[r.detail for r in res.goal_results if not r.holds]}"
        )
