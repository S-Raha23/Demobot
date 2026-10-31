"""Corrections, spoken or typed (docs/04 §12): "No, the eraser goes to the left of the mug."

Voice Transcribe turns speech (English, Hindi, Bengali) into text; Muse Wonder applies it as a goal
change plus a new program version, with the simulator in the loop; the new program is checked on
the demo layout and every red-team layout. The goal diff and the code diff are events.
"""

import json
from pathlib import Path
from typing import Any

from demobot import listen, media
from demobot.errors import DemoBotError
from demobot.program import synth
from demobot.schemas import (
    Calibration,
    GroundedDemo,
    IngestInfo,
    StressReport,
    Transcript,
)  # fmt: skip


async def correct(run: Any, text: str = "", audio: Path | None = None) -> dict[str, Any]:
    """Apply a correction to a finished run; returns a summary record (also correction_<n>.json)."""
    from demobot import pipeline
    from demobot.agents import redteam

    ctx = run.ctx.at("correct")
    n = len(list(run.art.glob("correction_*.json"))) + 1
    ctx.emit("stage_start", payload={"correction": n})
    from demobot import versions

    vs = versions.load(run.dir)
    base = vs[-1]  # a correction builds on the newest version of the skill, and never overwrites it
    spec = versions.spec(run.dir, base)
    if audio is not None:
        wav = run.art / f"correction_{n}.wav"
        media.to_wav(audio, wav)
        names = [o.name for o in spec.objects] + [o.kind for o in spec.objects]
        tr = await listen.transcribe(
            ctx, wav, keywords=[*listen.KEYWORDS, *names], source="correction"
        )
    else:
        tr = Transcript(text=text, language=listen.detect_language(text), source="correction")
    if not tr.text.strip():
        raise DemoBotError(
            "EMPTY_CORRECTION", "no words were heard; please try again", stage="correct", http=422
        )
    ctx.emit("artifact", payload={"name": "correction_transcript", "path": "", "kind": "json", "label": "You said",
                                  "text": tr.text, "language": tr.language})  # fmt: skip

    gd = run.read("grounded.json", GroundedDemo)
    info = run.read("ingest.json", IngestInfo)
    cal = run.read("calibration.json", Calibration)
    demo = pipeline.textured(run, pipeline.repair(pipeline.demo_layout(run))[0])
    current = versions.program(run.dir, base) or pipeline.latest_program(run)
    stress = run.read("stress.json", StressReport) if (run.art / "stress.json").exists() else None
    layouts = {"demo": demo} | ({c.layout.id: c.layout for c in stress.cases} if stress else {})
    previous = json.loads((run.art / "programs.json").read_text())
    kf = list(zip(info.keyframe_times, [run.art / k for k in info.keyframes], strict=True))
    brief = (
        f"## Correction from the person ({tr.language})\n\"{tr.text}\"\n"
        "The person watched the robot and wants a change. If it changes what should be true at the end (it usually does), "
        "call update_goal first with the corrected goal and an English gloss; then change the program, simulate it on "
        "\"demo\" (and a red-team layout or two), and submit."
    )  # fmt: skip
    si = synth.SynthInput(spec=spec, grounded=gd, layouts=layouts, transcript=tr, keyframes=[kf[0], kf[-1]] if kf else [],
                          calibration_json=cal.model_dump_json(), art=run.art, mode="correct", start_code=current.code,
                          extra=brief, first_version=len(previous) + 1, drafts=False)  # fmt: skip
    out = await synth.synthesize(ctx, si)
    (run.art / "programs.json").write_text(
        json.dumps(previous + [json.loads(p.model_dump_json()) for p in out.versions], indent=1)
    )
    if out.program is None or not out.program.passed_demo:
        ctx.emit(
            "stage_end", payload={"ok": False, "summary": "the correction could not be applied"}
        )
        raise DemoBotError(
            "CORRECTION_FAILED", "no corrected program passed the demo", stage="correct"
        )
    goal_before = spec.goal
    goal_after = out.goal or spec.goal
    gloss = (out.gloss or "").strip()
    update: dict[str, object] = {"goal": goal_after}
    if gloss:  # the new version does what the person said, so it is described that way
        update |= {
            "summary": gloss[0].upper() + gloss[1:],
            "generalization": f"{gloss.rstrip('.')}, wherever things start.",
        }
    new_v = len(vs) + 1
    spec_file = f"taskspec_v{new_v}.json"
    (run.art / spec_file).write_text(spec.model_copy(update=update).model_dump_json(indent=1))
    others = [lay for k, lay in layouts.items() if k != "demo"]
    results = (
        await redteam.simulate_all(
            run.ctx, out.program.code, others, goal_after, out.program.version, tag="correct"
        )
        if others
        else []
    )
    passed = sum(r.goal_ok for r in results)
    failing = [(lay, r) for lay, r in zip(others, results, strict=True) if not r.goal_ok]
    if failing:  # one hardening round for the corrected program (bounded: one synthesis)
        prog_list = json.loads((run.art / "programs.json").read_text())
        hi = synth.SynthInput(spec=spec.model_copy(update={"goal": goal_after}), grounded=gd,
                              layouts={"demo": layouts["demo"]} | {lay.id: lay for lay, _ in failing},
                              transcript=tr, keyframes=[kf[0], kf[-1]] if kf else [], calibration_json=cal.model_dump_json(),
                              art=run.art, mode="harden", start_code=out.program.code, extra=redteam.harden_brief(failing),
                              first_version=len(prog_list) + 1, drafts=False)  # fmt: skip
        hard = await synth.synthesize(ctx, hi)
        (run.art / "programs.json").write_text(
            json.dumps(
                prog_list + [json.loads(p.model_dump_json()) for p in hard.versions], indent=1
            )
        )
        if hard.program is not None and hard.program.passed_demo:
            res2 = await redteam.simulate_all(
                run.ctx, hard.program.code, others, goal_after, hard.program.version, tag="correct"
            )
            if sum(r.goal_ok for r in res2) > passed:
                out.program, results, passed = hard.program, res2, sum(r.goal_ok for r in res2)
    record = {
        "n": n, "transcript": tr.model_dump(), "gloss": out.gloss, "program_before": current.version,
        "program_after": out.program.version, "goal_before": [c.model_dump(exclude_none=True) for c in goal_before],
        "goal_after": [c.model_dump(exclude_none=True) for c in goal_after], "demo_passes": True,
        "stress_passed": f"{passed}/{len(results)}", "real_world": "superseded: the correction changes the goal the demo showed",
    }  # fmt: skip
    record |= {"version": new_v, "taskspec": spec_file}
    path = run.art / f"correction_{n}.json"
    path.write_text(json.dumps(record, indent=1))
    how = "voice" if audio is not None else "text"
    title = str(update.get("summary") or spec.summary).rstrip(".")
    versions.save(run.dir, [*vs, {"version": new_v, "label": f"corrected by {how}", "title": title, "taskspec": spec_file,
                                  "program_version": out.program.version, "said": tr.text, "language": tr.language,
                                  "from_version": base["version"]}])  # fmt: skip
    ctx.emit(
        "artifact",
        payload={
            "name": "skills.json",
            "path": "artifacts/skills.json",
            "kind": "json",
            "label": "Skill versions",
        },
    )
    ctx.emit(
        "artifact",
        payload={
            "name": path.name,
            "path": f"artifacts/{path.name}",
            "kind": "json",
            "label": "Correction",
        },
    )
    summary = (
        f"v{current.version} → v{out.program.version}: demo ✓, red-team {passed}/{len(results)}"
    )
    ctx.emit("stage_end", payload={"ok": True, "summary": summary})
    return record
