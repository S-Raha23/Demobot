"""Red team: delivered-vs-requested layout counts are visible, not silent."""

from pathlib import Path

from demobot.agents import redteam
from demobot.events import EventLog, RunContext, read_events
from demobot.schemas import Layout, SceneObject
from demobot.sim.layouts import default_frame


def _layout(name: str = "a") -> Layout:
    work, base = default_frame()
    obj = SceneObject(name=name, kind="pen", role="moved", x=20, y=20, w=4, d=4, h=2)  # type: ignore[arg-type]
    return Layout(objects=[obj], work_area=work, robot_base_cm=base, id="base")


async def test_red_team_emits_delivered_vs_requested(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    ctx = RunContext("r", "dev", EventLog(tmp_path / "events.jsonl", "r"), "run")
    base = _layout()

    async def fake_propose(c, persona, b, goal):  # type: ignore[no-untyped-def]
        # only two personas deliver one layout each; the rest deliver nothing
        if persona in ("crowder", "mirror"):
            return [(base, "hard")]
        return []

    monkeypatch.setattr(redteam, "propose", fake_propose)
    out = await redteam.red_team(ctx, base, [])
    assert len(out) == 2
    events = list(read_events(tmp_path / "events.jsonl"))
    metrics = [
        e.payload
        for e in events
        if e.type == "metric" and e.payload.get("name") == "redteam_layouts"
    ]
    assert metrics and metrics[0]["delivered"] == 2
    assert metrics[0]["requested"] == len(redteam.PERSONAS) * redteam.LAYOUTS_PER_PERSONA
    assert any(e.type == "log" and "2/" in str(e.payload.get("message", "")) for e in events)
