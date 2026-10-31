"""Supervisor fallback policy and decision bookkeeping (no network)."""

import json
from pathlib import Path
from typing import Any

from demobot.agents import supervisor
from demobot.errors import DemoBotError
from demobot.events import EventLog, RunContext, read_events
from demobot.schemas import GoalClause, IngestInfo, Selector, SpecObject, Step, TaskSpec, Track


class FakeRun:
    def __init__(self, d: Path) -> None:
        self.dir = d
        self.art = d / "artifacts"
        self.art.mkdir(parents=True)
        self.run_id = "r"
        self.ctx = RunContext("r", "dev", EventLog(d / "events.jsonl", "r"), "run")
        spec = TaskSpec(summary="pens into the mug", generalization="",
                        objects=[SpecObject(name="pen", kind="pen", role="moved", alt_names=["teal pen"]),
                                 SpecObject(name="mug", kind="mug", role="container")],
                        steps=[Step(action="place_in", object="pen", target="mug", t_start=1, t_end=3)],
                        goal=[GoalClause(quant="all", select=Selector(kind="pen"), pred="inside", target=Selector(name="mug"))])  # fmt: skip
        (self.art / "taskspec.json").write_text(spec.model_dump_json())

    def read(self, name: str, schema: Any) -> Any:
        return schema.model_validate_json((self.art / name).read_text())


def test_fixed_policy_covers_every_failure_class() -> None:
    # "inconclusive" added with the verify fix: it was previously missing because
    # inconclusive checks silently passed (classify returned None)
    assert supervisor.FIXED_POLICY == {"spec_mismatch": "rewatch", "program_bug": "reprogram",
                                       "perception_gap": "retrack", "judge_dissent": "accept",
                                       "inconclusive": "retrack"}  # fmt: skip


async def test_without_a_model_the_fixed_policy_decides_visibly(
    tmp_path: Path, monkeypatch
) -> None:
    run = FakeRun(tmp_path)
    obs = {
        "failure_class": "judge_dissent",
        "symbolic": {"ok": True},
        "real_world": {"ok": True},
        "perceptual": {"ok": True},
    }
    (run.art / "verify.json").write_text("{}")
    monkeypatch.setattr(supervisor, "observation", lambda r, e: obs)

    async def no_model(**_: Any) -> Any:
        raise DemoBotError("API_UNAVAILABLE", "down")

    monkeypatch.setattr(supervisor.gateway, "chain_call", no_model)
    out = await supervisor.supervise(run, DemoBotError("VERIFY_FAILED", "judge_dissent"))
    assert out.accepted and "three checks pass" in out.caveat
    events = list(read_events(tmp_path / "events.jsonl"))
    dec = [e.payload for e in events if e.type == "decision"]
    assert len(dec) == 1 and dec[0]["tool"] == "accept" and dec[0]["by"] == "fixed policy"
    assert dec[0]["observation"] and dec[0]["result"] and dec[0]["reasoning_summary"]
    assert any(e.payload.get("fallback") for e in events if e.type == "log")


async def test_unattended_ask_user_does_not_consume_a_decision(tmp_path: Path, monkeypatch) -> None:
    run = FakeRun(tmp_path)
    s = supervisor.Supervisor(run, DemoBotError("VERIFY_FAILED", "x"))
    monkeypatch.setattr(supervisor, "observation", lambda r, e: {"failure_class": "inconclusive"})
    calls: list[str] = []

    async def fake_decide(obs):  # type: ignore[no-untyped-def]
        calls.append("decide")
        if len(calls) == 1:
            return (
                "ask_user",
                {"question": "which?", "options": ["a", "b"], "reason": "unsure"},
                "test",
            )
        return "accept", {"caveat": "ok", "reason": "enough evidence"}, "test"

    monkeypatch.setattr(s, "decide", fake_decide)
    out = await s.loop()
    # the unattended ask got no answer and is not counted: only the accept is a decision,
    # numbered step 1, and the question event was still emitted by act()
    assert out.accepted and len(out.decisions) == 1 and out.decisions[0].tool == "accept"
    assert out.decisions[0].step == 1 and len(calls) == 2
    events = list(read_events(tmp_path / "events.jsonl"))
    assert any(e.type == "question" for e in events)
    assert len([e for e in events if e.type == "decision"]) == 1


async def test_accept_is_refused_when_checks_fail_and_budgets_hold(
    tmp_path: Path, monkeypatch
) -> None:
    run = FakeRun(tmp_path)
    s = supervisor.Supervisor(run, DemoBotError("VERIFY_FAILED", "x"))
    args = s.policy_args("accept", {"symbolic": {"ok": False}})
    assert (
        await s.act("accept", args) == "cannot accept: the checks do not all pass"
        and not s.out.accepted
    )
    s.used["reprogram"] = supervisor.BUDGET["reprogram"]
    assert (await s.act("reprogram", {"feedback": "x"})).startswith("refused")
    assert json.loads(json.dumps(supervisor.TOOLS))  # the tool table is valid JSON


def test_drop_final_mask_only_removes_that_object(tmp_path: Path) -> None:
    art = tmp_path / "artifacts"
    art.mkdir()
    assert supervisor.drop_final_mask(art, "pen") is False  # no file yet
    (art / "final_masks.json").write_text(
        json.dumps({"pen": {"centroid": [1, 2]}, "mug": {"centroid": [3, 4]}})
    )
    assert supervisor.drop_final_mask(art, "pen") is True
    assert json.loads((art / "final_masks.json").read_text()) == {"mug": {"centroid": [3, 4]}}
    assert supervisor.drop_final_mask(art, "pen") is False  # already gone


async def test_retrack_invalidates_final_mask(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    run = FakeRun(tmp_path)
    art = run.art
    info = IngestInfo(source_name="c.mp4", width=640, height=360, raw_duration_s=5, trim_start_s=0,
                      trim_end_s=5, duration_s=5, analysis_fps=10, analysis_frames=50, has_audio=False,
                      keyframes=[], keyframe_times=[])  # fmt: skip
    (art / "ingest.json").write_text(info.model_dump_json())
    (art / "analysis.mp4").write_bytes(b"clip")
    (art / "tracks.json").write_text(
        json.dumps({"tracks": [{"name": "pen", "phrase": "pen"}, {"name": "mug", "phrase": "mug"}]})
    )
    (art / "final_masks.json").write_text(
        json.dumps(
            {
                "pen": {"centroid": [1, 2], "poly": [[0, 0]]},
                "mug": {"centroid": [3, 4], "poly": [[1, 1]]},
            }
        )
    )
    from demobot import perceive, pipeline

    async def fake_sam(*a, **k):  # type: ignore[no-untyped-def]
        return {}

    monkeypatch.setattr(perceive, "sam_video", fake_sam)
    monkeypatch.setattr(perceive, "split_tracks", lambda frames, n: {"0": {0: object()}})
    monkeypatch.setattr(perceive, "quality", lambda track, n: 0.9)
    monkeypatch.setattr(perceive, "to_track",
                        lambda name, phrase, oid, inst, n, fps, stab, flags: Track(name=name, phrase=phrase, quality=0.9, frames=[]))  # fmt: skip

    async def noop(run):  # type: ignore[no-untyped-def]
        return "ok"

    monkeypatch.setattr(pipeline, "stage_ground", noop)
    monkeypatch.setattr(pipeline, "stage_twin_build", noop)
    s = supervisor.Supervisor(run, DemoBotError("VERIFY_FAILED", "x"))

    async def ok_reverify():  # type: ignore[no-untyped-def]
        return "verify passes: ok"

    monkeypatch.setattr(s, "reverify", ok_reverify)
    result = await s.retrack("pen", "teal pen")
    assert "retracked pen as 'teal pen'" in result
    # the stale reference-frame mask for pen is gone; mug's survives
    assert json.loads((art / "final_masks.json").read_text()) == {
        "mug": {"centroid": [3, 4], "poly": [[1, 1]]}
    }
    tracks = json.loads((art / "tracks.json").read_text())["tracks"]
    assert next(t for t in tracks if t["name"] == "pen")["phrase"] == "teal pen"
