"""Understanding accuracy on the synthetic set (M4): run the pipeline up to Watch on each clip and
check the TaskSpec against the exact truth.

A goal is correct when, evaluated on the true geometry under the spec's own names and kinds, it
holds on the true final state and does not already hold on the true initial state.

    uv run python -m eval.understanding_synth data/synth/set7 [--parallel 3]
"""

import argparse
import asyncio
import difflib
import json
import sys
from pathlib import Path
from typing import Any

from demobot import goal_dsl, pipeline
from demobot.schemas import SceneObject, TaskSpec


def map_objects(spec: TaskSpec, truth: dict[str, Any], t0: float) -> dict[str, str]:
    """spec name -> truth name: moved objects by step timing, the rest by kind and name."""
    out: dict[str, str] = {}
    tsteps = truth["steps"]
    for s in spec.steps:
        best, overlap = None, 0.0
        for ts in tsteps:
            a, b = ts["t_start"] - t0, ts["t_end"] - t0
            ov = min(b, s.t_end) - max(a, s.t_start)
            if ov > overlap and ts["object"] not in out.values():
                best, overlap = ts["object"], ov
        if best and s.object not in out:
            out[s.object] = best
    tobjs = {o["name"]: o for o in truth["objects"]}
    for s in spec.steps:  # targets of matched steps
        ts = next((x for x in tsteps if x["object"] == out.get(s.object)), None)
        if (
            ts
            and ts["target"]
            and s.target
            and s.target not in out
            and ts["target"] not in out.values()
        ):
            out[s.target] = ts["target"]
    for o in spec.objects:
        if o.name in out:
            continue
        cands = [
            (0.3 * (t["role"] == o.role) + 0.35 * (t["kind"] == o.kind)
             + 0.35 * difflib.SequenceMatcher(None, t["name"], o.name).ratio(), n)
            for n, t in tobjs.items() if n not in out.values()
        ]  # fmt: skip
        if cands:
            score, n = max(cands)
            if score >= 0.5:
                out[o.name] = n
    return out


def states(
    spec: TaskSpec, truth: dict[str, Any], m: dict[str, str]
) -> tuple[dict[str, SceneObject], dict[str, SceneObject]]:
    inv = {v: k for k, v in m.items()}
    specs = {o.name: o for o in spec.objects}
    init, final = {}, {}
    for t in truth["objects"]:
        sname = inv.get(t["name"])
        so = specs.get(sname) if sname else None
        base = {k: v for k, v in t.items() if k not in ("final", "texture")}
        if so is not None:
            base |= {"name": so.name, "kind": so.kind, "role": so.role}
        o = SceneObject.model_validate(base)
        init[o.name] = o
        f = t["final"]
        final[o.name] = o.model_copy(update={"x": f["x"], "y": f["y"]})
    return init, final


async def one(clip_dir: Path, sem: asyncio.Semaphore) -> dict[str, Any]:
    async with sem:
        truth = json.loads((clip_dir / "truth.json").read_text())
        run = pipeline.create_run(clip_dir / "clip.mp4", truth["summary"], f"syn7-{clip_dir.name}")
        try:
            await pipeline.run_pipeline(run, until="watch")
        except Exception as e:  # report and go on
            return {"clip": clip_dir.name, "error": f"{type(e).__name__}: {e}"[:200]}
        spec = TaskSpec.model_validate_json((run.art / "taskspec.json").read_text())
        cross = json.loads((run.art / "crosswatch.json").read_text())
        t0 = json.loads((run.art / "ingest.json").read_text())["trim_start_s"]
        m = map_objects(spec, truth, t0)
        init, final = states(spec, truth, m)
        holds_final = goal_dsl.all_hold(goal_dsl.evaluate(spec.goal, final, init))
        holds_init = goal_dsl.all_hold(goal_dsl.evaluate(spec.goal, init, init))
        moved_true = {s["object"] for s in truth["steps"]}
        moved_spec = {m.get(s.object) for s in spec.steps}
        return {
            "clip": clip_dir.name,
            "truth": truth["summary"],
            "spec": spec.summary,
            "goal_correct": holds_final and not holds_init,
            "holds_final": holds_final,
            "holds_initial": holds_init,
            "moved_recall": round(len(moved_true & moved_spec) / len(moved_true), 2),
            "steps": f"{len(spec.steps)}/{len(truth['steps'])}",
            "crosswatch_agreement": cross.get("agreement"),
            "arbitrated": bool(cross.get("arbitration")),
            "goal": [c.model_dump(exclude_none=True) for c in spec.goal],
        }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("set_dir")
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    sem = asyncio.Semaphore(a.parallel)
    dirs = [
        d
        for d in sorted(Path(a.set_dir).iterdir())
        if (d / "truth.json").exists() and a.only in d.name
    ]
    rows = await asyncio.gather(*(one(d, sem) for d in dirs))
    for r in rows:
        print(json.dumps({k: v for k, v in r.items() if k != "goal"}))
    ok = sum(bool(r.get("goal_correct")) for r in rows)
    print(f"\ngoal correct on {ok}/{len(rows)} clips", file=sys.stderr)
    Path(a.set_dir, "understanding_eval.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
