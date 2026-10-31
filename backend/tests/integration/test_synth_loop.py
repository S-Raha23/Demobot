"""The coder loop with a scripted Wonder (no network): real simulations, submit rules, versions."""

import json
from pathlib import Path
from typing import Any

import pytest

from demobot import gateway
from demobot.events import EventLog, RunContext, read_events
from demobot.program import synth
from demobot.schemas import GroundedDemo, TaskSpec, Transcript
from demobot.sim.layouts import random_layout

from .programs import FAMILIES

BUGGY = "def run(scene, robot):\n    box = scene.containers()[0]\n    for p in scene.with_role('moved'):\n        robot.pick(p)\n        robot.place_in(box)\n    robot.place_in(box)\n"
GOOD = "def run(scene, robot):\n    box = scene.containers()[0]\n    for p in scene.of_kind('pen'):\n        robot.pick(p)\n        robot.place_in(box)\n"


def fc(name: str, args: dict[str, Any], i: int) -> dict[str, Any]:
    return {
        "type": "function_call",
        "call_id": f"c{i}",
        "name": name,
        "arguments": json.dumps(args),
    }


def scripted(turns: list[list[dict[str, Any]]]):  # type: ignore[no-untyped-def]
    calls = iter(turns)
    seen: list[str] = []

    async def fake(**kw: Any) -> Any:
        seen.append(kw["purpose"])
        return {"output": next(calls)}

    return fake, seen


@pytest.fixture
def si(tmp_path: Path) -> synth.SynthInput:
    base, goal, _ = FAMILIES["place_in"]
    layout = random_layout(base, 1, "demo")
    spec = TaskSpec(summary="pens into the mug", objects=[], steps=[], goal=goal, generalization="")
    gd = GroundedDemo(
        initial=layout.objects, final=layout.objects, segments=[], contacts=[], matches=[]
    )
    img = tmp_path / "kf.jpg"
    import cv2
    import numpy as np

    cv2.imwrite(str(img), np.zeros((40, 60, 3), np.uint8))
    return synth.SynthInput(spec=spec, grounded=gd, layouts={"demo": layout}, transcript=Transcript(text=""),
                            keyframes=[(0.0, img)], calibration_json=None, art=tmp_path / "artifacts", drafts=False)  # fmt: skip


async def test_debugs_then_submits(si: synth.SynthInput, tmp_path: Path, monkeypatch) -> None:
    fake, seen = scripted([
        [fc("simulate", {"code": BUGGY, "layout": "demo", "render": False}, 1)],
        [fc("submit", {"code": BUGGY, "explanation": "x"}, 2)],  # refused: it failed
        [fc("simulate", {"code": GOOD, "layout": "demo", "render": True}, 3)],
        [fc("submit", {"code": GOOD, "explanation": "every pen into the mug"}, 4)],
    ])  # fmt: skip
    monkeypatch.setattr(gateway, "cached_call", fake)
    ctx = RunContext("r", "dev", EventLog(tmp_path / "events.jsonl", "r"), "program")
    out = await synth.synthesize(ctx, si)
    assert out.submitted and out.program is not None and out.program.version == 2
    assert out.program.explanation == "every pen into the mug" and out.program.passed_demo
    assert [p.passed_demo for p in out.versions] == [False, True]
    assert "-    for p in scene.with_role('moved'):" in out.versions[1].diff_from_parent
    assert (si.art / "programs" / "v2.py").read_text() == GOOD
    assert (si.art / "sim" / "demo_v2" / "result.json").exists()
    assert seen == ["synth:turn1", "synth:turn2", "synth:turn3", "synth:turn4"]
    events = list(read_events(tmp_path / "events.jsonl"))
    tools = [e.payload["tool"] for e in events if e.type == "tool_call"]
    assert tools == ["simulate", "submit", "simulate", "submit"]
    subs = [
        e.payload["result"]["ok"]
        for e in events
        if e.type == "tool_call" and e.payload["tool"] == "submit"
    ]
    assert subs == [False, True]
    assert sum(e.type == "artifact" and e.payload["kind"] == "code" for e in events) == 2


async def test_falls_back_to_the_best_passing_version(
    si: synth.SynthInput, tmp_path: Path, monkeypatch
) -> None:
    turns = [[fc("simulate", {"code": GOOD, "layout": "demo", "render": False}, 1)]]
    turns += [[{"type": "message", "content": [{"type": "output_text", "text": "thinking"}]}]] * (
        synth.MAX_TURNS - 1
    )
    fake, _ = scripted(turns)
    monkeypatch.setattr(gateway, "cached_call", fake)
    out = await synth.synthesize(RunContext("r", "dev", EventLog(tmp_path / "e.jsonl", "r")), si)
    assert (
        not out.submitted
        and out.program is not None
        and out.program.version == 1
        and out.turns == synth.MAX_TURNS
    )


def test_api_reference_lists_the_contract() -> None:
    ref = synth.api_reference()
    for needle in (
        "def free_spot(",
        "def place_next_to(",
        "def pick(",
        "NotReachable",
        "class Obj",
    ):
        assert needle in ref
    text, _ = synth.system_prompt()
    assert "{api}" not in text and "{examples}" not in text and "place_in" in text


async def test_correction_mode_updates_the_goal_first(
    si: synth.SynthInput, tmp_path: Path, monkeypatch
) -> None:
    """A correction changes the goal: pens into the mug becomes "the blue pen right of the mug"."""
    si.mode, si.start_code = "correct", GOOD
    new_goal = [
        {
            "quant": "the",
            "select": {"name": "blue pen"},
            "pred": "right_of",
            "target": {"name": "white mug"},
        }
    ]
    code = ("def run(scene, robot):\n    mug = scene.get('white mug')\n    robot.pick(scene.get('blue pen'))\n"
            "    robot.place_next_to(mug, 'right_of', gap=2)\n")  # fmt: skip
    fake, _ = scripted([
        [fc("simulate", {"code": GOOD, "layout": "demo", "render": False}, 1)],
        [fc("update_goal", {"goal": new_goal, "gloss": "the blue pen goes right of the mug"}, 2)],
        [fc("submit", {"code": GOOD, "explanation": "x"}, 3)],  # refused: not simulated against the new goal
        [fc("simulate", {"code": code, "layout": "demo", "render": False}, 4)],
        [fc("submit", {"code": code, "explanation": "moved the blue pen"}, 5)],
    ])  # fmt: skip
    monkeypatch.setattr(gateway, "cached_call", fake)
    si.spec = si.spec.model_copy(update={"objects": [
        __import__("demobot.schemas", fromlist=["SpecObject"]).SpecObject(name=o.name, kind=o.kind, role=o.role)
        for o in si.layouts["demo"].objects]})  # fmt: skip
    out = await synth.synthesize(RunContext("r", "dev", EventLog(tmp_path / "e.jsonl", "r")), si)
    assert out.submitted and out.program is not None and out.program.code == code
    assert (
        out.goal is not None and out.goal[0].pred == "right_of" and "right of the mug" in out.gloss
    )
    events = list(read_events(tmp_path / "e.jsonl"))
    assert any(e.type == "artifact" and e.payload.get("name") == "goal_diff" for e in events)
