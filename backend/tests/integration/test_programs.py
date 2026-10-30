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
