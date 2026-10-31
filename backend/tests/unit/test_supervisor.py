"""Supervisor fallback policy and decision bookkeeping (no network)."""

import json
from pathlib import Path
from typing import Any

from demobot.agents import supervisor
from demobot.errors import DemoBotError
from demobot.events import EventLog, RunContext, read_events
from demobot.schemas import GoalClause, Selector, SpecObject, Step, TaskSpec


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
    assert supervisor.FIXED_POLICY == {"spec_mismatch": "rewatch", "program_bug": "reprogram",
                                       "perception_gap": "retrack", "judge_dissent": "accept"}  # fmt: skip


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
