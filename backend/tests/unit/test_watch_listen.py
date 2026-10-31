"""Watch and Listen logic on recorded model outputs (no network)."""

import json
from pathlib import Path
from typing import Any

import pytest

from demobot import listen, watch
from demobot.events import EventLog, RunContext, read_events
from demobot.schemas import IngestInfo, TaskSpec, Transcript

SPECS = Path(__file__).parents[1] / "fixtures" / "specs"


def spec(name: str) -> TaskSpec:
    return TaskSpec.model_validate_json((SPECS / f"{name}.json").read_text())


def test_recorded_specs_pass_the_semantic_checks() -> None:
    for name in ("place_in_a", "place_in_b", "swap"):
        assert watch.check_spec(spec(name), 20.0) == []


def test_semantic_checks_catch_each_problem() -> None:
    s = spec("place_in_a")
    bad = s.model_copy(deep=True)
    bad.objects.append(bad.objects[0])
    bad.steps[0].target = "ghost box"
    bad.steps[1].t_start, bad.steps[1].t_end = 30.0, 31.0
    bad.goal[0].select.kind = "spaceship"
    problems = " | ".join(watch.check_spec(bad, 12.0))
    for needle in ("not unique", "'ghost box' is not in objects", "outside the 12.0 s video",
                   "no object of kind 'spaceship'"):  # fmt: skip
        assert needle in problems
    wrong_role = s.model_copy(deep=True)
    for o in wrong_role.objects:
        if o.role == "container":
            o.role = "reference"
    assert any("must have role container" in p for p in watch.check_spec(wrong_role, 20.0))


def test_compare_aligns_renamed_objects_through_steps() -> None:
    a, b = spec("place_in_a"), spec("place_in_b")
    renamed = b.model_copy(deep=True)
    for o in renamed.objects:  # the other model called them sticks
        o.name = o.name.replace("pen", "stick").replace("cup", "mug")
        o.kind = o.kind.replace("pen", "stick")
    names = {o.name for o in renamed.objects}
    for s in renamed.steps:
        s.object = s.object.replace("pen", "stick")
        s.target = s.target.replace("cup", "mug") if s.target else None
    assert all(s.object in names for s in renamed.steps)
    agreement, diffs = watch.compare(a, renamed)
    assert agreement == 1.0 and any("named differently" in d for d in diffs)


def test_compare_detects_a_different_task() -> None:
    a = spec("place_in_a")
    b = a.model_copy(deep=True)
    b.steps = b.steps[:1]
    agreement, diffs = watch.compare(a, b)
    assert agreement == 0.5 and any(d.startswith("only A") for d in diffs)


@pytest.fixture
def ctx(tmp_path: Path) -> RunContext:
    return RunContext("r", "dev", EventLog(tmp_path / "events.jsonl", "r"), "watch")


INFO = IngestInfo(source_name="c", width=1280, height=720, raw_duration_s=20, trim_start_s=0, trim_end_s=20,
                  duration_s=20, analysis_fps=10, analysis_frames=200, has_audio=False, keyframes=[],
                  keyframe_times=[])  # fmt: skip


async def test_disagreement_goes_to_the_arbiter_as_a_visible_decision(ctx, monkeypatch) -> None:
    a = spec("place_in_a")
    b = a.model_copy(deep=True)
    b.steps = b.steps[:1]

    async def fake_a(*_: Any) -> tuple[TaskSpec, str]:
        return a, "Muse Spark 1.3 (video)"

    async def fake_b(*_: Any) -> TaskSpec:
        return b

    async def fake_arb(*_: Any) -> watch.Arbitration:
        return watch.Arbitration(
            spec=a, reason="Both pens are seen going into the cup in the keyframes."
        )

    monkeypatch.setattr(watch, "spark_watch", fake_a)
    monkeypatch.setattr(watch, "cross_watch", fake_b)
    monkeypatch.setattr(watch, "arbitrate", fake_arb)
    final, record = await watch.watch(ctx, Path("."), INFO, Transcript(text=""))
    assert final == a and record["agreement"] == 0.5 and record["arbitration"]["used"]
    assert ctx.events is not None
    events = list(read_events(ctx.events.path))
    dec = [e for e in events if e.type == "decision"]
    assert (
        len(dec) == 1
        and dec[0].payload["agent"] == "arbiter"
        and "keyframes" in dec[0].payload["reasoning_summary"]
    )
    assert any(e.type == "metric" and e.payload["name"] == "crosswatch_agreement" for e in events)


async def test_missing_cross_watch_keeps_the_primary_spec(ctx, monkeypatch) -> None:
    a = spec("swap")

    async def fake_a(*_: Any) -> tuple[TaskSpec, str]:
        return a, "Muse Spark 1.3 (video)"

    async def none(*_: Any) -> None:
        return None

    monkeypatch.setattr(watch, "spark_watch", fake_a)
    monkeypatch.setattr(watch, "cross_watch", none)
    final, record = await watch.watch(ctx, Path("."), INFO, Transcript(text=""))
    assert final == a and record["agreement"] is None


def test_transcript_parsing_and_language() -> None:
    raw = {"transcript": "সব কলম মগে যাবে", "audioDurationMs": 4200,
           "turns": [{"transcript": "সব কলম মগে যাবে", "startMs": 300, "endMs": 3900}]}  # fmt: skip
    tr = listen.parse_transcript(raw, 4.2, "narration")
    assert tr.language == "Bengali" and tr.segments[0].t0 == 0.3 and tr.segments[0].t1 == 3.9
    hi = listen.parse_transcript({"transcript": "सारे पेन मग में जाएंगे", "turns": []}, 3.0, "narration")
    assert hi.language == "Hindi" and hi.segments[0].t1 == 3.0
    empty = listen.parse_transcript({"transcript": "", "turns": []}, 5.0, "narration")
    assert empty.source == "none" and empty.text == ""


async def test_no_audio_means_no_narration() -> None:
    tr = await listen.transcribe(RunContext(None), None)
    assert tr.source == "none" and tr.text == ""


def test_prompt_hash_changes_with_the_text() -> None:
    from demobot.llm import parse_json, prompt

    text, sha = prompt("watch")
    assert "goal DSL" in text and len(sha) == 10
    assert parse_json('Sure:\n```json\n{"a": 1}\n```', "x") == {"a": 1}
    _ = json
