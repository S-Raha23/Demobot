"""Card titles and steps, the template fallback, and the export zip (no network)."""

import io
import json
import zipfile
from pathlib import Path

import cv2
import numpy as np

from demobot import card, export
from demobot.schemas import GoalClause, Program, Selector, SkillCard, SpecObject, Step, TaskSpec


def spec(goal: list[GoalClause]) -> TaskSpec:
    return TaskSpec(summary="The person put the pens in the cup.", generalization="Every pen goes in the cup.",
                    objects=[SpecObject(name="left teal pen", kind="pen", role="moved"),
                             SpecObject(name="white cup", kind="cup", role="container")],
                    steps=[Step(action="place_in", object="left teal pen", target="white cup", t_start=1, t_end=2)],
                    goal=goal)  # fmt: skip


INSIDE = GoalClause(
    quant="all", select=Selector(kind="pen"), pred="inside", target=Selector(name="white cup")
)
LEFT = GoalClause(
    quant="the",
    select=Selector(name="left teal pen"),
    pred="left_of",
    target=Selector(name="white cup"),
)
SWAP = GoalClause(
    quant="pair", select=Selector(names=["glue bottle", "tennis ball"]), pred="swapped"
)


def test_titles_and_steps_are_short_imperatives() -> None:
    assert card.title_of(spec([INSIDE])) == "Put every pen in the white cup"
    assert card.steps_of([INSIDE]) == ["Find each pen", "Pick it up", "Drop it into the white cup"]
    assert (
        card.title_of(spec([LEFT])) == "Put the teal pen left of the white cup"
    )  # ordinals dropped
    assert card.steps_of([SWAP])[0] == "Park the glue bottle in a free spot"
    assert all(len(s.split()) <= 8 for g in ([INSIDE], [LEFT], [SWAP]) for s in card.steps_of(g))
    assert card.title_of(spec([INSIDE, LEFT])).startswith("Put each pen in the white cup;")


def test_template_card_and_export_zip(tmp_path: Path) -> None:
    run = tmp_path / "run1"
    art = run / "artifacts"
    art.mkdir(parents=True)
    cv2.imwrite(str(art / "reference_frame.jpg"), np.full((360, 640, 3), 200, np.uint8))
    s = spec([INSIDE])
    card.template(
        art / "reference_frame.jpg", card.title_of(s), card.steps_of(s.goal), art / "card.png"
    )
    assert (art / "card.png").stat().st_size > 1000
    (art / "taskspec.json").write_text(s.model_dump_json())
    (art / "programs.json").write_text(json.dumps([Program(version=2, code="def run(scene, robot):\n    pass\n",
                                                           author="wonder").model_dump()]))  # fmt: skip
    (art / "card.json").write_text(SkillCard(skill_id="run1", title="Put every pen in the white cup", description="d",
                                             goal_text="g", program_version=2, robustness=1.0, cost_to_learn_usd=1.2,
                                             run_id="run1").model_dump_json())  # fmt: skip
    z = zipfile.ZipFile(io.BytesIO(export.build_zip(run)))
    assert sorted(z.namelist()) == [
        "README.md",
        "card.png",
        "goal.json",
        "program.py",
        "skill_api.md",
        "taskspec.json",
    ]
    assert "def run(scene, robot)" in z.read("program.py").decode()
    assert "def place_next_to(" in z.read("skill_api.md").decode()
    assert json.loads(z.read("goal.json"))[0]["pred"] == "inside"
    assert "not on a physical" in z.read("README.md").decode()
    assert export.forged_skills_used("def run(scene, robot):\n    pass\n") == []


def test_export_bundles_forged_skill_source_and_notes_it(tmp_path: Path) -> None:
    run = tmp_path / "run2"
    art = run / "artifacts"
    art.mkdir(parents=True)
    s = spec([INSIDE])
    code = (
        "def run(scene, robot):\n"
        "    rotate_in_place(robot, scene, scene.get('left teal pen'), 90)\n"
    )
    (art / "taskspec.json").write_text(s.model_dump_json())
    (art / "programs.json").write_text(json.dumps([Program(version=1, code=code,
                                                           author="wonder").model_dump()]))  # fmt: skip
    (art / "card.json").write_text(SkillCard(skill_id="run2", title="t", description="d",
                                             goal_text="g", program_version=1, robustness=None,
                                             cost_to_learn_usd=0.1, run_id="run2").model_dump_json())  # fmt: skip
    assert export.forged_skills_used(code) == ["rotate_in_place"]
    # a mere mention (comment) is not a call
    assert export.forged_skills_used("def run(scene, robot):\n    pass  # rotate_in_place\n") == []
    z = zipfile.ZipFile(io.BytesIO(export.build_zip(run)))
    assert "forged/rotate_in_place.py" in z.namelist()
    assert "def rotate_in_place(" in z.read("forged/rotate_in_place.py").decode()
    readme = z.read("README.md").decode()
    assert "forged/rotate_in_place.py" in readme and "rotate_in_place" in readme
