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
    TaskSpec,
    Transcript,
)  # fmt: skip


async def correct(run: Any, text: str = "", audio: Path | None = None) -> dict[str, Any]:
    """Apply a correction to a finished run; returns a summary record (also correction_<n>.json)."""
    from demobot import pipeline
    from demobot.agents import redteam

    ctx = run.ctx.at("correct")
    n = len(list(run.art.glob("correction_*.json"))) + 1
    ctx.emit("stage_start", payload={"correction": n})
    spec = run.read("taskspec.json", TaskSpec)
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
    current = pipeline.latest_program(run)
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
    if out.goal is not None:
        (run.art / f"taskspec_before_correction_{n}.json").write_text(
            spec.model_dump_json(indent=1)
        )
        run.write("taskspec.json", spec.model_copy(update={"goal": goal_after}))
    run.update_meta(program_version=out.program.version)
    others = [lay for k, lay in layouts.items() if k != "demo"]
    results = (
        await redteam.simulate_all(
            run.ctx, out.program.code, others, goal_after, out.program.version, tag="correct"
        )
        if others
        else []
    )
    passed = sum(r.goal_ok for r in results)
    record = {
        "n": n, "transcript": tr.model_dump(), "gloss": out.gloss, "program_before": current.version,
        "program_after": out.program.version, "goal_before": [c.model_dump(exclude_none=True) for c in goal_before],
        "goal_after": [c.model_dump(exclude_none=True) for c in goal_after], "demo_passes": True,
        "stress_passed": f"{passed}/{len(results)}", "real_world": "superseded: the correction changes the goal the demo showed",
    }  # fmt: skip
    path = run.art / f"correction_{n}.json"
    path.write_text(json.dumps(record, indent=1))
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
