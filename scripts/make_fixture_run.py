"""Build a fixture run from a synthetic clip, for UI development (docs/run-artifacts.md).

Real: ingest, calibration (with stabilisation), the simulator, twin export and renders.
Simulated (labelled `fixture: true`): every model output, taken from the synthetic ground truth.

    uv run python scripts/make_fixture_run.py data/synth/set7/00_place_in [--id fx-place-in] [--bake]
"""

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from demobot import calibrate, goal_dsl, media  # noqa: E402
from demobot.config import OPEN_WEIGHT_MODELS, settings  # noqa: E402
from demobot.events import EventLog  # noqa: E402
from demobot.program.sandbox import execute  # noqa: E402
from demobot.schemas import (  # noqa: E402
    AgentDecision,
    CheckResult,
    Contact,
    GoalClause,
    GroundedDemo,
    JudgeVerdict,
    Layout,
    MotionSegment,
    Program,
    SceneObject,
    Segment,
    SimResult,
    SkillCard,
    SpecObject,
    Step,
    StepMatch,
    StressCase,
    StressReport,
    TaskSpec,
    Track,
    TrackFrame,
    Transcript,
    Verification,
)  # fmt: skip
from demobot.sim.layouts import random_layout, reach_map  # noqa: E402

SPARK, WONDER, SAM, VOICE = (
    "muse-spark-1.3",
    "muse-wonder-1.0",
    "sam-3.1",
    "muse-voice-transcribe-1.0",
)
OPEN_B, OPEN_M = "meta-models/muse-spark-open-1026", "meta-models/Muse-Spark-Open-816B-A42B"

# Per family: a buggy first draft (what the simulator catches) and the fixed version.
PROGRAMS: dict[str, tuple[str, str, str]] = {
    "place_in": (
        """def run(scene, robot):
    box = scene.containers()[0]
    for item in scene.with_role("moved"):
        robot.pick(item)
        robot.place_in(box)
    robot.place_in(box)
""",
        """def run(scene, robot):
    box = scene.containers()[0]
    for pen in scene.of_kind("pen"):
        if scene.is_inside(pen, box):
            continue
        robot.pick(pen)
        robot.place_in(box)
    robot.home()
""",
        "The draft called place_in once more with nothing held; the fix moves only pens that are not already inside.",
    ),
    "next_to": (
        """def run(scene, robot):
    ref = scene.with_role("reference")[0]
    item = scene.with_role("moved")[0]
    robot.pick(item)
    robot.place_next_to(ref, "{wrong}", gap=2)
""",
        """def run(scene, robot):
    ref = scene.with_role("reference")[0]
    item = scene.with_role("moved")[0]
    robot.pick(item)
    robot.place_next_to(scene.get(ref.name), "{rel}", gap=2.5)
""",
        "The draft placed it on the wrong side; the goal says {rel}.",
    ),
    "line_up": (
        """def run(scene, robot):
    items = scene.with_role("moved")
    y = items[0].y
    x = items[0].x
    for item in items[1:]:
        x += 8
        robot.move(item, x, y)
""",
        """def run(scene, robot):
    items = scene.with_role("moved")
    x0, y0, x1, y1 = scene.bounds()
    y = (y0 + y1) / 2
    total = sum(o.w for o in items) + 4 * (len(items) - 1)
    x = (x0 + x1) / 2 - total / 2
    placed = []
    for item in items:
        cx = x + item.w / 2
        for o in scene.objects():
            if o.name != item.name and o.name not in placed and abs(o.x - cx) < (o.w + item.w) / 2 + 4 and abs(o.y - y) < (o.d + item.d) / 2 + 4:
                robot.move(o, *scene.free_spot(size=(o.w, o.d), clearance=3, avoid=[(cx, y, 2 * (x1 - x0), item.d + 2)]))
        robot.move(scene.get(item.name), cx, y)
        placed.append(item.name)
        x += item.w + 4
""",
        "Fixed 8 cm steps made items collide; the fix spaces them by their widths and clears the row first.",
    ),
    "sort": (
        """def run(scene, robot):
    box = scene.of_kind("box")[0]
    for item in scene.with_role("moved"):
        robot.pick(item)
        robot.place_in(box)
""",
        """def run(scene, robot):
    mug = scene.of_kind("mug")[0]
    box = scene.of_kind("box")[0]
    for item in scene.with_role("moved"):
        robot.pick(item)
        robot.place_in(mug if item.kind == "pen" else box)
""",
        "The draft put everything in the box; pens belong in the mug.",
    ),
    "swap": (
        """def run(scene, robot):
    a, b = scene.with_role("moved")[:2]
    ax, ay = a.x, a.y
    robot.move(a, b.x, b.y)
    robot.move(scene.get(b.name), ax, ay)
""",
        """def run(scene, robot):
    a, b = scene.with_role("moved")[:2]
    ax, ay, bx, by = a.x, a.y, b.x, b.y
    side = max(a.w, a.d, b.w, b.d) + 2
    robot.move(a, *scene.free_spot(size=(side, side), clearance=3))
    robot.move(scene.get(b.name), ax, ay)
    robot.move(scene.get(a.name), bx, by)
""",
        "The draft dropped one item onto the other; the fix parks it in a free spot first.",
    ),
}


class Clock:
    def __init__(self, start: datetime) -> None:
        self.t = start

    def tick(self, s: float) -> str:
        self.t += timedelta(seconds=s)
        return self.t.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def rel(run: Path, p: Path | str) -> str:
    return str(Path(p).resolve().relative_to(run.resolve()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("clip_dir")
    ap.add_argument("--id")
    ap.add_argument("--bake", action="store_true", help="copy into backend/tests/fixtures/runs/")
    a = ap.parse_args()
    src = Path(a.clip_dir)
    truth = json.loads((src / "truth.json").read_text())
    family = truth["family"]
    run_id = a.id or f"fx-{family.replace('_', '-')}-{truth['seed']}"
    run = settings.data_path / "runs" / run_id
    if run.exists():
        shutil.rmtree(run)
    art = run / "artifacts"
    (run / "input").mkdir(parents=True)
    shutil.copy(src / "clip.mp4", run / "input" / "clip.mp4")
    clock = Clock(datetime(2026, 10, 31, 9, 0, tzinfo=UTC))
    log = EventLog(run / "events.jsonl", run_id)
    stages: dict[str, str] = {}

    def ev(type_: str, stage: str, dt: float = 0.2, **kw: Any) -> None:
        log.emit(type_, stage, ts=clock.tick(dt), **kw)  # type: ignore[arg-type]

    def call(stage: str, model: str, provider: str, purpose: str, secs: float, tin: int, tout: int,
             cost: float, **extra: Any) -> None:  # fmt: skip
        for k in range(int(secs // 5)):
            ev("log", stage, 5.0, payload={"heartbeat": True, "purpose": purpose, "model": model,
                                           "elapsed_s": 5.0 * (k + 1)})  # fmt: skip
        ev("model_call", stage, secs % 5 + 0.1, model=model, provider=provider,
           latency_ms=int(secs * 1000), tokens={"in": tin, "cached": 0, "out": tout},
           cost_usd=cost, cached=False,
           payload={"purpose": purpose, "open_weight": model in OPEN_WEIGHT_MODELS, "fixture": True, **extra})  # fmt: skip

    def artifact(stage: str, path: Path, kind: str, label: str) -> None:
        ev(
            "artifact",
            stage,
            0.05,
            payload={"name": path.name, "path": rel(run, path), "kind": kind, "label": label},
        )

    def start(stage: str) -> None:
        stages[stage] = "running"
        ev("stage_start", stage, 0.3)

    def end(stage: str, summary: str, secs: float) -> None:
        stages[stage] = "done"
        ev("stage_end", stage, 0.1, payload={"ok": True, "summary": summary, "duration_s": secs})

    # ---------- ingest (real) ----------
    start("ingest")
    info = media.ingest(run / "input" / "clip.mp4", art)
    (art / "ingest.json").write_text(info.model_dump_json(indent=1))
    artifact("ingest", art / "keyframes" / "kf_00.jpg", "image", "First frame")
    end("ingest", f"{info.duration_s:.1f} s of action, {info.width}×{info.height}", 2.1)
    t0 = info.trim_start_s

    # ---------- calibrate (real) ----------
    start("calibrate")
    cal = calibrate.run(art / "analysis.mp4", art, art / "display_raw.mp4")
    for name, kind, label in [("display.mp4", "video", "Your demo (stabilised)"),
                              ("calibration.json", "json", "Calibration"),
                              ("camera_track.json", "json", "Camera track"),
                              ("calibration_overlay.json", "json", "Marker overlay"),
                              ("rectified_first.png", "image", "Table, top-down")]:  # fmt: skip
        artifact("calibrate", art / name, kind, label)
    ev(
        "metric",
        "calibrate",
        payload={"name": "reprojection_px", "value": round(cal.reprojection_px, 2), "unit": "px"},
    )
    ev(
        "metric",
        "calibrate",
        payload={"name": "handheld_drift_px", "value": cal.max_motion_px, "unit": "px"},
    )
    end("calibrate", f"4 markers, {cal.reprojection_px:.2f} px; camera {cal.camera.position_cm[2]:.0f} cm high, "
        f"{cal.frames_interpolated} frames interpolated", 3.4)  # fmt: skip

    # ---------- listen (simulated) ----------
    start("listen")
    first = truth["steps"][0]["t_start"] - t0
    tr = Transcript(text=truth["narration"], language="English", languages=["English"],
                    segments=[Segment(t0=max(0.0, first - 0.5), t1=first + 2.0, text=truth["narration"])])  # fmt: skip
    (art / "transcript.json").write_text(tr.model_dump_json(indent=1))
    call("listen", VOICE, "meta", "listen", 3.8, 0, 0, 0.0008, audio_s=info.duration_s)
    artifact("listen", art / "transcript.json", "json", "Narration")
    end("listen", f'"{tr.text}"', 4.0)

    # ---------- watch (simulated) ----------
    start("watch")
    objs = truth["objects"]
    spec = TaskSpec(
        summary=truth["summary"],
        objects=[
            SpecObject(
                name=o["name"],
                kind=o["kind"],
                alt_names=[o["kind"]],
                role=o["role"],
                color=o["name"].split()[0],
                est_height_cm=o["h"],
                est_size_cm=(o["w"], o["d"]),
            )
            for o in objs
        ],
        steps=[
            Step(
                action=s["action"],
                object=s["object"],
                target=s["target"],
                relation=s["relation"],
                t_start=round(s["t_start"] - t0, 2),
                t_end=round(s["t_end"] - t0, 2),
                evidence=f"the hand lifts the {s['object']} and sets it down",
            )
            for s in truth["steps"]
        ],
        goal=[GoalClause.model_validate(g) for g in truth["goal"]],
        generalization={
            "place_in": "Every pen goes into the container, wherever it starts.",
            "next_to": "The item ends up on that side of the reference, wherever both are.",
            "line_up": "The moved items end in one straight left-to-right row.",
            "sort": "Pens go in the mug; every other moved item goes in the box.",
            "swap": "The two items trade places.",
        }[family],
    )
    (art / "taskspec.json").write_text(spec.model_dump_json(indent=1))
    call("watch", SPARK, "meta", "watch", 14.2, 9800, 3900, 0.0288)
    artifact("watch", art / "taskspec.json", "json", "What it understood")
    call("watch", OPEN_M, "modal", "crosswatch", 9.5, 7200, 2600, 0.0201)
    (art / "crosswatch.json").write_text(
        json.dumps({"spec": json.loads(spec.model_dump_json()), "agree": True, "differences": []})
    )
    ev("metric", "watch", payload={"name": "crosswatch_agree", "value": True})
    end("watch", spec.summary, 24.1)

    # ---------- perceive (simulated SAM from ground-truth masks) ----------
    start("perceive")
    stab = json.loads((art / "stabilise.json").read_text())["M"]
    tracks = []
    for name, recs in truth["tracks"].items():
        frames = []
        for r in recs:
            t = round(r["t"] - t0, 2)
            if t < 0 or t > info.duration_s:
                continue
            M = np.array(stab[min(len(stab) - 1, round(t * 30))])
            poly = None
            if r.get("poly"):
                pts = cv2.perspectiveTransform(np.array([r["poly"]], float), M)[0]
                poly = [(round(float(x), 1), round(float(y), 1)) for x, y in pts]
            bbox = tuple(r["bbox"]) if r.get("bbox") else None
            cen = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2) if bbox else None
            frames.append(
                TrackFrame(
                    t=t, bbox_px=bbox, centroid_px=cen, poly_px=poly, score=0.93 if bbox else None
                )
            )
        seen = sum(f.bbox_px is not None for f in frames) / max(1, len(frames))
        tracks.append(Track(name=name, phrase=name if name != "hand" else "hand", track_id=str(len(tracks)),
                            quality=round(0.93 * seen, 2), frames=frames))  # fmt: skip
        call(
            "perceive",
            SAM,
            "meta",
            f"track:{name}",
            6.5,
            0,
            0,
            round(len(frames) * 0.0002, 4),
            frames=len(frames),
        )
    (art / "tracks.json").write_text(json.dumps({"fps": 10, "size": [info.width, info.height],
                                                 "tracks": [json.loads(t.model_dump_json()) for t in tracks]}))  # fmt: skip
    artifact("perceive", art / "tracks.json", "json", "SAM 3.1 tracks")
    end("perceive", f"{len(tracks)} tracks", 6.5 * len(tracks))

    # ---------- ground (from truth) ----------
    start("ground")
    from synth.objects import CATALOGUE

    initial = [SceneObject.model_validate({k: v for k, v in o.items() if k != "final"}
                                          | {"texture": None, "hollow": CATALOGUE[o["kind"]].container})
               for o in objs]  # fmt: skip
    final = [o.model_copy(update={"x": round(f["final"]["x"], 2), "y": round(f["final"]["y"], 2), "z": round(f["final"]["z"], 2)})
             for o, f in zip(initial, objs, strict=True)]  # fmt: skip
    real = goal_dsl.evaluate(spec.goal, goal_dsl.to_state(final), goal_dsl.to_state(initial))
    grounded = GroundedDemo(
        initial=initial, final=final,
        segments=[MotionSegment(object=s["object"], t0=round(s["grasp_t"] - t0, 2), t1=round(s["release_t"] - t0, 2),
                                from_cm=tuple(s["from_cm"]), to_cm=tuple(s["to_cm"])) for s in truth["steps"]],  # type: ignore[arg-type]
        contacts=[c for s in truth["steps"] for c in (Contact(t=round(s["grasp_t"] - t0, 2), type="grasp", object=s["object"]),
                                                       Contact(t=round(s["release_t"] - t0, 2), type="release", object=s["object"]))],
        matches=[StepMatch(step=i, segment=i, confidence=0.9, timing_delta_s=0.2) for i in range(len(truth["steps"]))],
        real_world=real,
    )  # fmt: skip
    (art / "grounded.json").write_text(grounded.model_dump_json(indent=1))
    artifact("ground", art / "grounded.json", "json", "Measured in centimetres")
    ev("metric", "ground", payload={"name": "real_world_goal", "value": goal_dsl.all_hold(real)})
    end(
        "ground",
        f"{len(grounded.segments)} moves measured; the goal holds on your real final table",
        1.2,
    )

    # ---------- twin build ----------
    start("twin_build")
    layout = Layout(objects=initial, work_area=cal.work_area, robot_base_cm=cal.robot_base_cm)
    twin_scene = {"layout": json.loads(layout.model_dump_json()), "markers": [json.loads(m.model_dump_json()) for m in cal.markers],
                  "camera": json.loads(cal.camera.model_dump_json()), "image_size": list(cal.image_size),
                  "table_texture": "artifacts/rectified_first.png",
                  "rectify": {"origin_cm": list(cal.rectify_origin_cm), "px_per_cm": cal.rectify_px_per_cm},
                  "reach": reach_map(cal.work_area, cal.robot_base_cm)}  # fmt: skip
    (art / "twin_scene.json").write_text(json.dumps(twin_scene))
    artifact("twin_build", art / "twin_scene.json", "json", "Digital twin")
    end(
        "twin_build",
        f"{len(initial)} stand-ins on a {cal.work_area.w:.0f} × {cal.work_area.h:.0f} cm table",
        0.4,
    )

    # ---------- program (real simulation of a buggy draft, then the fix) ----------
    start("program")
    draft, fixed, why = PROGRAMS[family]
    rel_word = (
        (truth["steps"][-1].get("relation") or "right_of") if family == "next_to" else "right_of"
    )
    wrong = {
        "left_of": "right_of",
        "right_of": "left_of",
        "behind": "in_front_of",
        "in_front_of": "behind",
    }[rel_word]
    draft, fixed, why = (
        s.replace("{rel}", rel_word).replace("{wrong}", wrong) for s in (draft, fixed, why)
    )
    cal_json = cal.model_dump_json()
    programs: list[Program] = []
    (art / "programs").mkdir()
    for v, code in ((1, draft), (2, fixed)):
        call("program", WONDER, "meta", "synth", 18.0 if v == 1 else 11.0, 21000, 4200 if v == 1 else 2100,
             0.168 if v == 1 else 0.082)  # fmt: skip
        out = art / "sim" / f"demo_v{v}"
        res = execute(code, layout, spec.goal, out_dir=out, render=True, calibration_json=cal_json)
        res = _relpaths(res, run)
        (out / "result.json").write_text(res.model_dump_json(indent=1))
        passed = sum(r.holds for r in res.goal_results)
        ev("tool_call", "program", 0.5 + res.wall_s, payload={
            "agent": "coder", "iteration": v, "tool": "simulate", "args": {"layout": "demo", "program": v},
            "result": {"ok": res.goal_ok, "error": res.error.splitlines()[-1] if res.error else None,
                       "clauses_passed": passed, "clauses_total": len(res.goal_results)}})  # fmt: skip
        ev("metric", "program", payload={"name": "clauses_passed", "value": passed, "iteration": v})
        (art / "programs" / f"v{v}.py").write_text(code)
        programs.append(Program(version=v, parent_version=v - 1 or None, code=code, author="wonder",
                                explanation=why if v == 2 else "First draft from the TaskSpec.",
                                diff_from_parent=_diff(draft, fixed) if v == 2 else "", passed_demo=res.goal_ok))  # fmt: skip
        artifact("program", art / "programs" / f"v{v}.py", "code", f"Program v{v}")
        artifact("program", out / "twin_demo.json", "trajectory", f"Robot run, v{v}")
        last = res
    (art / "programs.json").write_text(
        json.dumps([json.loads(p.model_dump_json()) for p in programs], indent=1)
    )
    ev("tool_call", "program", 1.0, payload={"agent": "coder", "iteration": 3, "tool": "submit", "args": {"program": 2},
                                             "result": {"ok": True}})  # fmt: skip
    end(
        "program",
        f"v2 passes {sum(r.holds for r in last.goal_results)}/{len(last.goal_results)} clauses after 2 iterations",
        35.0,
    )

    # ---------- verify ----------
    start("verify")
    call(
        "verify",
        SAM,
        "meta",
        "segment_image",
        2.1,
        0,
        0,
        0.0025 * len(initial),
        images=len(initial),
    )
    call("verify", OPEN_B, "baseten", "judge", 4.2, 2400, 380, 0.0046)
    ver = Verification(
        program_version=2,
        symbolic=CheckResult(ok=last.goal_ok, clauses=last.goal_results, detail="goal on the simulated final state"),
        real_world=CheckResult(ok=goal_dsl.all_hold(real), clauses=real, detail="goal on your real final state"),
        perceptual=CheckResult(ok=last.goal_ok, clauses=last.goal_results, detail="SAM on the camera-view render (fixture: copied from symbolic)"),
        judge=JudgeVerdict(same_goal_achieved=True, confidence=0.86, differences=["the stand-ins are simpler shapes"]),
        agree=True, failure_class=None,
        renders={"real": "artifacts/reference_frame.jpg", "camera": last.renders.get("camera", ""), "top": last.renders.get("top", "")},
    )  # fmt: skip
    (art / "verify.json").write_text(ver.model_dump_json(indent=1))
    artifact("verify", art / "verify.json", "json", "Three checks and a judge")
    end("verify", "symbolic ✓ real-world ✓ perceptual ✓ judge ✓", 7.0)

    # ---------- stress and harden (real sims on random layouts standing in for personas) ----------
    start("stress")
    personas = ["crowder", "edge-walker", "rotator", "decoy", "near-miss", "stacker"]
    cases = []
    for i, persona in enumerate(personas):
        call("stress", OPEN_B, "baseten", f"redteam:{persona}", 3.0 + 0.4 * i, 1800, 700, 0.0052)
    for i in range(12):
        lay = random_layout(layout, 100 + i, f"red-{i:02d}").model_copy(
            update={"source": f"redteam:{personas[i % 6]}"}
        )
        out = art / "sim" / f"red-{i:02d}_v2"
        res = _relpaths(execute(fixed, lay, spec.goal, out_dir=out, render=True), run)
        (out / "result.json").write_text(res.model_dump_json(indent=1))
        cases.append(
            StressCase(
                layout=lay,
                persona=personas[i % 6],
                rationale="random rearrangement (fixture)",
                before=res,
            )
        )
        ev("tool_call", "stress", 0.3 + res.wall_s / 2, payload={"agent": "redteam", "iteration": i, "tool": "simulate",
           "args": {"layout": lay.id}, "result": {"ok": res.goal_ok, "layout": lay.id}})  # fmt: skip
    rb = sum(bool(c.before and c.before.goal_ok) for c in cases) / len(cases)
    report = StressReport(
        cases=cases, robustness_before=rb, robustness_after=rb, program_before=2, program_after=2
    )
    (art / "stress.json").write_text(report.model_dump_json())
    ev("metric", "stress", payload={"name": "robustness_before", "value": round(rb, 3)})
    artifact("stress", art / "stress.json", "json", "Red-team layouts")
    end("stress", f"robustness {round(rb * 12)}/12", 40.0)
    stages["harden"] = "skipped"

    # ---------- card ----------
    start("card")
    card = SkillCard(skill_id=run_id, title=truth["summary"].rstrip("."), description=spec.generalization,
                     image=None, goal_text=spec.summary, program_version=2, robustness=rb,
                     cost_to_learn_usd=0.0, run_id=run_id)  # fmt: skip
    events = [json.loads(line) for line in (run / "events.jsonl").read_text().splitlines()]
    total = round(sum(e.get("cost_usd") or 0 for e in events if e["type"] == "model_call"), 4)
    card.cost_to_learn_usd = total
    (art / "card.json").write_text(card.model_dump_json(indent=1))
    artifact("card", art / "card.json", "json", "Skill card")
    end("card", "skill saved to the library", 0.5)
    by_model: dict[str, float] = {}
    by_provider: dict[str, float] = {}
    ow = 0.0
    for e in events:
        if e["type"] == "model_call":
            by_model[e["model"]] = by_model.get(e["model"], 0) + e["cost_usd"]
            by_provider[e["provider"]] = by_provider.get(e["provider"], 0) + e["cost_usd"]
            ow += e["cost_usd"] if e["model"] in OPEN_WEIGHT_MODELS else 0
    (art / "costs.json").write_text(json.dumps({"by_model": by_model, "by_provider": by_provider, "total_usd": total,
                                                "open_weight_share": round(ow / total, 3) if total else 0, "fixture": True}))  # fmt: skip
    (run / "run.json").write_text(json.dumps({"run_id": run_id, "title": truth["summary"], "created_at": clock.tick(0),
                                              "source": f"synthetic:{src.name}", "mode": "replay", "status": "done",
                                              "fixture": True}, indent=1))  # fmt: skip
    (run / "state.json").write_text(json.dumps({"cursor": "card", "stages": stages}, indent=1))
    for big in ("display_raw.mp4", "analysis.mp4"):
        if a.bake:
            (art / big).unlink(missing_ok=True)
    print(
        f"{run}: {truth['summary']} | v2 demo ok={last.goal_ok}, robustness {rb:.2f}, simulated cost ${total}",
        file=sys.stderr,
    )
    if a.bake:
        dest = ROOT / "backend" / "tests" / "fixtures" / "runs" / run_id
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(run, dest, ignore=shutil.ignore_patterns("input", "*.video.mp4"))
        print(f"baked to {dest}", file=sys.stderr)


def _relpaths(res: SimResult, run: Path) -> SimResult:
    renders = {k: rel(run, v) for k, v in res.renders.items()}
    twin = rel(run, res.twin_trajectory) if res.twin_trajectory else None
    return res.model_copy(update={"renders": renders, "twin_trajectory": twin})


def _diff(a: str, b: str) -> str:
    import difflib

    return "".join(difflib.unified_diff(a.splitlines(True), b.splitlines(True), "v1.py", "v2.py"))


_ = AgentDecision

if __name__ == "__main__":
    main()
