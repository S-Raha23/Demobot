"""Stage 4: Watch. Muse Spark 1.3 turns the demo video (plus narration) into a TaskSpec; Muse
Spark Open on Modal watches it independently; Muse Wonder arbitrates when they disagree
(docs/04 §4)."""

import asyncio
import difflib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from demobot import gateway, providers
from demobot.config import settings, token_cost
from demobot.errors import DemoBotError
from demobot.events import RunContext
from demobot.llm import chat_text, jpeg_data_url, output_text, parse_json, prompt, video_data_url
from demobot.schemas import AgentDecision, IngestInfo, TaskSpec, Transcript
from demobot.schemas_util import strict_schema

WATCH_MAX_OUT = 16000
OPEN_MAX_OUT = 8000
ESTIMATE = {"watch": 0.17, "crosswatch": 0.10, "arbitrate": 0.40, "repair": 0.12}


class Arbitration(BaseModel):
    spec: TaskSpec
    reason: str


# ---------- checks ----------
def check_spec(spec: TaskSpec, duration_s: float) -> list[str]:
    """Semantic checks after schema validation; an empty list means the spec is usable."""
    problems: list[str] = []
    names = [o.name for o in spec.objects]
    by_name = {o.name: o for o in spec.objects}
    if len(set(names)) != len(names):
        problems.append("object names are not unique")
    if not spec.steps:
        problems.append("no steps: at least one object must be moved")
    last = -1.0
    for i, s in enumerate(spec.steps):
        if s.object not in by_name:
            problems.append(f"step {i}: object {s.object!r} is not in objects")
        if s.target is not None and s.target not in by_name:
            problems.append(f"step {i}: target {s.target!r} is not in objects")
        if s.action == "place_in" and s.target in by_name and by_name[s.target].role != "container":
            problems.append(f"step {i}: place_in target {s.target!r} must have role container")
        if s.action == "place_next_to" and (s.target is None or s.relation is None):
            problems.append(f"step {i}: place_next_to needs a target and a relation")
        if not (0 <= s.t_start <= s.t_end <= duration_s + 0.5):
            problems.append(
                f"step {i}: times {s.t_start}-{s.t_end} s are outside the {duration_s:.1f} s video"
            )
        if s.t_start + 0.05 < last:
            problems.append(f"step {i}: steps are not in time order")
        last = s.t_start
    if not spec.goal:
        problems.append("the goal is empty")
    for i, c in enumerate(spec.goal):
        sels = [c.select] + ([c.target] if c.target else [])
        for sel in sels:
            if sel.name and sel.name not in by_name:
                problems.append(f"goal clause {i}: {sel.name!r} is not in objects")
            if sel.names and any(n not in by_name for n in sel.names):
                problems.append(f"goal clause {i}: {sel.names} not all in objects")
            if sel.kind and not any(o.kind == sel.kind for o in spec.objects):
                problems.append(f"goal clause {i}: no object of kind {sel.kind!r}")
            if sel.role and not any(o.role == sel.role for o in spec.objects):
                problems.append(f"goal clause {i}: no object with role {sel.role!r}")
    return problems


# ---------- requests ----------
def _user_text(transcript: Transcript, duration_s: float) -> str:
    said = (
        f'The person said: "{transcript.text}" ({transcript.language}).'
        if transcript.text
        else "There is no narration."
    )
    return f"The video lasts {duration_s:.1f} s. {said} Return the TaskSpec as JSON."


def _validate_spec(stage: str):
    def validate(raw: Any) -> TaskSpec:
        text = output_text(raw) if "output" in raw else chat_text(raw)
        try:
            return TaskSpec.model_validate(parse_json(text, stage))
        except DemoBotError:
            raise
        except Exception as e:
            raise DemoBotError(
                "INVALID_MODEL_OUTPUT", f"TaskSpec: {str(e)[:400]}", stage=stage
            ) from e

    return validate


def _keyframe_parts(art: Path, info: IngestInfo, kind: str) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    for path, t in zip(info.keyframes, info.keyframe_times, strict=True):
        url = jpeg_data_url(art / path)
        if kind == "responses":
            parts += [
                {"type": "input_text", "text": f"t = {t:.1f} s"},
                {"type": "input_image", "image_url": url},
            ]
        else:
            parts += [
                {"type": "text", "text": f"t = {t:.1f} s"},
                {"type": "image_url", "image_url": {"url": url}},
            ]
    return parts


def _routes(ctx: RunContext, art: Path, info: IngestInfo, transcript: Transcript, extra: str,
            purpose: str) -> list[gateway.Route]:  # fmt: skip
    """Spark 1.3 on the video, then Wonder on keyframes (docs/03 'watch' chain)."""
    text, sha = prompt("watch")
    clip = art / "analysis.mp4"
    clip_sha = gateway.sha256_file(clip)
    user = _user_text(transcript, info.duration_s) + extra
    schema = {
        "format": {
            "type": "json_schema",
            "name": "TaskSpec",
            "schema": TaskSpec.model_json_schema(),
        }
    }

    async def spark(timeout: float) -> tuple[Any, float, dict[str, Any]]:
        fid = await providers.upload_file(clip, clip_sha)
        call = providers.responses_call(
            settings.model_spark,
            input=[{"role": "system", "content": text},
                   {"role": "user", "content": [{"type": "input_text", "text": user},
                                                {"type": "input_file", "file_id": fid}]}],
            text=schema, reasoning={"effort": "high"}, max_output_tokens=WATCH_MAX_OUT,
        )  # fmt: skip
        return await call(timeout)

    wonder = providers.responses_call(
        settings.model_wonder,
        input=[{"role": "system", "content": text},
               {"role": "user", "content": [{"type": "input_text", "text": user + " (Keyframes in time order.)"},
                                            *_keyframe_parts(art, info, "responses")]}],
        text=schema, reasoning={"effort": "high"}, max_output_tokens=WATCH_MAX_OUT,
    )  # fmt: skip
    base = {"stage": purpose, "prompt": sha, "clip": clip_sha, "user": user, "effort": "high"}
    return [
        gateway.Route("meta", settings.model_spark, {**base, "input": "video"}, ESTIMATE["watch"], spark,
                      "Muse Spark 1.3 (video)"),
        gateway.Route("meta", settings.model_wonder, {**base, "input": "keyframes"}, ESTIMATE["arbitrate"],
                      wonder, "Muse Wonder (keyframes)"),
    ]  # fmt: skip


async def spark_watch(
    ctx: RunContext, art: Path, info: IngestInfo, transcript: Transcript
) -> tuple[TaskSpec, str]:
    """The primary TaskSpec, with one repair turn if the semantic checks fail."""
    spec, route = await gateway.chain_call(
        ctx=ctx, purpose="watch", routes=_routes(ctx, art, info, transcript, "", "watch"),
        validate=_validate_spec("watch"),
    )  # fmt: skip
    problems = check_spec(spec, info.duration_s)
    if not problems:
        return spec, route.name()
    ctx.emit("log", payload={"message": f"TaskSpec needs repair: {'; '.join(problems)[:300]}"})
    extra = (
        "\n\nYour previous answer had these problems:\n- " + "\n- ".join(problems)
        + "\nPrevious answer:\n" + spec.model_dump_json() + "\nReturn a corrected TaskSpec."
    )  # fmt: skip
    routes = [
        r
        for r in _routes(ctx, art, info, transcript, extra, "watch-repair")
        if r.model == route.model
    ]
    spec, _ = await gateway.chain_call(
        ctx=ctx, purpose="watch", routes=routes, validate=_validate_spec("watch")
    )
    problems = check_spec(spec, info.duration_s)
    if problems:
        raise DemoBotError("INVALID_TASKSPEC", "; ".join(problems)[:500], stage="watch")
    return spec, route.name()


async def cross_watch(
    ctx: RunContext, art: Path, info: IngestInfo, transcript: Transcript
) -> TaskSpec | None:
    """The second opinion: Spark Open on Modal with the video, else Baseten with keyframes,
    else skipped (logged)."""
    text, sha = prompt("watch")
    clip = art / "analysis.mp4"
    user = _user_text(transcript, info.duration_s)
    fmt = {
        "type": "json_schema",
        "json_schema": {"name": "TaskSpec", "schema": strict_schema(TaskSpec), "strict": True},
    }
    base = {"stage": "crosswatch", "prompt": sha, "clip": gateway.sha256_file(clip), "user": user}
    modal = providers.chat_call(
        "modal", settings.model_spark_open_modal, affinity_key=ctx.run_id,
        messages=[{"role": "system", "content": text},
                  {"role": "user", "content": [{"type": "text", "text": user},
                                               {"type": "video_url", "video_url": {"url": video_data_url(clip)}}]}],
        response_format=fmt, max_tokens=OPEN_MAX_OUT,
    )  # fmt: skip
    baseten = providers.chat_call(
        "baseten", settings.model_spark_open,
        messages=[{"role": "system", "content": text},
                  {"role": "user", "content": [{"type": "text", "text": user + " (Keyframes in time order.)"},
                                               *_keyframe_parts(art, info, "chat")]}],
        response_format=fmt, max_tokens=OPEN_MAX_OUT,
    )  # fmt: skip
    routes = [
        gateway.Route("modal", settings.model_spark_open_modal, {**base, "input": "video"}, ESTIMATE["crosswatch"],
                      modal, "Muse Spark Open @ Modal (video)"),
        gateway.Route("baseten", settings.model_spark_open, {**base, "input": "keyframes"}, ESTIMATE["crosswatch"],
                      baseten, "Muse Spark Open @ Baseten (keyframes)"),
    ]  # fmt: skip
    try:
        spec, _ = await gateway.chain_call(ctx=ctx, purpose="crosswatch", routes=routes,
                                           validate=_validate_spec("crosswatch"))  # fmt: skip
    except DemoBotError as e:
        ctx.emit("log", payload={"fallback": True, "purpose": "crosswatch", "from": "Muse Spark Open",
                                 "to": "skipped", "code": e.code, "message": f"cross-watch skipped ({e.code})"})  # fmt: skip
        return None
    return spec


# ---------- comparison ----------
def _sim(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def name_map(a: TaskSpec, b: TaskSpec) -> dict[str, str]:
    """B's object names -> A's. First through steps that overlap in time (same moved object,
    same target), then by role, kind and fuzzy name for the rest (greedy, best pairs first)."""
    out: dict[str, str] = {}
    used: set[str] = set()
    for sb in b.steps:
        best = max(
            a.steps,
            key=lambda sa: min(sa.t_end, sb.t_end) - max(sa.t_start, sb.t_start),
            default=None,
        )
        if best is None or min(best.t_end, sb.t_end) - max(best.t_start, sb.t_start) <= 0:
            continue
        for nb, na in ((sb.object, best.object), (sb.target, best.target)):
            if nb and na and nb not in out and na not in used:
                out[nb] = na
                used.add(na)
    roles_a = {o.name: o for o in a.objects}
    pairs = []
    for ob in b.objects:
        if ob.name in out:
            continue
        for oa in a.objects:
            if oa.name in used:
                continue
            score = (
                0.3 * (oa.role == ob.role)
                + 0.35 * (oa.kind.lower() == ob.kind.lower())
                + 0.35 * _sim(oa.name, ob.name)
            )
            pairs.append((score, ob.name, oa.name))
    for score, nb, na in sorted(pairs, reverse=True):
        if score >= 0.5 and nb not in out and na not in used:
            out[nb] = na
            used.add(na)
    _ = roles_a
    return out


def compare(a: TaskSpec, b: TaskSpec) -> tuple[float, list[str]]:
    """Agreement = matched steps (action, object, target, relation) over the union of steps.
    Naming differences are reported but do not lower the agreement."""
    m = name_map(a, b)
    key_a = [(s.action, s.object, s.target, s.relation) for s in a.steps]
    key_b = [(s.action, m.get(s.object, "?" + s.object), m.get(s.target, "?" + s.target) if s.target else None,
              s.relation) for s in b.steps]  # fmt: skip
    remaining = list(key_b)
    matched = 0
    for k in key_a:
        if k in remaining:
            remaining.remove(k)
            matched += 1
    union = len(key_a) + len(key_b) - matched
    agreement = matched / union if union else 1.0
    diffs = []
    for k in key_a:
        if k not in key_b:
            diffs.append(
                f"only A: {k[0]} {k[1]}"
                + (f" → {k[2]}" if k[2] else "")
                + (f" ({k[3]})" if k[3] else "")
            )
    for k in remaining:
        diffs.append(
            f"only B: {k[0]} {k[1]}"
            + (f" → {k[2]}" if k[2] else "")
            + (f" ({k[3]})" if k[3] else "")
        )
    unmatched = [o.name for o in b.objects if o.name not in m]
    if unmatched:
        diffs.append(f"objects only in B: {', '.join(unmatched)}")
    renamed = [f"{na} / {nb}" for nb, na in m.items() if na != nb]
    if renamed:
        diffs.append(f"named differently (A / B): {', '.join(renamed)}")
    ga = {(c.pred, c.quant) for c in a.goal}
    gb = {(c.pred, c.quant) for c in b.goal}
    if ga != gb:
        diffs.append(f"goal predicates differ: A {sorted(ga)} vs B {sorted(gb)}")
        agreement = min(agreement, 0.99)  # same steps but a different goal still needs arbitration
    return round(agreement, 3), diffs


async def arbitrate(ctx: RunContext, art: Path, info: IngestInfo, transcript: Transcript, a: TaskSpec,
                    b: TaskSpec, diffs: list[str]) -> Arbitration:  # fmt: skip
    text, sha = prompt("arbitrate")
    watch_rules, watch_sha = prompt("watch")
    user = (
        f"Video length {info.duration_s:.1f} s. Narration: {transcript.text or '(none)'}\n"
        f"Differences found: {'; '.join(diffs)}\n\nSpec A (Muse Spark 1.3):\n{a.model_dump_json()}\n\n"
        f"Spec B (Muse Spark Open):\n{b.model_dump_json()}\n\nKeyframes follow in time order."
    )
    call = providers.responses_call(
        settings.model_wonder,
        input=[{"role": "system", "content": text + "\n\nThe original instructions:\n" + watch_rules},
               {"role": "user", "content": [{"type": "input_text", "text": user},
                                            *_keyframe_parts(art, info, "responses")]}],
        text={"format": {"type": "json_schema", "name": "Arbitration", "schema": Arbitration.model_json_schema()}},
        reasoning={"effort": "medium"}, max_output_tokens=WATCH_MAX_OUT,
    )  # fmt: skip

    def validate(raw: Any) -> Arbitration:
        try:
            return Arbitration.model_validate(parse_json(output_text(raw), "arbitrate"))
        except DemoBotError:
            raise
        except Exception as e:
            raise DemoBotError(
                "INVALID_MODEL_OUTPUT", f"Arbitration: {str(e)[:300]}", stage="watch"
            ) from e

    return await gateway.cached_call(
        ctx=ctx, purpose="arbitrate", provider="meta", model=settings.model_wonder,
        request={"stage": "arbitrate", "prompt": sha + watch_sha, "user": user,
                 "frames": [gateway.sha256_file(art / k) for k in info.keyframes]},
        estimate_usd=ESTIMATE["arbitrate"], call=call, validate=validate,
    )  # fmt: skip


# ---------- the stage ----------
async def watch(
    ctx: RunContext, art: Path, info: IngestInfo, transcript: Transcript
) -> tuple[TaskSpec, dict[str, Any]]:
    """Returns the final TaskSpec and the cross-watch record (written to crosswatch.json)."""
    ctx = ctx.at("watch")
    (spec_a, who), spec_b = await asyncio.gather(
        spark_watch(ctx, art, info, transcript), cross_watch(ctx, art, info, transcript)
    )
    record: dict[str, Any] = {
        "primary": who,
        "spec": spec_b.model_dump(mode="json") if spec_b else None,
    }
    if spec_b is None:
        record |= {"agree": None, "agreement": None, "differences": []}
        return spec_a, record
    agreement, diffs = compare(spec_a, spec_b)
    ctx.emit("metric", payload={"name": "crosswatch_agreement", "value": agreement})
    record |= {"agreement": agreement, "agree": agreement == 1.0, "differences": diffs}
    if agreement == 1.0:
        return spec_a, record
    try:
        arb = await arbitrate(ctx, art, info, transcript, spec_a, spec_b, diffs)
    except DemoBotError as e:
        ctx.emit("log", payload={"fallback": True, "purpose": "arbitrate", "from": "Muse Wonder", "to": "Spark 1.3 spec",
                                 "code": e.code,
                                 "message": f"arbitration failed ({e.code}); keeping Spark 1.3's spec"})  # fmt: skip
        return spec_a, record
    problems = check_spec(arb.spec, info.duration_s)
    final = arb.spec if not problems else spec_a
    decision = AgentDecision(
        agent="arbiter", step=0, observation=f"specs agree on {agreement:.0%} of steps: {'; '.join(diffs)[:300]}",
        reasoning_summary=arb.reason[:300], tool="arbitrate", args={"a": who, "b": "Muse Spark Open"},
        result="arbiter spec" if not problems else f"arbiter spec invalid ({problems[0]}); kept A",
    )  # fmt: skip
    ctx.emit("decision", payload=decision.model_dump(mode="json"))
    record |= {"arbitration": {"reason": arb.reason, "used": not problems}}
    return final, record


_ = (token_cost, json)
