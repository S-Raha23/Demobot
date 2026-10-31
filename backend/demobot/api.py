"""HTTP API (docs/02 "HTTP API"). Runs are folders on disk (docs/run-artifacts.md); baked runs
ship in backend/tests/fixtures/runs/ and are always listed."""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pybullet_data
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from demobot import budget
from demobot.config import PROVIDERS, ROOT, settings
from demobot.errors import DemoBotError
from demobot.schemas import GoalClause, Layout, SceneObject

app = FastAPI(title="DemoBot", version=version("demobot"))
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"],
)  # fmt: skip
BAKED = ROOT / "backend" / "tests" / "fixtures" / "runs"
PANDA = Path(pybullet_data.getDataPath()) / "franka_panda"
app.mount("/assets/franka_panda", StaticFiles(directory=PANDA), name="panda")


@app.exception_handler(DemoBotError)
async def _demobot_error(_: Request, e: DemoBotError) -> JSONResponse:
    return JSONResponse(e.as_dict(), status_code=e.http)


def run_roots() -> list[Path]:
    return [settings.data_path / "runs", BAKED]


def run_dir(run_id: str) -> Path:
    if not run_id.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(404, "no such run")
    for root in run_roots():
        d = root / run_id
        if (d / "events.jsonl").exists():
            return d
    raise HTTPException(404, "no such run")


def _read_json(p: Path) -> Any:
    return json.loads(p.read_text()) if p.exists() else None


@app.get("/api/health")
def health() -> dict[str, object]:
    mode = settings.demobot_mode
    headroom = {} if mode == "replay" else {p: budget.remaining(mode, p) for p in PROVIDERS}
    return {"ok": True, "mode": mode, "version": app.version, "headroom_usd": headroom}


@app.get("/api/runs")
def list_runs() -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for root in run_roots():
        if not root.exists():
            continue
        for d in sorted(root.iterdir()):
            meta = _read_json(d / "run.json")
            if meta and d.name not in seen:
                card = _read_json(d / "artifacts" / "card.json")
                seen[d.name] = {**meta, "baked": root == BAKED, "card": card}
    return sorted(seen.values(), key=lambda r: r.get("created_at", ""), reverse=True)


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    d = run_dir(run_id)
    files = sorted(
        str(p.relative_to(d)) for p in (d / "artifacts").rglob("*") if p.is_file()
    ) if (d / "artifacts").exists() else []  # fmt: skip
    return {
        "run": _read_json(d / "run.json"),
        "state": _read_json(d / "state.json"),
        "artifacts": files,
    }


@app.get("/api/runs/{run_id}/artifacts/{path:path}")
def get_artifact(run_id: str, path: str) -> FileResponse:
    d = run_dir(run_id).resolve()
    p = (d / path).resolve()
    if not p.is_relative_to(d) or not p.is_file():
        raise HTTPException(404, "no such artifact")
    return FileResponse(p)


def _ts(e: dict[str, Any]) -> float:
    return datetime.fromisoformat(e["ts"].replace("Z", "+00:00")).timestamp()


async def _event_stream(
    d: Path, replay: bool, speed: float, request: Request
) -> AsyncIterator[dict[str, str]]:
    """Replay: every event with its original relative timing / speed (gaps capped at 3 s so
    replays never stall). Live: tail events.jsonl until the run ends."""
    path = d / "events.jsonl"
    if replay:
        prev: float | None = None
        for line in path.read_text().splitlines():
            if await request.is_disconnected():
                return
            if not line.strip():
                continue
            e = json.loads(line)
            if prev is not None:
                await asyncio.sleep(min(3.0, max(0.0, _ts(e) - prev)) / max(speed, 0.1))
            prev = _ts(e)
            yield {"event": "event", "data": line}
        yield {"event": "end", "data": "{}"}
        return
    pos = 0
    idle = 0.0
    while not await request.is_disconnected():
        with path.open() as f:
            f.seek(pos)
            chunk = f.read()
            pos = f.tell()
        for line in chunk.splitlines():
            if line.strip():
                yield {"event": "event", "data": line}
        state = _read_json(d / "state.json") or {}
        if not chunk and state.get("cursor") in ("done", "failed", "card") and idle > 2:
            yield {"event": "end", "data": "{}"}
            return
        idle = 0.0 if chunk else idle + 0.5
        await asyncio.sleep(0.5)


@app.get("/api/runs/{run_id}/events")
async def run_events(
    run_id: str, request: Request, replay: int = 0, speed: float = 1.0
) -> EventSourceResponse:
    return EventSourceResponse(_event_stream(run_dir(run_id), bool(replay), speed, request))


@app.get("/api/runs/{run_id}/events.json")
def run_events_json(run_id: str) -> list[dict[str, Any]]:
    """All events at once (for "skip to result" and tests)."""
    path = run_dir(run_id) / "events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _latest_program(d: Path) -> tuple[str, int]:
    programs = _read_json(d / "artifacts" / "programs.json") or []
    passing = [p for p in programs if p.get("passed_demo")] or programs
    if not passing:
        raise HTTPException(409, "this run has no program yet")
    p = max(passing, key=lambda p: p["version"])
    return p["code"], p["version"]


@app.post("/api/runs/{run_id}/try-layout")
async def try_layout(run_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Run the skill's program on a judge-edited layout: simulation only, free.
    Body: {"objects": [{name, x, y, yaw?}]} (moves applied to the demo layout) or a full Layout."""
    from demobot.program.sandbox import simulate
    from demobot.sim.layouts import validate

    d = run_dir(run_id)
    scene = _read_json(d / "artifacts" / "twin_scene.json")
    spec = _read_json(d / "artifacts" / "taskspec.json")
    if not scene or not spec:
        raise HTTPException(409, "this run has no twin yet")
    base = Layout.model_validate(scene["layout"])
    if "work_area" in body:
        layout = Layout.model_validate(body)
    else:
        moves = {m["name"]: m for m in body.get("objects", [])}
        objs: list[SceneObject] = []
        for o in base.objects:
            m = moves.get(o.name)
            objs.append(
                o.model_copy(update={k: float(m[k]) for k in ("x", "y", "yaw") if m and k in m})
            )
        layout = base.model_copy(update={"objects": objs, "id": "user", "source": "user"})
    problems = validate(layout)
    if problems:
        return {"ok": False, "problems": problems}
    code, version_ = _latest_program(d)
    goal = [GoalClause.model_validate(g) for g in spec["goal"]]
    res = await simulate(code, layout, goal, render=False)
    out = res.model_dump(mode="json")
    if res.twin_trajectory:
        out["twin"] = json.loads(Path(res.twin_trajectory).read_text())
    return {
        "ok": True,
        "program_version": version_,
        "layout": layout.model_dump(mode="json"),
        "result": out,
    }


@app.post("/api/runs/{run_id}/shuffle")
def shuffle(run_id: str, seed: int = 0) -> dict[str, Any]:
    from demobot.sim.layouts import random_layout

    scene = _read_json(run_dir(run_id) / "artifacts" / "twin_scene.json")
    if not scene:
        raise HTTPException(409, "this run has no twin yet")
    return random_layout(Layout.model_validate(scene["layout"]), seed).model_dump(mode="json")


@app.get("/api/skills")
def skills() -> list[dict[str, Any]]:
    return [r["card"] | {"run_title": r.get("title"), "fixture": r.get("fixture", False)}
            for r in list_runs() if r.get("card")]  # fmt: skip


@app.get("/api/costs")
def costs() -> dict[str, Any]:
    runs = []
    for r in list_runs():
        c = _read_json(run_dir(r["run_id"]) / "artifacts" / "costs.json")
        if c:
            runs.append({"run_id": r["run_id"], "title": r.get("title"), **c})
    return {"ledger": budget.summary(), "runs": runs}


# the built frontend (Docker / HF Space); in dev, Vite serves it on :5173
DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="web")

    @app.exception_handler(404)
    async def _spa(request: Request, exc: HTTPException) -> Any:
        if request.url.path.startswith(("/api", "/assets/franka_panda")):
            return JSONResponse(
                {"code": "NOT_FOUND", "message": str(exc.detail), "stage": None}, 404
            )
        return FileResponse(DIST / "index.html")
