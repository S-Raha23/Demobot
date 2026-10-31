"""Compute every metric of docs/09 from the run artifacts and write eval/results.md.

    uv run python -m eval.run_eval [--set data/synth/set7] [--runs syn7-] [--real real-]

No model calls: it reads finished runs (data/runs/<prefix>*) and the saved acceptance files. Every
number in the README and the video is copied from the generated file, which records the date and
the git SHA.
"""

import argparse
import json
import statistics as st
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from demobot import goal_dsl
from demobot.config import OPEN_WEIGHT_MODELS, ROOT, settings
from demobot.events import read_events
from demobot.schemas import GroundedDemo, StressReport, TaskSpec, Verification

RUNS = settings.data_path / "runs"


def _json(p: Path) -> Any:
    return json.loads(p.read_text()) if p.exists() else None


def pct(x: float | None) -> str:
    return "–" if x is None else f"{100 * x:.0f}%"


def mean(xs: list[float]) -> float | None:
    return st.mean(xs) if xs else None


def run_metrics(d: Path, truth: dict[str, Any] | None) -> dict[str, Any]:
    art = d / "artifacts"
    state = (_json(d / "state.json") or {}).get("stages", {})
    m: dict[str, Any] = {"run": d.name, "done": state.get("card") == "done"}
    spec = (
        TaskSpec.model_validate_json((art / "taskspec.json").read_text())
        if (art / "taskspec.json").exists()
        else None
    )
    if truth and spec:
        from eval.understanding_synth import map_objects, states

        t0 = (_json(art / "ingest.json") or {}).get("trim_start_s", 0.0)
        mp = map_objects(spec, truth, t0)
        init, final = states(spec, truth, mp)
        m["goal_correct"] = goal_dsl.all_hold(goal_dsl.evaluate(spec.goal, final, init)) and not goal_dsl.all_hold(
            goal_dsl.evaluate(spec.goal, init, init))  # fmt: skip
    cross = _json(art / "crosswatch.json")
    if cross and cross.get("agreement") is not None:
        m["crosswatch_agreement"] = cross["agreement"]
    tr = _json(art / "tracks.json")
    if tr:
        objs = [t for t in tr["tracks"] if t["name"] != "hand"]
        m["track_quality"] = mean([t["quality"] for t in objs])
        m["tracked"] = mean([0.0 if "not_found" in t["flags"] else 1.0 for t in objs])
    if (art / "grounded.json").exists():
        gd = GroundedDemo.model_validate_json((art / "grounded.json").read_text())
        m["real_world_ok"] = goal_dsl.all_hold(gd.real_world)
        if truth:
            from eval.grounding_synth import score

            g = score(Path(truth["_dir"]), d)
            m["start_err"], m["end_err"] = g["start_err_median"], g["end_err_median"]
    trace = _json(art / "synthesis_trace.json")
    if trace:
        m["coder_turns"] = trace.get("turns")
        m["submitted"] = trace.get("submitted")
        m["winner"] = trace.get("winner")
    if (art / "programs.json").exists():
        m["program_ok"] = state.get("program") == "done"
    if (art / "verify.json").exists():
        v = Verification.model_validate_json((art / "verify.json").read_text())
        m["verify_agree"] = v.agree
        m["verify_accepted_caveat"] = bool(v.accepted_caveat)
        m["perceptual_inconclusive"] = v.perceptual.inconclusive
        m["judge_agrees"] = None if v.judge is None else v.judge.same_goal_achieved
        m["sym_perc_agree"] = v.symbolic.ok == v.perceptual.ok
    if (art / "stress.json").exists():
        r = StressReport.model_validate_json((art / "stress.json").read_text())
        m["robust_before"] = r.robustness_before
        m["robust_after"] = (
            r.robustness_after if r.robustness_after is not None else r.robustness_before
        )
        m["stress_layouts"] = len(r.cases)
    corr = sorted(art.glob("correction_[0-9]*.json"))
    if corr:
        m["corrections"] = len(corr)
        m["corrections_ok"] = sum(bool((_json(c) or {}).get("demo_passes")) for c in corr)
    costs = _json(art / "costs.json")
    if costs:
        m["cost"] = costs["total_usd"]
        m["by_provider"] = costs["by_provider"]
        m["by_model"] = costs["by_model"]
    calls = open_calls = 0
    secs = 0.0
    last: dict[str, float] = {}
    for e in read_events(d / "events.jsonl"):
        if e.type == "model_call":
            calls += 1
            open_calls += e.model in OPEN_WEIGHT_MODELS
        if e.type == "stage_end" and "duration_s" in e.payload:
            last[e.stage] = float(
                e.payload["duration_s"]
            )  # the last (successful) run of each stage
    secs = sum(last.values())
    m["calls"], m["open_calls"], m["pipeline_s"] = calls, open_calls, round(secs, 1)
    return m


def git_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()


def section(title: str, rows: list[dict[str, Any]], extra: dict[str, Any]) -> list[str]:
    done = [r for r in rows if r.get("done")]

    def avg(key: str) -> float | None:
        vals = [float(r[key]) for r in rows if r.get(key) is not None]
        return mean(vals)

    L = [
        f"## {title}",
        "",
        f"{len(rows)} clips; {len(done)} finished end to end (ingest → card).",
        "",
    ]
    L += ["| Metric | Value | Definition |", "| --- | --- | --- |"]
    if any("goal_correct" in r for r in rows):
        n = sum(bool(r.get("goal_correct")) for r in rows if "goal_correct" in r)
        k = sum("goal_correct" in r for r in rows)
        L.append(
            f"| Goal accuracy (Watch) | **{n}/{k}** | the TaskSpec goal holds on the true final state and not on the true initial state |"
        )
    ca = [r["crosswatch_agreement"] for r in rows if "crosswatch_agreement" in r]
    if ca:
        L.append(
            f"| Cross-model agreement | **{pct(mean(ca))}** mean; {sum(a == 1.0 for a in ca)}/{len(ca)} identical | Spark 1.3 vs Spark Open step agreement, before arbitration |"
        )
    if avg("track_quality") is not None:
        L.append(
            f"| Tracking quality | **{avg('track_quality'):.2f}** mean; {pct(avg('tracked'))} of objects tracked | fraction of frames with a SAM box, per object |"
        )
    se = [r["start_err"] for r in rows if r.get("start_err") is not None]
    ee = [r["end_err"] for r in rows if r.get("end_err") is not None]
    if se:
        L.append(
            f"| Grounding error | start **{np.median(se):.2f} cm** (p90 {np.percentile(se, 90):.2f}), end **{np.median(ee):.2f} cm** (p90 {np.percentile(ee, 90):.2f}) | moved objects vs exact synthetic truth |"
        )
    rw = [r["real_world_ok"] for r in rows if "real_world_ok" in r]
    if rw:
        L.append(
            f"| Real-world check | **{sum(rw)}/{len(rw)}** | the goal holds on the measured real final state |"
        )
    po = [r["program_ok"] for r in rows if "program_ok" in r]
    if po:
        L.append(
            f"| Program success | **{sum(po)}/{len(po)}** pass the demo; {avg('coder_turns') or 0:.1f} Wonder turns on average | after the coder loop (incl. the supervisor's reprogram) |"
        )
    va = [r for r in rows if "verify_agree" in r]
    if va:
        acc = sum(r["verify_agree"] or r["verify_accepted_caveat"] for r in va)
        L.append(
            f"| Verification | **{sum(r['verify_agree'] for r in va)}/{len(va)}** all checks agree; {acc}/{len(va)} accepted (incl. supervisor caveats); judge agrees on {sum(bool(r['judge_agrees']) for r in va)}/{len(va)}; perceptual inconclusive on {sum(bool(r['perceptual_inconclusive']) for r in va)}/{len(va)} | symbolic, real-world, perceptual, judge |"
        )
    rb, ra = avg("robust_before"), avg("robust_after")
    if rb is not None:
        improved = sum(
            1
            for r in rows
            if r.get("robust_after") is not None
            and r.get("robust_before") is not None
            and r["robust_after"] > r["robust_before"]
        )
        L.append(
            f"| Robustness | **{pct(rb)} → {pct(ra)}** (mean over {sum(r.get('robust_before') is not None for r in rows)} skills; improved on {improved}) | red-team pass rate before and after hardening |"
        )
    if any("corrections" in r for r in rows):
        c = sum(r.get("corrections", 0) for r in rows)
        ok = sum(r.get("corrections_ok", 0) for r in rows)
        L.append(
            f"| Correction success | **{ok}/{c}** | corrections applied and verified on the demo |"
        )
    costs = [r["cost"] for r in done if r.get("cost") is not None]
    if costs:
        calls = sum(r["calls"] for r in done)
        open_calls = sum(r["open_calls"] for r in done)
        L.append(
            f"| Cost per skill | **${st.mean(costs):.2f}** mean (min ${min(costs):.2f}, max ${max(costs):.2f}) | spend of the run's own model calls (cache hits count $0) |"
        )
        L.append(
            f"| Open-weight share | **{pct(open_calls / calls if calls else None)}** of model calls | Muse Spark Open on Baseten and Modal |"
        )
    ps = [r["pipeline_s"] for r in done if r.get("pipeline_s")]
    if ps:
        L.append(
            f"| Time per skill | **{st.mean(ps) / 60:.1f} min** mean | sum of stage times from upload to the skill card |"
        )
    wins = [r["winner"] for r in rows if r.get("winner")]
    if wins:
        L.append(
            f"| Best-of-N | Wonder {wins.count('wonder')}, Spark Open draft {wins.count('spark-open-draft')} | whose program was submitted |"
        )
    for k, v in extra.items():
        L.append(f"| {k} | {v[0]} | {v[1]} |")
    if done:
        prov: dict[str, float] = {}
        for r in done:
            for p, c in (r.get("by_provider") or {}).items():
                prov[p] = prov.get(p, 0) + c
        L += [
            "",
            "Spend by provider over these runs: "
            + ", ".join(f"{p} ${c:.2f}" for p, c in sorted(prov.items()))
            + ".",
        ]
    return [*L, ""]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="data/synth/set7")
    ap.add_argument("--runs", default="syn7-")
    ap.add_argument("--real", default="real-")
    a = ap.parse_args()
    set_dir = ROOT / a.set
    rows = []
    for d in sorted(RUNS.glob(f"{a.runs}*")):
        clip = set_dir / d.name.removeprefix(a.runs)
        truth = _json(clip / "truth.json")
        if truth:
            truth["_dir"] = str(clip)
        rows.append(run_metrics(d, truth))
    extra: dict[str, tuple[str, str]] = {}
    cal = _json(set_dir / "calibration_eval.json")
    if cal:
        extra["Calibration (handheld)"] = (
            f"**{sum(r['pass'] for r in cal)}/{len(cal)}** pass; marker error ≤ {max(r['marker_err_cm'] for r in cal):.2f} cm, reprojection ≤ {max(r['reprojection_px'] for r in cal):.2f} px",
            "marker error < 0.8 cm and reprojection < 1.5 px",
        )  # fmt: skip
    fi = _json(RUNS / "syn7-01_next_to/artifacts/fault_injection.json")
    if fi:
        exact = sum(r["got"] == r["expected"] for r in fi)
        extra["Fault injection (verify)"] = (f"**{sum(bool(r['correct']) for r in fi)}/{len(fi)}** caught; {exact}/{len(fi)} with the exact class",
                                             "5 injected faults; the failure class verification assigns")  # fmt: skip
    si = _json(settings.data_path / "supervisor_injection.json")
    if si:
        extra["Supervisor recovery"] = (
            f"**{sum(bool(r['recovered']) for r in si)}/{len(si)}**",
            "injected failures the supervisor recovered from",
        )
    real_rows = [run_metrics(d, None) for d in sorted(RUNS.glob(f"{a.real}*"))]
    sha = git_sha()
    now = datetime.now(UTC).astimezone().strftime("%a %b %d %Y, %H:%M %Z")
    L = ["# DemoBot evaluation results", "",
         f"Generated by `eval/run_eval.py` on {now} at git `{sha}`. Every number in the README and the video is copied from this file.", ""]  # fmt: skip
    if real_rows:
        L += section("Real clips (the human's desk, handheld phone)", real_rows, {})
    else:
        L += [
            "## Real clips",
            "",
            "Not yet: the real clips have not arrived. This section is generated once they are run.",
            "",
        ]
    L += section("Synthetic clips (exact ground truth)", rows, extra)
    L += ["Synthetic clips are rendered by `synth/` with the human's real objects and handheld shake; their model calls are real.",
          "Costs include re-runs made while developing, except where cached (cache hits are $0).", ""]  # fmt: skip
    out = ROOT / "eval" / "results.md"
    out.write_text("\n".join(L))
    (ROOT / "eval" / "results.json").write_text(
        json.dumps({"sha": sha, "synthetic": rows, "real": real_rows}, indent=1, default=str)
    )
    print(out.read_text())


if __name__ == "__main__":
    sys.exit(main())
