"""Export a learned skill as a robot-agnostic zip (docs/04 §14): the program, the skill API contract
any robot stack can implement, the goal, the task spec, the card and a README."""

import io
import json
import zipfile
from pathlib import Path

from demobot.program.synth import api_reference
from demobot.schemas import Program, SkillCard, TaskSpec

SKILL_API_MD = """# DemoBot skill API

A DemoBot program is plain Python defining `run(scene, robot)`. To run it on any robot, implement
the objects below on top of your perception and motion stack. Units are centimetres in the table
frame: the origin is the centre of marker 0, +x points to marker 1 (right), +y points to marker 3
(towards the robot); z is up from the table; angles are degrees.

- `scene` reads the live state of the table (from your perception), so positions are current
  after every move.
- `robot` needs six primitives: `pick`, `place_at`, `place_in`, `place_next_to`, `move` (pick then
  place_at) and `home`, plus `can_reach`. Every place lets go of the held object.
- Errors are exceptions with clear messages; programs must not catch them.

{api}

## Goal

`goal.json` states what must be true at the end, in the goal DSL (quantifier, selector,
predicate, target). Use it to check the result on your robot.
"""

README = """# {title}

{description}

Learned by DemoBot from one phone video ({run_id}), program version {version}{robust}.

- `program.py`: the robot program (`run(scene, robot)`).
- `skill_api.md`: the API the program needs; implement it on your robot.
- `goal.json`: what must be true at the end (goal DSL).
- `taskspec.json`: what the demo showed (objects, steps, goal, generalisation).
- `card.png`: the skill card.

The program was verified in simulation (a simulated Franka Panda in PyBullet), not on a physical
robot.
"""


def skill_api_md() -> str:
    return SKILL_API_MD.replace("{api}", api_reference())


def build_zip(run_dir: Path) -> bytes:
    art = run_dir / "artifacts"
    card = SkillCard.model_validate_json((art / "card.json").read_text())
    spec = TaskSpec.model_validate_json((art / "taskspec.json").read_text())
    programs = [Program.model_validate(p) for p in json.loads((art / "programs.json").read_text())]
    prog = next((p for p in programs if p.version == card.program_version), programs[-1])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "program.py",
            f'"""{card.title}: learned by DemoBot (program v{prog.version})."""\n\n' + prog.code,
        )
        z.writestr("skill_api.md", skill_api_md())
        z.writestr(
            "goal.json", json.dumps([c.model_dump(exclude_none=True) for c in spec.goal], indent=1)
        )
        z.writestr("taskspec.json", spec.model_dump_json(indent=1))
        if (art / "card.png").exists():
            z.write(art / "card.png", "card.png")
        robust = (
            f", robustness {card.robustness:.0%} on red-team layouts"
            if card.robustness is not None
            else ""
        )
        z.writestr("README.md", README.format(title=card.title, description=card.description, run_id=card.run_id,
                                              version=prog.version, robust=robust))  # fmt: skip
    return buf.getvalue()
