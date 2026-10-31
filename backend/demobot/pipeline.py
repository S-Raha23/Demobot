"""The event-sourced, resumable run (docs/02 "The run model", docs/run-artifacts.md).

Each stage reads earlier artifacts, writes its own and emits events. A finished stage is never
rerun; a rerun of an unfinished one hits the model cache, so restarts cost $0.
"""

import json
import secrets
import shutil
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from demobot import calibrate, listen, media, watch
from demobot.config import settings
from demobot.errors import DemoBotError
from demobot.events import EventLog, RunContext
from demobot.schemas import Calibration, IngestInfo, TaskSpec, Transcript

STAGES = [
    "ingest", "calibrate", "listen", "watch", "perceive", "ground", "twin_build", "program",
    "verify", "stress", "harden", "card",
]  # fmt: skip


@dataclass
class Run:
    run_id: str
    dir: Path
    ctx: RunContext

    @property
    def art(self) -> Path:
        return self.dir / "artifacts"

    def state(self) -> dict[str, Any]:
        p = self.dir / "state.json"
        return json.loads(p.read_text()) if p.exists() else {"cursor": None, "stages": {}}

    def set_stage(self, stage: str, status: str) -> None:
        st = self.state()
        st["stages"][stage] = status
        st["cursor"] = stage if status != "done" or stage != STAGES[-1] else "done"
        (self.dir / "state.json").write_text(json.dumps(st, indent=1))

    def meta(self) -> dict[str, Any]:
        return json.loads((self.dir / "run.json").read_text())

    def update_meta(self, **kw: Any) -> None:
        (self.dir / "run.json").write_text(json.dumps(self.meta() | kw, indent=1))

    def artifact(self, stage: str, path: Path, kind: str, label: str) -> None:
        self.ctx.emit("artifact", stage, payload={"name": path.name, "path": str(path.relative_to(self.dir)),
                                                  "kind": kind, "label": label})  # fmt: skip

    def write(self, name: str, model: Any) -> Path:
        p = self.art / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            model.model_dump_json(indent=1)
            if hasattr(model, "model_dump_json")
            else json.dumps(model, indent=1)
        )
        return p

    def read(self, name: str, schema: Any) -> Any:
        return schema.model_validate_json((self.art / name).read_text())


def new_run_id() -> str:
    return datetime.now(UTC).strftime("%m%d-%H%M") + "-" + secrets.token_hex(3)


def create_run(
    clip: Path, title: str = "", run_id: str | None = None, mode: str | None = None
) -> Run:
    rid = run_id or new_run_id()
    d = settings.data_path / "runs" / rid
    (d / "input").mkdir(parents=True, exist_ok=True)
    dest = d / "input" / f"clip{clip.suffix.lower()}"
    if not dest.exists():
        shutil.copy(clip, dest)
    if not (d / "run.json").exists():
        (d / "run.json").write_text(json.dumps({
            "run_id": rid, "title": title or clip.stem.replace("_", " "),
            "created_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "source": clip.name, "mode": mode or settings.demobot_mode, "status": "created", "fixture": False,
        }, indent=1))  # fmt: skip
    return open_run(rid)


def open_run(run_id: str) -> Run:
    d = settings.data_path / "runs" / run_id
    if not (d / "run.json").exists():
        raise DemoBotError("NO_SUCH_RUN", f"no run {run_id}", http=404)
    meta = json.loads((d / "run.json").read_text())
    log = EventLog(d / "events.jsonl", run_id)
    return Run(run_id, d, RunContext(run_id, meta.get("mode", "dev"), log, "run"))


# ---------- stages ----------
async def stage_ingest(run: Run) -> str:
    clip = next((run.dir / "input").glob("clip.*"))
    info = media.ingest(clip, run.art)
    run.write("ingest.json", info)
    run.artifact("ingest", run.art / "keyframes" / "kf_00.jpg", "image", "First frame")
    return f"{info.duration_s:.1f} s of action, {info.width}×{info.height}" + (
        ", with narration" if info.has_audio else ""
    )


async def stage_calibrate(run: Run) -> str:
    cal = calibrate.run(run.art / "analysis.mp4", run.art, run.art / "display_raw.mp4")
    for name, kind, label in [("display.mp4", "video", "Your demo (stabilised)"), ("calibration.json", "json", "Calibration"),
                              ("camera_track.json", "json", "Camera track"),
                              ("calibration_overlay.json", "json", "Marker overlay"),
                              ("rectified_first.png", "image", "Table, top-down")]:  # fmt: skip
        run.artifact("calibrate", run.art / name, kind, label)
    run.ctx.emit(
        "metric",
        "calibrate",
        payload={"name": "reprojection_px", "value": round(cal.reprojection_px, 2), "unit": "px"},
    )
    run.ctx.emit(
        "metric",
        "calibrate",
        payload={"name": "handheld_drift_px", "value": cal.max_motion_px, "unit": "px"},
    )
    for w in cal.warnings:
        run.ctx.emit("log", "calibrate", payload={"message": w})
    return (f"4 markers, {cal.reprojection_px:.2f} px; camera {cal.camera.position_cm[2]:.0f} cm high, "
            f"tilt {cal.camera.tilt_deg:.0f}°; {cal.frames_interpolated} frames interpolated")  # fmt: skip


async def stage_listen(run: Run) -> str:
    info = run.read("ingest.json", IngestInfo)
    wav = run.art / "audio.wav" if info.has_audio else None
    tr = await listen.transcribe(run.ctx, wav)
    run.write("transcript.json", tr)
    run.artifact("listen", run.art / "transcript.json", "json", "Narration")
    return f'"{tr.text}" ({tr.language})' if tr.text else "no narration"


async def stage_watch(run: Run) -> str:
    info = run.read("ingest.json", IngestInfo)
    tr = run.read("transcript.json", Transcript)
    spec, cross = await watch.watch(run.ctx, run.art, info, tr)
    run.write("taskspec.json", spec)
    run.write("crosswatch.json", cross)
    run.artifact("watch", run.art / "taskspec.json", "json", "What it understood")
    run.artifact("watch", run.art / "crosswatch.json", "json", "Second opinion")
    agree = cross.get("agreement")
    return spec.summary + (f" (cross-watch agreement {agree:.0%})" if agree is not None else "")


StageFn = Callable[[Run], Awaitable[str]]
STAGE_FNS: dict[str, StageFn] = {
    "ingest": stage_ingest,
    "calibrate": stage_calibrate,
    "listen": stage_listen,
    "watch": stage_watch,
}


async def run_pipeline(run: Run, until: str | None = None) -> None:
    """Run every unfinished stage in order (resuming), stopping after `until`."""
    run.update_meta(status="running")
    for stage in STAGES:
        fn = STAGE_FNS.get(stage)
        if fn is None:
            break  # not built yet
        if run.state()["stages"].get(stage) == "done":
            if stage == until:
                break
            continue
        run.set_stage(stage, "running")
        run.ctx.emit("stage_start", stage)
        t0 = time.monotonic()
        try:
            summary = await fn(run)
        except DemoBotError as e:
            run.set_stage(stage, "failed")
            run.ctx.emit("error", stage, payload=e.as_dict())
            run.update_meta(status="failed", error=e.as_dict())
            raise
        run.set_stage(stage, "done")
        run.ctx.emit("stage_end", stage, payload={"ok": True, "summary": summary,
                                                  "duration_s": round(time.monotonic() - t0, 1)})  # fmt: skip
        if stage == until:
            break
    done = all(run.state()["stages"].get(s) == "done" for s in STAGE_FNS)
    run.update_meta(status="done" if done and len(STAGE_FNS) == len(STAGES) else "partial")


_ = (Calibration, TaskSpec)
