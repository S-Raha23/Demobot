"""A caveat the supervisor accepted for a program carries over when verify re-checks that program."""

import json
import shutil
from pathlib import Path
from typing import Any, ClassVar

import pytest

from demobot import pipeline
from demobot.errors import DemoBotError
from demobot.events import EventLog, RunContext
from demobot.schemas import Verification

RUN = Path(__file__).parents[1] / "fixtures" / "runs" / "pens-in-cup"


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, symbolic_ok: bool) -> pipeline.Run:
    d = tmp_path / "r"
    shutil.copytree(RUN, d)
    run = pipeline.Run("r", d, RunContext("r", "dev", EventLog(d / "events.jsonl", "r"), "verify"))
    ver = run.read("verify.json", Verification)
    ver.agree, ver.failure_class, ver.accepted_caveat = False, "judge_dissent", None
    ver.symbolic.ok = symbolic_ok
    ver.real_world.ok = True

    class Sim:
        renders: ClassVar[dict[str, str]] = {}

    async def simulate(*a: Any, **k: Any) -> Sim:
        return Sim()

    async def fake_verify(*a: Any, **k: Any) -> tuple[Verification, dict[str, Any]]:
        return ver.model_copy(deep=True), {}

    from demobot.program import sandbox

    monkeypatch.setattr(sandbox, "simulate", simulate)
    monkeypatch.setattr(pipeline, "keep_sim", lambda run, res, tag, v: res)
    monkeypatch.setattr(pipeline.verify, "verify", fake_verify)
    return run


async def test_accepted_caveat_applies_to_the_same_program(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _run(tmp_path, monkeypatch, symbolic_ok=True)
    with pytest.raises(DemoBotError):  # no caveat yet: the judge's dissent fails verify
        await pipeline.stage_verify(run)
    run.update_meta(
        caveat="stand-ins look larger than the real pens",
        caveat_program=pipeline.latest_program(run).version,
    )
    summary = await pipeline.stage_verify(run)
    assert "accepted by the supervisor" in summary
    assert json.loads((run.art / "verify.json").read_text())["accepted_caveat"].startswith(
        "stand-ins"
    )
    # a newer program is not covered by the old caveat
    run.update_meta(caveat_program=-1)
    with pytest.raises(DemoBotError):
        await pipeline.stage_verify(run)


async def test_caveat_never_covers_a_failed_symbolic_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _run(tmp_path, monkeypatch, symbolic_ok=False)
    run.update_meta(caveat="x", caveat_program=pipeline.latest_program(run).version)
    with pytest.raises(DemoBotError):
        await pipeline.stage_verify(run)
