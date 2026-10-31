import json
from pathlib import Path

from fastapi.testclient import TestClient

from demobot.api import app
from demobot.config import settings
from demobot.events import EventLog


def make_run(run_id: str = "r-test") -> Path:
    d = settings.data_path / "runs" / run_id
    log = EventLog(d / "events.jsonl", run_id)
    log.emit("stage_start", "ingest", ts="2026-10-31T09:00:00.000Z")
    log.emit("stage_end", "ingest", ts="2026-10-31T09:00:00.500Z", payload={"ok": True})
    (d / "artifacts").mkdir()
    (d / "artifacts" / "taskspec.json").write_text('{"summary": "x"}')
    (d / "run.json").write_text(
        json.dumps({"run_id": run_id, "title": "Test", "created_at": "2026-10-31T09:00:01Z"})
    )
    (d / "state.json").write_text(json.dumps({"cursor": "done", "stages": {}}))
    return d


def test_runs_listing_detail_and_artifacts() -> None:
    make_run()
    c = TestClient(app)
    runs = c.get("/api/runs").json()
    assert any(r["run_id"] == "r-test" for r in runs)
    detail = c.get("/api/runs/r-test").json()
    assert detail["artifacts"] == ["artifacts/taskspec.json"]
    assert c.get("/api/runs/r-test/artifacts/artifacts/taskspec.json").json() == {"summary": "x"}
    sneaky = c.get("/api/runs/r-test/artifacts/..%2F..%2F..%2F..%2Fetc%2Fpasswd")
    assert sneaky.status_code == 404 and "root:" not in sneaky.text
    assert "root:" not in c.get("/api/runs/r-test/artifacts/../../../../etc/passwd").text
    assert c.get("/api/runs/nope").status_code == 404
    assert len(c.get("/api/runs/r-test/events.json").json()) == 2


def test_replay_streams_every_event_then_end() -> None:
    make_run()
    c = TestClient(app)
    with c.stream("GET", "/api/runs/r-test/events?replay=1&speed=50") as resp:
        body = "".join(resp.iter_text())
    assert body.count("event: event") == 2 and "event: end" in body


def test_panda_assets_are_served() -> None:
    c = TestClient(app)
    r = c.get("/assets/franka_panda/panda.urdf")
    assert r.status_code == 200 and "<robot" in r.text


def test_health() -> None:
    assert TestClient(app).get("/api/health").json()["ok"] is True


def test_live_endpoints(monkeypatch, tmp_path) -> None:
    from demobot import jobs

    c = TestClient(app)
    sample = settings.data_path / "samples" / "pens"
    sample.mkdir(parents=True)
    (sample / "clip.mp4").write_bytes(b"x")
    (sample / "sample.json").write_text('{"title": "Pens into the box"}')
    assert c.get("/api/samples").json()[0] == {
        "id": "pens",
        "title": "Pens into the box",
        "duration_s": None,
        "thumb": None,
        "source": "synthetic",
        "cached": False,
    }
    started: list[tuple[str, str]] = []
    monkeypatch.setattr(jobs, "start_sample", lambda s: started.append(("sample", s)) or "run-1")
    monkeypatch.setattr(
        jobs,
        "start_correction",
        lambda r, text="", audio_bytes=None: started.append((r, text)) or r,
    )
    assert c.post("/api/runs", json={"sample": "pens"}).json() == {"run_id": "run-1"}
    make_run("r-fix")
    assert c.post("/api/runs/r-fix/correct", json={"text": "left of the mug"}).status_code == 202
    assert started == [("sample", "pens"), ("r-fix", "left of the mug")]
    monkeypatch.setattr(settings, "demobot_mode", "replay")
    assert c.post("/api/runs", json={"sample": "pens"}).status_code == 405
    assert c.get("/assets/print/markers.pdf").headers["content-type"] == "application/pdf"
    assert "markdown" in c.get("/api/eval").json()


def test_judge_mode_limits(monkeypatch) -> None:
    from demobot import api, jobs

    c = TestClient(app)
    monkeypatch.setattr(settings, "demobot_mode", "judge")
    monkeypatch.setattr(jobs, "start_sample", lambda s: "run-1")
    assert c.post("/api/runs", json={"sample": "x"}).status_code == 202
    monkeypatch.setattr(settings, "cap_meta_judge_daily_usd", 0.5)  # below the headroom floor
    r = c.post("/api/runs", json={"sample": "x"})
    assert r.status_code == 429 and "Try-it" in r.text
    _ = api


def test_page_is_revalidated_and_hashed_bundles_are_cached() -> None:
    from fastapi.testclient import TestClient

    from demobot.api import app

    c = TestClient(app)
    assert c.get("/api/health").headers["cache-control"] == "no-cache"
    assert "immutable" in c.get("/assets/franka_panda/panda.urdf").headers["cache-control"]


def test_a_correction_is_a_new_skill_version_and_never_overwrites_the_demo_skill() -> None:
    """Library entry, Try-it record and the simulated program all come from one version (Fix 0, item 2)."""
    from fastapi.testclient import TestClient

    from demobot.api import app

    c = TestClient(app)
    run = "real-spoon-in-tub"
    entries = [s for s in c.get("/api/skills").json() if s["run_id"] == run]
    assert [e["version"] for e in entries] == [1, 2]
    v1, v2 = (c.get(f"/api/runs/{run}/skill?v={v}").json() for v in (1, 2))
    assert entries[0]["title"] == v1["title"] and entries[1]["title"] == v2["title"] != v1["title"]
    assert "spoon" in v1["spec"]["goal"][0]["select"]["name"] and "ball" in str(
        v2["spec"]["goal"][0]["select"]
    )
    assert v1["program"]["version"] == v1["program_version"] != v2["program"]["version"]
    r1 = c.post(f"/api/runs/{run}/try-layout", json={"objects": [], "version": 1}).json()
    assert r1["ok"] and r1["program_version"] == v1["program_version"]
    assert c.get(f"/api/runs/{run}").json()["run"]["title"] == v1["title"]
