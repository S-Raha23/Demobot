"""Perception + grounding accuracy on the synthetic set (M5): start and end positions of the moved
objects against the exact truth, plus whether the goal holds on the grounded real final state.

    uv run python -m eval.grounding_synth data/synth/set7 [--only 00_] [--run]
"""

import argparse
import asyncio
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np

from demobot import pipeline
from demobot.config import settings
from demobot.schemas import GroundedDemo, TaskSpec
from eval.understanding_synth import map_objects


def score(clip_dir: Path, run_dir: Path) -> dict[str, Any]:
    truth = json.loads((clip_dir / "truth.json").read_text())
    art = run_dir / "artifacts"
    spec = TaskSpec.model_validate_json((art / "taskspec.json").read_text())
    gd = GroundedDemo.model_validate_json((art / "grounded.json").read_text())
    t0 = json.loads((art / "ingest.json").read_text())["trim_start_s"]
    m = map_objects(spec, truth, t0)
    tobj = {o["name"]: o for o in truth["objects"]}
    moved = {s["object"] for s in truth["steps"]}
    starts, ends, rows = [], [], []
    for gi, gf in zip(gd.initial, gd.final, strict=True):
        tn = m.get(gi.name)
        if tn is None or tn not in moved:
            continue
        t = tobj[tn]
        es = math.dist((gi.x, gi.y), (t["x"], t["y"]))
        ee = math.dist((gf.x, gf.y), (t["final"]["x"], t["final"]["y"]))
        starts.append(es)
        ends.append(ee)
        rows.append({"object": gi.name, "truth": tn, "start_err_cm": round(es, 2), "end_err_cm": round(ee, 2)})
    return {
        "clip": clip_dir.name,
        "start_err_median": round(float(np.median(starts)), 2) if starts else None,
        "end_err_median": round(float(np.median(ends)), 2) if ends else None,
        "real_world_goal": all(r.holds for r in gd.real_world),
        "segments": len(gd.segments),
        "steps_matched": sum(x.segment is not None for x in gd.matches),
        "steps": len(gd.matches),
        "objects": rows,
        "flags": gd.flags,
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("set_dir")
    ap.add_argument("--only", default="")
    ap.add_argument("--run", action="store_true", help="run the pipeline up to twin_build first")
    a = ap.parse_args()
    dirs = [d for d in sorted(Path(a.set_dir).iterdir()) if (d / "truth.json").exists() and a.only in d.name]
    rows = []
    for d in dirs:  # sequential: SAM video jobs must not run in parallel
        rid = f"syn7-{d.name}"
        if a.run:
            run = pipeline.create_run(d / "clip.mp4", "", rid)
            try:
                await pipeline.run_pipeline(run, until="twin_build")
            except Exception as e:
                rows.append({"clip": d.name, "error": f"{type(e).__name__}: {e}"[:200]})
                continue
        rows.append(score(d, settings.data_path / "runs" / rid))
    for r in rows:
        print(json.dumps({k: v for k, v in r.items() if k not in ("objects",)}))
    starts = [r["start_err_median"] for r in rows if r.get("start_err_median") is not None]
    ends = [r["end_err_median"] for r in rows if r.get("end_err_median") is not None]
    if starts:
        print(f"\nmedian start error {np.median(starts):.2f} cm, median end error {np.median(ends):.2f} cm; "
              f"real-world goal holds on {sum(bool(r.get('real_world_goal')) for r in rows)}/{len(rows)}",
              file=sys.stderr)  # fmt: skip
    Path(a.set_dir, "grounding_eval.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
