"""M7 acceptance: inject 5 faults into a verified run and check the failure class of each.

uv run python -m eval.fault_injection syn7-01_next_to
"""

import asyncio
import json
import sys
from typing import Any

from demobot import goal_dsl, pipeline
from demobot.program import sandbox
from demobot.schemas import Calibration, GroundedDemo, TaskSpec
from demobot.sim.layouts import repair
from demobot.verify import verify

OPPOSITE = {
    "left_of": "right_of",
    "right_of": "left_of",
    "in_front_of": "behind",
    "behind": "in_front_of",
}


async def check(run: pipeline.Run, name: str, spec: TaskSpec, gd: GroundedDemo, code: str,
                expected: str | None, fake_success: bool = False) -> dict[str, Any]:  # fmt: skip
    cal = run.read("calibration.json", Calibration)
    layout = pipeline.textured(run, repair(pipeline.demo_layout(run))[0])
    sim = await sandbox.simulate(
        code, layout, spec.goal, render=True, calibration_json=cal.model_dump_json()
    )
    sim = pipeline.keep_sim(run, sim, f"fault-{name}", 0)
    if fake_success:  # a simulator that misreports: the state claims success, the render does not
        good = await sandbox.simulate(pipeline.latest_program(run).code, layout, spec.goal)
        sim = sim.model_copy(update={"final_state": good.final_state, "goal_results": good.goal_results,
                                     "goal_ok": good.goal_ok, "ok": True, "error": None})  # fmt: skip
    gd2 = gd.model_copy(update={"real_world": goal_dsl.evaluate(spec.goal, goal_dsl.to_state(gd.final),
                                                                 goal_dsl.to_state(gd.initial))})  # fmt: skip
    ver, _ = await verify(run.ctx, run.dir, spec, gd2, layout, sim, cal, pipeline.phrases(run), 0)
    got = ver.failure_class
    ok = got == expected or (
        name == "sim_only_offset" and got in ("perception_gap", "judge_dissent")
    )
    return {"fault": name, "expected": expected, "got": got, "correct": ok,
            "checks": [ver.symbolic.ok, ver.real_world.ok, ver.perceptual.ok,
                       None if ver.judge is None else ver.judge.same_goal_achieved]}  # fmt: skip


async def main() -> None:
    run = pipeline.open_run(sys.argv[1] if len(sys.argv) > 1 else "syn7-01_next_to")
    spec = run.read("taskspec.json", TaskSpec)
    gd = run.read("grounded.json", GroundedDemo)
    good = pipeline.latest_program(run).code
    step = spec.steps[-1]
    rel = step.relation or "right_of"
    moved = step.object
    distractor = next(o.name for o in spec.objects if o.role == "distractor")
    rows = []
    # 1. wrong target: the program puts it on the other side
    rows.append(
        await check(
            run,
            "wrong_target",
            spec,
            gd,
            good.replace(f'"{rel}"', f'"{OPPOSITE[rel]}"'),
            "program_bug",
        )
    )
    # 2. wrong relation: the spec says the opposite side
    bad_rel = spec.model_copy(deep=True)
    for c in bad_rel.goal:
        if c.pred in OPPOSITE:
            c.pred = OPPOSITE[c.pred]  # type: ignore[assignment]
    rows.append(
        await check(
            run,
            "wrong_relation",
            bad_rel,
            gd,
            good.replace(f'"{rel}"', f'"{OPPOSITE[rel]}"'),
            "spec_mismatch",
        )
    )
    # 3. missing step: the program does nothing
    rows.append(
        await check(
            run,
            "missing_step",
            spec,
            gd,
            "def run(scene, robot):\n    robot.home()\n",
            "program_bug",
        )
    )
    # 4. wrong object: the goal is about the distractor
    bad_obj = spec.model_copy(deep=True)
    for c in bad_obj.goal:
        if c.select.name == moved:
            c.select.name = distractor
    rows.append(await check(run, "wrong_object", bad_obj, gd, good, "spec_mismatch"))
    # 5. sim-only offset: the simulator reports success, but what it renders is elsewhere
    far = (f'def run(scene, robot):\n    o = scene.get("{moved}")\n'
           "    robot.move(o, *scene.free_spot(near=None))\n")  # fmt: skip
    rows.append(
        await check(run, "sim_only_offset", spec, gd, far, "perception_gap", fake_success=True)
    )
    for r in rows:
        print(json.dumps(r))
    ok = sum(r["correct"] for r in rows)
    print(f"\ncorrect failure class on {ok}/{len(rows)} injected faults", file=sys.stderr)
    (run.art / "fault_injection.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
