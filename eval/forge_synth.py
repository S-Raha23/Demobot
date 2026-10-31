"""F1 acceptance on synthetic layouts (docs/11): DemoBot forges `push` and `rotate_in_place`, each
>= 9/10 on fresh seeds with the regression gate green. Writes eval/forge_results.json.

    uv run python -m eval.forge_synth [push] [rotate_in_place]
"""

import asyncio
import json
import sys

from demobot.config import ROOT, settings
from demobot.events import EventLog, RunContext
from demobot.program import forge
from demobot.schemas import Layout, SceneObject
from demobot.sim.layouts import default_frame

REQUESTS = {
    "push": forge.ForgeRequest(
        name="push", signature="push(robot, scene, obj, dx_cm, dy_cm)",
        purpose="Slide an object along the table by (dx_cm, dy_cm) without lifting it, for objects too wide to pick.",
        evidence="robot.pick(white tub) raised TooWide: the tub is 14.0 cm wide and the gripper opens 8 cm; the demo slid it ~12 cm to the right.",
        target="white tub"),
    "rotate_in_place": forge.ForgeRequest(
        name="rotate_in_place", signature="rotate_in_place(robot, scene, obj, dyaw_deg)",
        purpose="Turn an object by dyaw_deg degrees where it lies (it ends within 2 cm of where it was).",
        evidence="the goal needs the teal box cutter turned 90 degrees in place; pick/place_at keep the orientation unless yaw is given, "
                 "and no primitive turns an object without moving it.",
        target="teal box cutter"),
}  # fmt: skip


def base_layout() -> Layout:
    work, base = default_frame()
    objs = [
        SceneObject(name="white tub", kind="tub", role="container", shape="box", x=22, y=20, w=14, d=14, h=9, color="#eeeeee", hollow=True),
        SceneObject(name="teal box cutter", kind="box cutter", role="moved", shape="box", x=42, y=14, w=13, d=2.2, h=1.2, color="#2aa7a0"),
        SceneObject(name="teal pen", kind="pen", role="distractor", shape="box", x=8, y=30, w=14, d=1.2, h=1.2, color="#2aa7a0", yaw=90),
        SceneObject(name="tennis ball", kind="tennis ball", role="distractor", shape="sphere", x=46, y=30, w=6.6, d=6.6, h=6.6, color="#cddc39"),
    ]  # fmt: skip
    return Layout(objects=objs, work_area=work, robot_base_cm=base, id="forge-base")


async def main(names: list[str]) -> None:
    out_path = ROOT / "eval" / "forge_results.json"
    results = json.loads(out_path.read_text()) if out_path.exists() else {}
    art = settings.data_path / "runs" / "forge-synth" / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    for name in names:
        ctx = RunContext(
            "forge-synth", "dev", EventLog(art.parent / "events.jsonl", "forge-synth"), "forge"
        )
        out = await forge.forge(ctx, REQUESTS[name], base_layout(), art, "forge-synth")
        results[name] = {"promoted": out.promoted, "pass_rate": out.pass_rate, "regression": out.regression, "turns": out.turns,
                         "reason": out.reason, "skill_api_version": forge.skill_api_version()}  # fmt: skip
        print(name, results[name])
        out_path.write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or list(REQUESTS)))
