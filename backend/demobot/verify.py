"""Stage 9: Verify, three ways plus a judge (docs/04 §9).

1. Symbolic: the goal on the simulated final state.
2. Real-world: the goal on the human's real final state (from Ground).
3. Perceptual: SAM 3.1 segments a render of the simulated final state taken from the real
   camera's reference pose, the masks go through the same homography and parallax, and the goal
   is checked on what SAM perceives: "it checks itself with the same eyes".
4. Judge: Muse Spark Open compares the real final frame with that render.
"""

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from demobot import gateway, goal_dsl, providers
from demobot.camera import apply_h, parallax_correct
from demobot.config import settings
from demobot.errors import DemoBotError
from demobot.events import RunContext
from demobot.llm import chat_text, jpeg_data_url, output_text, parse_json
from demobot.perceive import Instance, sam_image
from demobot.schemas import (
    Calibration,
    CheckResult,
    ClauseResult,
    GoalClause,
    GroundedDemo,
    JudgeVerdict,
    Layout,
    SceneObject,
    SimResult,
    TaskSpec,
    Verification,
)  # fmt: skip
from demobot.schemas_util import strict_schema

JUDGE_MIN_CONFIDENCE = 0.6


def clause_words(c: GoalClause) -> str:
    sel = c.select.name or (f"every {c.select.kind}" if c.select.kind else None) or \
        (f"every {c.select.role} object" if c.select.role else " and ".join(c.select.names or []))  # fmt: skip
    if c.pred == "swapped":
        return f"{sel} have swapped places"
    if c.pred == "collinear":
        return f"{sel} stand in a straight {'left-to-right row' if c.order_by != 'y' else 'front-to-back column'}"
    tgt = (c.target.name or c.target.kind or c.target.role) if c.target else str(c.point_cm)
    return f"{sel} {'is' if c.quant == 'the' else 'are'} {c.pred.replace('_', ' ')} the {tgt}"


def perceived_state(
    final: list[SceneObject], found: dict[str, Instance], cal: Calibration
) -> list[SceneObject]:
    """Simulated objects at the positions SAM saw in the render (reference camera pose)."""
    H = np.array(cal.H_img_to_table)
    cam = cal.camera
    out = []
    for o in final:
        inst = found.get(o.name)
        if inst is None:
            continue
        p = apply_h(H, np.array([inst.centroid]))[0]
        h = o.z if o.z > 0 else o.h / 2  # the visible centre's height above the table
        p = parallax_correct(p, cam.nadir_cm, cam.position_cm[2], h)
        out.append(o.model_copy(update={"x": round(float(p[0]), 2), "y": round(float(p[1]), 2)}))
    return out


def project(cal: Calibration, o: SceneObject) -> tuple[float, float]:
    """Where a simulated object's centre appears in the reference frame."""
    from demobot.calibrate import camera_of

    cam = camera_of(cal)
    uv = cam.project(np.array([[o.x, o.y, -(o.z if o.z > 0 else o.h / 2)]]))[0]
    return float(uv[0]), float(uv[1])


def clean_plate(run_dir: Path) -> Path:
    """The reference (last clean) frame with every tracked object inpainted away: the real,
    empty table seen by the real camera."""
    import cv2

    out = run_dir / "artifacts" / "clean_plate.jpg"
    if out.exists():
        return out
    img: Any = cv2.imread(str(run_dir / "artifacts" / "reference_frame.jpg"))
    mask: Any = np.zeros(img.shape[:2], np.uint8)
    fm = run_dir / "artifacts" / "final_masks.json"
    polys = (
        [m["poly"] for m in json.loads(fm.read_text()).values() if m.get("poly")]
        if fm.exists()
        else []
    )
    tr = json.loads((run_dir / "artifacts" / "tracks.json").read_text())
    for t in tr["tracks"]:  # the last tracked box of everything, the hand too
        box = next((f["bbox_px"] for f in reversed(t["frames"]) if f["bbox_px"]), None)
        if box:
            cv2.rectangle(
                mask,
                (int(box[0]) - 6, int(box[1]) - 6),
                (int(box[2]) + 6, int(box[3]) + 6),
                255,
                -1,
            )
    for poly in polys:
        cv2.fillPoly(mask, [np.array(poly, np.int32)], 255)
    mask = cv2.dilate(mask, np.ones((15, 15), np.uint8))
    plate = cv2.inpaint(img, mask, 9, cv2.INPAINT_TELEA)
    cv2.imwrite(str(out), plate, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return out


def composite(run_dir: Path, render: Path, mask: Path, out: Path) -> Path:
    """The simulated objects (render pixels under the object mask) on the clean real table."""
    import cv2

    plate: Any = cv2.imread(str(clean_plate(run_dir)))
    ren: Any = cv2.imread(str(render))
    m: Any = cv2.imread(str(mask), cv2.IMREAD_GRAYSCALE)
    m = m > 127
    if plate.shape != ren.shape:
        plate = cv2.resize(plate, (ren.shape[1], ren.shape[0]))
    plate[m] = ren[m]
    cv2.imwrite(str(out), plate, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return out


async def perceptual(ctx: RunContext, render: Path, sim_final: list[SceneObject], initial: list[SceneObject],
                     phrases: dict[str, str], goal: list[GoalClause], cal: Calibration,
                     real_seen: set[str] | None = None) -> tuple[CheckResult, dict[str, Any]]:  # fmt: skip
    """SAM on the camera-pose render; each object is matched to the nearest instance of its phrase."""
    real_seen = set(real_seen or [])
    found: dict[str, Instance] = {}
    by_phrase: dict[str, list[SceneObject]] = {}
    for o in sim_final:
        by_phrase.setdefault(phrases.get(o.name, o.name), []).append(o)
    for phrase, objs in by_phrase.items():
        insts = await sam_image(ctx, render, phrase)
        for o in objs:
            if not insts:
                break
            u, v = project(cal, o)
            best = min(insts, key=lambda i: math.hypot(i.centroid[0] - u, i.centroid[1] - v))
            if math.hypot(best.centroid[0] - u, best.centroid[1] - v) < 90:
                found[o.name] = best
                insts.remove(best)
    seen = perceived_state(sim_final, found, cal)
    # an object SAM could not see in the real final frame either (e.g. pens inside a cup) is
    # hidden in both views: consistent, so it is checked at its simulated position, and labelled
    hidden_both = [o for o in sim_final if o.name not in found and o.name not in real_seen]
    seen += hidden_both
    results = goal_dsl.evaluate(goal, goal_dsl.to_state(seen), goal_dsl.to_state(initial))
    # an object hidden inside a container SAM does see in the render looks like "inside"
    seen_boxes = [o for o in seen if o.is_open]
    in_seen_box = [o for o in sim_final if o.name not in found and o.name in real_seen
                   and any(goal_dsl.inside(o, c, sim=True)[0] for c in seen_boxes)]  # fmt: skip
    seen += in_seen_box
    results = goal_dsl.evaluate(goal, goal_dsl.to_state(seen), goal_dsl.to_state(initial))
    hidden_both += in_seen_box
    missing = [
        o.name
        for o in sim_final
        if o.name not in found and o.name in real_seen and o not in in_seen_box
    ]
    for r in results:  # an object seen for real but not in the render must not pass vacuously
        involved = [o for o in sim_final if goal_dsl.select(r.clause.select, {o.name: o})]
        lost = [o.name for o in involved if o.name in missing]
        hid = [o.name for o in involved if o in hidden_both]
        if hid:
            r.detail += f" ({', '.join(hid)} hidden from view: checked at the simulated position)"
        if lost:
            r.holds, r.code = False, "NOT_SEEN"
            r.detail = f"SAM saw {', '.join(lost)} in the real frame but not in the render"
    ok = goal_dsl.all_hold(results)
    masks = {n: {"box": i.box, "centroid": i.centroid, "poly": i.poly} for n, i in found.items()}
    return CheckResult(
        ok=ok,
        clauses=results,
        detail=f"SAM saw {len(found)}/{len(sim_final)} objects in the render",
    ), masks


async def judge(
    ctx: RunContext,
    real: Path,
    render: Path,
    goal: list[GoalClause],
    clauses: list[ClauseResult],
    objects: str = "",
) -> JudgeVerdict | None:
    words = "; ".join(clause_words(c) for c in goal)
    table = "\n".join(
        f"- {clause_words(r.clause)}: {'holds' if r.holds else 'fails'} ({r.detail})"
        for r in clauses
    )
    text = (
        "Image 1 is the real table after a person did a task. Image 2 is a simulated table after a robot did the same "
        "task (simple stand-in shapes, a robot is not shown). Same camera viewpoint.\n"
        f"Objects on the table (name: role): {objects}.\nThe goal: {words}.\nThe simulator's own check:\n{table}\n"
        "Does image 2 achieve the same goal as image 1? Judge the goal, not the exact shapes or colours. "
        'Return JSON {"same_goal_achieved": bool, "confidence": 0..1, "differences": [str], "suspected_error": str}.'
    )
    imgs = [jpeg_data_url(real), jpeg_data_url(render)]
    fmt = {
        "type": "json_schema",
        "json_schema": {
            "name": "JudgeVerdict",
            "schema": strict_schema(JudgeVerdict),
            "strict": True,
        },
    }
    chat_content = [{"type": "text", "text": text}] + [
        {"type": "image_url", "image_url": {"url": u}} for u in imgs
    ]
    req = {
        "stage": "judge",
        "text": text,
        "imgs": [gateway.sha256_file(real), gateway.sha256_file(render)],
    }

    def chat(provider: str, model: str) -> gateway.Call:
        return providers.chat_call(provider, model, affinity_key=ctx.run_id, messages=[{"role": "user", "content": chat_content}],
                                   response_format=fmt, max_tokens=3000)  # fmt: skip

    spark = providers.responses_call(
        settings.model_spark,
        input=[{"role": "user", "content": [{"type": "input_text", "text": text},
                                            *({"type": "input_image", "image_url": u} for u in imgs)]}],
        text={"format": {"type": "json_schema", "name": "JudgeVerdict", "schema": JudgeVerdict.model_json_schema()}},
        reasoning={"effort": "low"}, max_output_tokens=4000,
    )  # fmt: skip

    def validate(raw: Any) -> JudgeVerdict:
        t = output_text(raw) if "output" in raw else chat_text(raw)
        try:
            return JudgeVerdict.model_validate(parse_json(t, "verify"))
        except DemoBotError:
            raise
        except Exception as e:
            raise DemoBotError("INVALID_MODEL_OUTPUT", str(e)[:300], stage="verify") from e

    routes = [
        gateway.Route("baseten", settings.model_spark_open, req, 0.03, chat("baseten", settings.model_spark_open), "Muse Spark Open @ Baseten"),
        gateway.Route("modal", settings.model_spark_open_modal, req, 0.03, chat("modal", settings.model_spark_open_modal), "Muse Spark Open @ Modal"),
        gateway.Route("meta", settings.model_spark, req, 0.02, spark, "Muse Spark 1.3"),
    ]  # fmt: skip
    try:
        verdict, _ = await gateway.chain_call(
            ctx=ctx, purpose="judge", routes=routes, validate=validate
        )
    except DemoBotError as e:
        ctx.emit(
            "log", payload={"message": f"the judge is unavailable ({e.code}); three checks only"}
        )
        return None
    return verdict


def classify(
    symbolic: CheckResult, real: CheckResult, perc: CheckResult, verdict: JudgeVerdict | None
) -> str | None:
    if not real.ok:
        return "spec_mismatch"
    if not symbolic.ok:
        return "program_bug"
    if not perc.ok:
        return "perception_gap"
    if (
        verdict is not None
        and not verdict.same_goal_achieved
        and verdict.confidence >= JUDGE_MIN_CONFIDENCE
    ):
        return "judge_dissent"
    return None


async def verify(ctx: RunContext, run_dir: Path, spec: TaskSpec, grounded: GroundedDemo, layout: Layout,
                 sim: SimResult, cal: Calibration, phrases: dict[str, str], program_version: int) -> tuple[Verification, dict[str, Any]]:  # fmt: skip
    ctx = ctx.at("verify")
    symbolic = CheckResult(ok=sim.goal_ok, clauses=sim.goal_results,
                           detail="the goal on the simulated final state" + (f" (error: {sim.error_type})" if sim.error else ""))  # fmt: skip
    real = CheckResult(ok=goal_dsl.all_hold(grounded.real_world), clauses=grounded.real_world,
                       detail="the goal on your real final table, measured by SAM")  # fmt: skip
    render = run_dir / sim.renders["camera"] if sim.renders.get("camera") else None
    if render is None or not render.exists():
        raise DemoBotError("NO_RENDER", "the simulation has no camera-pose render", stage="verify")
    mask = run_dir / sim.renders["camera_mask"] if sim.renders.get("camera_mask") else None
    seen_img = render
    if (
        mask is not None
        and mask.exists()
        and (run_dir / "artifacts" / "reference_frame.jpg").exists()
    ):
        seen_img = composite(run_dir, render, mask, render.with_name("perceptual_input.jpg"))
    fm = run_dir / "artifacts" / "final_masks.json"
    real_seen = (
        set(json.loads(fm.read_text())) if fm.exists() else {o.name for o in sim.final_state}
    )
    perc, masks = await perceptual(
        ctx, seen_img, sim.final_state, layout.objects, phrases, spec.goal, cal, real_seen
    )
    real_img = run_dir / "artifacts" / "reference_frame.jpg"
    verdict = (
        await judge(
            ctx,
            real_img,
            render,
            spec.goal,
            sim.goal_results,
            "; ".join(f"{o.name}: {o.role}" for o in spec.objects),
        )
        if real_img.exists()
        else None
    )
    failure = classify(symbolic, real, perc, verdict)
    ver = Verification(
        program_version=program_version, symbolic=symbolic, real_world=real, perceptual=perc, judge=verdict,
        agree=failure is None, failure_class=failure,
        renders={"real": "artifacts/reference_frame.jpg", "camera": sim.renders.get("camera", ""), "top": sim.renders.get("top", ""),
                 "perceptual_input": str(seen_img.relative_to(run_dir))},
    )  # fmt: skip
    return ver, masks


_ = json
