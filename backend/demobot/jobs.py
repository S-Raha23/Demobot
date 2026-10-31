"""Background jobs for the HTTP API: one live pipeline job at a time (SAM video jobs must never
run in parallel), corrections, and samples. Status lives in run.json, so the UI streams a job
live while it says "running" and replays it afterwards."""

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

from demobot import pipeline
from demobot.config import ROOT, settings
from demobot.errors import DemoBotError
from demobot.logging import get_logger

_lock = asyncio.Lock()
_tasks: set[asyncio.Task[Any]] = set()
SAMPLES = [settings.data_path / "samples", ROOT / "backend" / "tests" / "fixtures" / "samples"]


def samples() -> list[dict[str, Any]]:
    """Sample clips judges can run: <id>/clip.mp4 plus an optional sample.json {title}."""
    out: dict[str, dict[str, Any]] = {}
    for root in SAMPLES:
        if not root.exists():
            continue
        for d in sorted(root.iterdir()):
            if (d / "clip.mp4").exists() and d.name not in out:
                meta = (
                    json.loads((d / "sample.json").read_text())
                    if (d / "sample.json").exists()
                    else {}
                )
                out[d.name] = {"id": d.name, "title": meta.get("title", d.name.replace("_", " ")),
                               "duration_s": meta.get("duration_s"), "thumb": f"/api/samples/{d.name}/thumb"
                               if (d / "thumb.jpg").exists() else None}  # fmt: skip
    return list(out.values())


def sample_dir(sample_id: str) -> Path:
    for root in SAMPLES:
        d = root / sample_id
        if (d / "clip.mp4").exists():
            return d
    raise DemoBotError("NO_SUCH_SAMPLE", f"no sample {sample_id!r}", http=404)


def _spawn(coro: Any) -> None:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _run_job(run: pipeline.Run) -> None:
    log = get_logger(run_id=run.run_id)
    async with _lock:
        run.update_meta(status="running")
        try:
            await pipeline.run_pipeline(run)
        except DemoBotError as e:
            log.warning("run_failed", code=e.code)
        except Exception as e:  # never leave a run "running"
            run.ctx.emit("error", "run", payload={"code": "INTERNAL", "message": str(e)[:300]})
            run.update_meta(status="failed")
            log.error("run_crashed", error=repr(e)[:300])
        finally:
            if run.meta().get("status") == "running":
                run.update_meta(
                    status="done"
                    if all(v == "done" for v in run.state()["stages"].values())
                    else "partial"
                )


def start_run(clip: Path, title: str = "", task_hint: str = "") -> str:
    run = pipeline.create_run(clip, title or clip.stem, mode=settings.demobot_mode)
    run.update_meta(status="queued", task_hint=task_hint or None)
    _spawn(_run_job(run))
    return run.run_id


def start_sample(sample_id: str) -> str:
    d = sample_dir(sample_id)
    meta = json.loads((d / "sample.json").read_text()) if (d / "sample.json").exists() else {}
    return start_run(d / "clip.mp4", meta.get("title", sample_id))


async def _correct_job(run: pipeline.Run, text: str, audio: Path | None) -> None:
    from demobot import correct

    async with _lock:
        before = run.meta().get("status")
        run.update_meta(status="running")
        try:
            await correct.correct(run, text=text, audio=audio)
        except DemoBotError as e:
            run.ctx.emit("error", "correct", payload=e.as_dict())
        except Exception as e:
            run.ctx.emit("error", "correct", payload={"code": "INTERNAL", "message": str(e)[:300]})
        finally:
            run.update_meta(status=before or "done")


def start_correction(run_id: str, text: str = "", audio_bytes: bytes | None = None) -> str:
    run = pipeline.open_run(run_id)
    if not (run.art / "programs.json").exists():
        raise DemoBotError("NOT_READY", "this run has no program to correct yet", http=409)
    audio = None
    if audio_bytes:
        n = len(list(run.art.glob("correction_upload_*"))) + 1
        audio = run.art / f"correction_upload_{n}.wav"
        audio.write_bytes(audio_bytes)
    if not text and audio is None:
        raise DemoBotError("EMPTY_CORRECTION", "send audio or text", http=422)
    _spawn(_correct_job(run, text, audio))
    return run.run_id


def copy_baked(run_id: str) -> Path:
    """A baked run is read-only: corrections work on a copy in data/runs."""
    src = ROOT / "backend" / "tests" / "fixtures" / "runs" / run_id
    dst = settings.data_path / "runs" / run_id
    if src.exists() and not dst.exists():
        shutil.copytree(src, dst)
    return dst
