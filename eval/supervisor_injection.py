"""M8 acceptance: inject failures into copies of verified runs and let the supervisor recover.

uv run python -m eval.supervisor_injection
"""

import asyncio
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from demobot import pipeline
from demobot.config import settings
from demobot.schemas import TaskSpec

OPPOSITE = {
    "left_of": "right_of",
    "right_of": "left_of",
    "in_front_of": "behind",
    "behind": "in_front_of",
}
RUNS = settings.data_path / "runs"


def clone(src: str, name: str) -> Path:
    dst = RUNS / f"sup-{name}"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(RUNS / src, dst, ignore=shutil.ignore_patterns("clean_plate.jpg"))
    meta = json.loads((dst / "run.json").read_text())
    for k in ("supervised", "caveat", "error"):
        meta.pop(k, None)
    meta["run_id"] = dst.name
    (dst / "run.json").write_text(json.dumps(meta, indent=1))
    for line in ("events.jsonl",):
        (dst / line).write_text("")
    return dst


def reset(d: Path, *stages: str) -> None:
    st = json.loads((d / "state.json").read_text())
    for s in stages:
        st["stages"].pop(s, None)
    (d / "state.json").write_text(json.dumps(st))


def inject_program_bug(d: Path) -> None:
    progs = json.loads((d / "artifacts" / "programs.json").read_text())
    bad = dict(progs[-1])
    bad["version"] = len(progs) + 1
    bad["code"] = (
        "def run(scene, robot):\n    for o in scene.with_role('moved'):\n        robot.move(o, o.x + 15, o.y)\n"
    )
    bad["explanation"] = "injected fault"
    progs.append(bad)
    (d / "artifacts" / "programs.json").write_text(json.dumps(progs, indent=1))
    meta = json.loads((d / "run.json").read_text())
    meta["program_version"] = bad["version"]
    (d / "run.json").write_text(json.dumps(meta, indent=1))
    reset(d, "verify")


def edit_spec(d: Path, fn: Any) -> None:
    p = d / "artifacts" / "taskspec.json"
    spec = TaskSpec.model_validate_json(p.read_text())
    fn(spec)
    p.write_text(spec.model_dump_json(indent=1))
    reset(d, "ground", "twin_build", "verify")


def flip_relation(spec: TaskSpec) -> None:
    for c in spec.goal:
        if c.pred in OPPOSITE:
            c.pred = OPPOSITE[c.pred]  # type: ignore[assignment]


def wrong_object(spec: TaskSpec) -> None:
    moved = spec.steps[-1].object
    other = next(o.name for o in spec.objects if o.role == "distractor")
    for c in spec.goal:
        if c.select.name == moved:
            c.select.name = other


def drop_track(d: Path) -> None:
    p = d / "artifacts" / "tracks.json"
    raw = json.loads(p.read_text())
    spec = TaskSpec.model_validate_json((d / "artifacts" / "taskspec.json").read_text())
    moved = spec.steps[-1].object
    for t in raw["tracks"]:
        if t["name"] == moved:
            t["flags"] = ["not_found"]
            t["quality"] = 0.0
            for f in t["frames"]:
                f.update({"bbox_px": None, "centroid_px": None, "poly_px": None, "area_px": None})
    p.write_text(json.dumps(raw))
    reset(d, "ground", "twin_build", "verify")


CASES = [
    ("judge-dissent", "syn7-00_place_in", lambda d: reset(d, "verify")),
    ("program-bug", "syn7-01_next_to", inject_program_bug),
    ("wrong-relation", "syn7-01_next_to", lambda d: edit_spec(d, flip_relation)),
    ("wrong-object", "syn7-01_next_to", lambda d: edit_spec(d, wrong_object)),
    ("lost-track", "syn7-09_swap", drop_track),
]


async def main() -> None:
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    rows = []
    for name, src, inject in CASES:
        if only and only != name:
            continue
        d = clone(src, name)
        inject(d)
        run = pipeline.open_run(d.name)
        try:
            await pipeline.run_pipeline(run, until="verify")
            recovered = run.state()["stages"].get("verify") == "done"
        except Exception as e:
            recovered = False
            print(f"{name}: {type(e).__name__}: {str(e)[:200]}", file=sys.stderr)
        decisions = [json.loads(line)["payload"] for line in (d / "events.jsonl").read_text().splitlines()
                     if '"type":"decision"' in line and '"agent":"supervisor"' in line]  # fmt: skip
        complete = all(
            k in x and x[k]
            for x in decisions
            for k in ("observation", "tool", "result", "reasoning_summary")
        )
        rows.append({"case": name, "recovered": recovered, "decisions": [f"{x['tool']}: {x['result'][:90]}" for x in decisions],
                     "every_decision_complete": complete, "caveat": run.meta().get("caveat")})  # fmt: skip
        print(json.dumps(rows[-1]))
    ok = sum(r["recovered"] for r in rows)
    print(f"\nrecovered {ok}/{len(rows)} injected failures", file=sys.stderr)
    (settings.data_path / "supervisor_injection.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
