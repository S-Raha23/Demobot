"""M0 probes: answer every PROBE item in docs/03-models.md with real calls through the gateway.

Every call is cached, so a second run costs $0.00. Raw findings go to data/probe/results.json;
the human-readable summary is docs/probe-results.md.

    uv run python scripts/probe_models.py [--only name,name] [--fresh name,name]
"""

import argparse
import asyncio
import base64
import json
import subprocess
import sys
import time
import traceback
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel

from demobot import budget, gateway, providers
from demobot.config import settings, token_cost
from demobot.events import RunContext
from demobot.gateway import passthrough
from demobot.providers import client, dump, responses_usage, tokens_cost

ROOT = Path(__file__).resolve().parents[1]
OUT = settings.data_path / "probe"
CTX = RunContext(run_id=None, mode="dev")
FRESH: set[str] = set()


# ---------- probe media (rendered locally, free) ----------
def make_media() -> dict[str, Path]:
    """A PyBullet table with a tray, a duck and coloured blocks; one still and a 3 s clip in
    which the red block slides into the tray; 5 s of real phone audio as a WAV."""
    import cv2
    import pybullet as p
    import pybullet_data

    OUT.mkdir(parents=True, exist_ok=True)
    still, clip, wav = OUT / "scene.png", OUT / "clip.mp4", OUT / "audio.wav"
    if still.exists() and clip.exists() and wav.exists():
        return {"still": still, "clip": clip, "wav": wav}
    cid = p.connect(p.DIRECT)
    p.setAdditionalSearchPath(pybullet_data.getDataPath())
    plane = p.loadURDF("plane.urdf")
    p.changeVisualShape(plane, -1, rgbaColor=[0.85, 0.82, 0.76, 1])
    p.loadURDF("tray/traybox.urdf", [0.15, 0.0, 0.0], globalScaling=0.6)
    p.loadURDF(
        "duck_vhacd.urdf",
        [-0.15, 0.12, 0.02],
        p.getQuaternionFromEuler([1.57, 0, 0.5]),
        globalScaling=1.2,
    )
    blocks = []
    for xy, rgba in [((-0.15, -0.1), [0.85, 0.1, 0.1, 1]), ((-0.02, 0.15), [0.1, 0.3, 0.85, 1])]:
        b = p.loadURDF("cube_small.urdf", [*xy, 0.025], globalScaling=1.0)
        p.changeVisualShape(b, -1, rgbaColor=rgba)
        blocks.append(b)
    view = p.computeViewMatrix([0, 0.45, 0.55], [0, 0, 0], [0, -1, 0.8])
    proj = p.computeProjectionMatrixFOV(55, 640 / 480, 0.05, 3)

    def frame() -> np.ndarray:
        _, _, rgb, _, _ = p.getCameraImage(640, 480, view, proj, renderer=p.ER_TINY_RENDERER)
        return cv2.cvtColor(
            np.asarray(rgb, np.uint8).reshape(480, 640, 4)[:, :, :3], cv2.COLOR_RGB2BGR
        )

    cv2.imwrite(str(still), frame())
    raw = OUT / "clip_raw.mp4"
    vw = cv2.VideoWriter(str(raw), cv2.VideoWriter_fourcc(*"mp4v"), 10, (640, 480))
    start, end = np.array([-0.15, -0.1, 0.025]), np.array([0.15, 0.0, 0.06])
    for i in range(30):
        a = min(1.0, max(0.0, (i - 5) / 20))
        pos = start + (end - start) * a + np.array([0, 0, 0.08 * np.sin(np.pi * a)])
        p.resetBasePositionAndOrientation(blocks[0], pos.tolist(), [0, 0, 0, 1])
        vw.write(frame())
    vw.release()
    p.disconnect(cid)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(raw),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(clip),
        ],
        check=True,
    )
    raw.unlink()
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-ss",
            "3",
            "-t",
            "5",
            "-i",
            str(ROOT / "data/calibration/checkerboard.mp4"),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-sample_fmt",
            "s16",
            str(wav),
        ],
        check=True,
    )
    return {"still": still, "clip": clip, "wav": wav}


def data_url(path: Path, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


# ---------- helpers ----------
async def gw(
    name: str,
    provider: str,
    model: str,
    request: dict[str, Any],
    call: gateway.Call,
    est: float = 0.05,
) -> Any:
    return await gateway.cached_call(
        ctx=CTX,
        purpose=f"probe:{name}",
        provider=provider,
        model=model,
        request=request,
        estimate_usd=est,
        call=call,
        validate=passthrough,
        use_cache=name not in FRESH,
    )


def raw_responses(
    model: str, cost_fn: Callable[[dict[str, Any]], float] | None = None, **kw: Any
) -> gateway.Call:
    """Responses call that keeps incomplete answers (we want to see them) and the headers."""

    async def call(timeout: float) -> tuple[Any, float, dict[str, Any]]:
        t0 = time.monotonic()
        raw = (
            await client("meta")
            .with_options(timeout=timeout)
            .responses.with_raw_response.create(model=model, **kw)
        )
        resp = raw.parse()
        usage = responses_usage(resp)
        cost = cost_fn(usage) if cost_fn else tokens_cost(model, usage)
        headers = {
            k: v
            for k, v in raw.headers.items()
            if "limit" in k.lower() or "request-id" in k.lower()
        }
        return (
            {"response": dump(resp), "headers": headers, "wall_s": round(time.monotonic() - t0, 2)},
            cost,
            usage,
        )

    return call


def raw_chat(provider: str, model: str, **kw: Any) -> gateway.Call:
    async def call(timeout: float) -> tuple[Any, float, dict[str, Any]]:
        t0 = time.monotonic()
        resp = (
            await client(provider)
            .with_options(timeout=timeout)
            .chat.completions.create(model=model, **kw)
        )
        usage = providers.chat_usage(resp)
        return (
            {"response": dump(resp), "wall_s": round(time.monotonic() - t0, 2)},
            tokens_cost(model, usage),
            usage,
        )

    return call


def output_text(resp: dict[str, Any]) -> str:
    parts = []
    for item in resp.get("output", []):
        for c in item.get("content") or []:
            if c.get("type") == "output_text":
                parts.append(c.get("text", ""))
    return "".join(parts)


def chat_text(resp: dict[str, Any]) -> str:
    return ((resp.get("choices") or [{}])[0].get("message") or {}).get("content") or ""


class Obj(BaseModel):
    name: str
    color: str


class Scene(BaseModel):
    summary: str
    objects: list[Obj]


SCENE_SCHEMA = Scene.model_json_schema()  # has $defs/$ref


# ---------- probes ----------
async def p_meta_hello(m: dict[str, Path]) -> dict[str, Any]:
    spark = settings.model_spark
    r = await gw(
        "meta_hello",
        "meta",
        spark,
        {"t": "hello", "effort": "low"},
        raw_responses(
            spark,
            input="Reply with exactly: OK",
            reasoning={"effort": "low"},
            max_output_tokens=4000,
        ),
    )
    tiny = await gw(
        "meta_tiny_budget",
        "meta",
        spark,
        {"t": "tiny", "effort": "high"},
        raw_responses(
            spark,
            input="Explain in 300 words why the sky is blue.",
            reasoning={"effort": "high"},
            max_output_tokens=200,
        ),
    )
    return {
        "hello_text": output_text(r["response"]),
        "status": r["response"].get("status"),
        "usage": r["response"].get("usage"),
        "reasoning_field_accepted": True,
        "rate_limit_headers": r["headers"],
        "tiny_budget_status": tiny["response"].get("status"),
        "tiny_budget_incomplete_details": tiny["response"].get("incomplete_details"),
        "tiny_budget_usage": tiny["response"].get("usage"),
        "tiny_budget_text_len": len(output_text(tiny["response"])),
    }


async def p_spark_video(m: dict[str, Path]) -> dict[str, Any]:
    spark = settings.model_spark
    sha = gateway.sha256_file(m["clip"])
    fid = await providers.upload_file(m["clip"], sha)
    out: dict[str, Any] = {"file_id_prefix": fid[:8]}
    content = [
        {
            "type": "input_text",
            "text": "This is a short rendered video of a table. What objects are visible and what moves where? Answer in the JSON schema.",
        },
        {"type": "input_file", "file_id": fid},
    ]
    try:
        r = await gw(
            "spark_video_defs",
            "meta",
            spark,
            {"clip": sha, "schema": "defs"},
            raw_responses(
                spark,
                input=[{"role": "user", "content": content}],
                reasoning={"effort": "low"},
                max_output_tokens=8000,
                text={"format": {"type": "json_schema", "name": "Scene", "schema": SCENE_SCHEMA}},
            ),
        )
        out["defs_accepted"] = True
        out["defs_text"] = output_text(r["response"])[:800]
        out["usage"] = r["response"].get("usage")
        out["wall_s"] = r["wall_s"]
    except Exception as e:
        out["defs_accepted"] = False
        out["defs_error"] = str(e)[:600]
    return out


TOOLS = [
    {
        "type": "function",
        "name": "simulate",
        "description": "Run a robot program in the simulator and return a test report.",
        "parameters": {
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
            "additionalProperties": False,
        },
    }
]


async def p_wonder_tools(m: dict[str, Path]) -> dict[str, Any]:
    wonder = settings.model_wonder
    out: dict[str, Any] = {}
    r1 = await gw(
        "wonder_tool_1",
        "meta",
        wonder,
        {"t": 1},
        raw_responses(
            wonder,
            input="Write a one-line Python program `print(2+3)` and test it by calling the simulate tool exactly once. Do not answer before calling the tool.",
            tools=TOOLS,
            reasoning={"effort": "low"},
            max_output_tokens=4000,
        ),
        est=0.1,
    )
    resp1 = r1["response"]
    calls = [o for o in resp1.get("output", []) if o.get("type") == "function_call"]
    out["first_output_types"] = [o.get("type") for o in resp1.get("output", [])]
    out["function_call"] = calls[0] if calls else None
    out["usage_1"] = resp1.get("usage")
    if not calls:
        return out
    follow = [
        {
            "type": "function_call_output",
            "call_id": calls[0]["call_id"],
            "output": json.dumps({"ok": True, "stdout": "5"}),
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "Good. Also: in one sentence, what objects are in this simulator render?",
                },
                {"type": "input_image", "image_url": data_url(m["still"], "image/png")},
            ],
        },
    ]
    try:
        r2 = await gw(
            "wonder_tool_2",
            "meta",
            wonder,
            {"t": 2, "prev": resp1["id"]},
            raw_responses(
                wonder,
                previous_response_id=resp1["id"],
                input=follow,
                tools=TOOLS,
                reasoning={"effort": "low"},
                max_output_tokens=4000,
            ),
            est=0.1,
        )
        out["previous_response_id_ok"] = True
        out["image_in_followup_ok"] = True
        out["followup_text"] = output_text(r2["response"])[:400]
        out["usage_2"] = r2["response"].get("usage")
    except Exception as e:
        out["previous_response_id_ok"] = False
        out["followup_error"] = str(e)[:600]
    # video input
    sha = gateway.sha256_file(m["clip"])
    fid = await providers.upload_file(m["clip"], sha)
    try:
        r3 = await gw(
            "wonder_video",
            "meta",
            wonder,
            {"clip": sha},
            raw_responses(
                wonder,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": "In one sentence: what moves in this video?",
                            },
                            {"type": "input_file", "file_id": fid},
                        ],
                    }
                ],
                reasoning={"effort": "low"},
                max_output_tokens=4000,
            ),
            est=0.1,
        )
        out["video_input_ok"] = True
        out["video_text"] = output_text(r3["response"])[:400]
        out["video_usage"] = r3["response"].get("usage")
    except Exception as e:
        out["video_input_ok"] = False
        out["video_error"] = str(e)[:600]
    return out


def sam_parse(text: str, media: str) -> dict[str, Any]:
    from meta_sam_parser import (
        CompletedOutcome,
        image_segmentation_format,
        video_segmentation_format,
    )

    fmt = image_segmentation_format() if media == "image" else video_segmentation_format()
    parser = fmt.create_parser()
    parser.push(text, emit=False)
    try:
        res = parser.finish(CompletedOutcome()).result  # type: ignore[call-arg]
    except TypeError:
        import meta_sam_parser as msp

        res = parser.finish(msp.CompletedOutcome(kind="completed")).result  # type: ignore[call-arg]
    recs = getattr(res, "records", ())
    boxes = [r for r in recs if getattr(r, "kind", "") == "box"]
    masks = [r for r in recs if getattr(r, "kind", "") == "mask"]
    return {
        "n_boxes": len(boxes),
        "n_masks": len(masks),
        "first_box": repr(boxes[0])[:300] if boxes else None,
        "first_mask_meta": (masks[0].mask.encoding, masks[0].mask.width, masks[0].mask.height)
        if masks
        else None,
        "object_ids": sorted({b.object_id for b in boxes})[:20],
        "frames": sorted(
            {getattr(b.frame, "frame_index", None) for b in boxes if b.frame is not None},
            key=lambda x: (x is None, x),
        )[:50],
        "diagnostics": [repr(d)[:200] for d in getattr(res, "diagnostics", ())][:5],
    }


async def p_sam(m: dict[str, Path]) -> dict[str, Any]:
    sam = settings.model_sam
    out: dict[str, Any] = {}
    img_sha = gateway.sha256_file(m["still"])
    r = await gw(
        "sam_image",
        "meta",
        sam,
        {"img": img_sha, "phrase": "cube"},
        raw_responses(
            sam,
            cost_fn=lambda u: 0.0025,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "cube"},
                        {"type": "input_image", "image_url": data_url(m["still"], "image/png")},
                    ],
                }
            ],
        ),
        est=0.01,
    )
    text = output_text(r["response"])
    out["image_raw_head"] = text[:600]
    out["image_usage"] = r["response"].get("usage")
    out["image_wall_s"] = r["wall_s"]
    try:
        out["image_parsed"] = sam_parse(text, "image")
    except Exception as e:
        out["image_parse_error"] = repr(e)[:400]
    sha = gateway.sha256_file(m["clip"])
    fid = await providers.upload_file(m["clip"], sha)
    try:
        r2 = await gw(
            "sam_video",
            "meta",
            sam,
            {"clip": sha, "phrase": "red cube"},
            raw_responses(
                sam,
                cost_fn=lambda u: 30 * 0.0002,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "red cube"},
                            {"type": "input_video", "file_id": fid},
                        ],
                    }
                ],
            ),
            est=0.05,
        )
        vtext = output_text(r2["response"])
        out["video_file_id_ok"] = True
        out["video_raw_head"] = vtext[:600]
        out["video_raw_len"] = len(vtext)
        out["video_usage"] = r2["response"].get("usage")
        out["video_wall_s"] = r2["wall_s"]
        try:
            out["video_parsed"] = sam_parse(vtext, "video")
        except Exception as e:
            out["video_parse_error"] = repr(e)[:400]
    except Exception as e:
        out["video_file_id_ok"] = False
        out["video_error"] = str(e)[:600]
    return out


async def p_voice(m: dict[str, Path]) -> dict[str, Any]:
    asr = settings.model_asr
    sha = gateway.sha256_file(m["wav"])
    req = {
        "model": asr,
        "mode": "PUSH_TO_TALK",
        "audioEncoding": "WAV",
        "languageBias": ["English", "Hindi", "Bengali"],
        "keywords": ["mug", "pen", "eraser"],
    }

    async def call(timeout: float) -> tuple[Any, float, dict[str, Any]]:
        t0 = time.monotonic()
        resp = await providers.raw_post(
            "asr/transcribe",
            timeout=timeout,
            files={
                "request": (None, json.dumps(req), "application/json"),
                "audio": ("audio.wav", m["wav"].read_bytes(), "audio/wav"),
            },
        )
        return (
            {"json": resp.json(), "wall_s": round(time.monotonic() - t0, 2)},
            5 / 3600 * 0.18,
            {"audio_s": 5},
        )

    r = await gw("voice", "meta", asr, {"wav": sha, "req": req}, call, est=0.01)
    return {"response": r["json"], "wall_s": r["wall_s"]}


async def p_image(m: dict[str, Path]) -> dict[str, Any]:
    model = settings.model_image
    out: dict[str, Any] = {}
    prompt = "A clean top-down photo texture of a plain yellow sticky-note pad on a white background, no text."

    def gen(extra: dict[str, Any]) -> gateway.Call:
        async def call(timeout: float) -> tuple[Any, float, dict[str, Any]]:
            t0 = time.monotonic()
            resp = (
                await client("meta")
                .with_options(timeout=timeout)
                .images.generate(model=model, prompt=prompt, n=1, extra_body=extra or None)
            )
            d = dump(resp)
            for item in d.get("data") or []:
                if item.get("b64_json"):
                    (OUT / "image_gen.png").write_bytes(base64.b64decode(item["b64_json"]))
                    item["b64_json"] = f"<{len(item['b64_json'])} chars>"
            return {"response": d, "wall_s": round(time.monotonic() - t0, 2)}, 0.01, {"images": 1}

        return call

    variants = [
        ("fast", {"fast": True}),
        ("web_search", {"web_search": False}),
        ("enable_web_search", {"enable_web_search": False}),
        ("search", {"search": False}),
        ("reasoning", {"reasoning": {"effort": "minimal"}}),
        ("plain", {}),
    ]
    for label, extra in variants:
        try:
            r = await gw(
                f"image_gen_{label}",
                "meta",
                model,
                {"prompt": prompt, "extra": extra},
                gen(extra),
                est=0.02,
            )
            out[f"generate_{label}"] = r
            break
        except Exception as e:
            out[f"generate_{label}_error"] = str(e)[:500]

    async def edit(timeout: float) -> tuple[Any, float, dict[str, Any]]:
        t0 = time.monotonic()
        with m["still"].open("rb") as f:
            resp = (
                await client("meta")
                .with_options(timeout=timeout)
                .images.edit(
                    model=model,
                    image=f,
                    prompt="Turn this render into a clean flat illustration with the title 'Block into tray' at the top.",
                )
            )
        d = dump(resp)
        for item in d.get("data") or []:
            if item.get("b64_json"):
                (OUT / "image_edit.png").write_bytes(base64.b64decode(item["b64_json"]))
                item["b64_json"] = f"<{len(item['b64_json'])} chars>"
        return {"response": d, "wall_s": round(time.monotonic() - t0, 2)}, 0.01, {"images": 1}

    try:
        out["edit"] = await gw(
            "image_edit", "meta", model, {"img": gateway.sha256_file(m["still"])}, edit, est=0.02
        )
    except Exception as e:
        out["edit_error"] = str(e)[:500]
    return out


async def p_open(provider: str, m: dict[str, Path]) -> dict[str, Any]:
    model = settings.model_spark_open if provider == "baseten" else settings.model_spark_open_modal
    out: dict[str, Any] = {}
    r = await gw(
        f"{provider}_hello",
        provider,
        model,
        {"t": "hello"},
        raw_chat(
            provider,
            model,
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
            max_tokens=2000,
        ),
    )
    out["hello"] = chat_text(r["response"])[:300]
    out["hello_usage"] = r["response"].get("usage")
    out["hello_wall_s"] = r["wall_s"]
    out["message_keys"] = sorted(
        ((r["response"].get("choices") or [{}])[0].get("message") or {}).keys()
    )
    strict = gateway_strict(SCENE_SCHEMA)
    try:
        r = await gw(
            f"{provider}_json_schema",
            provider,
            model,
            {"t": "schema"},
            raw_chat(
                provider,
                model,
                messages=[
                    {"role": "user", "content": "Describe a desk with a mug and a pen as JSON."}
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "Scene", "schema": strict, "strict": True},
                },
                max_tokens=3000,
            ),
        )
        out["json_schema_ok"] = True
        out["json_schema_text"] = chat_text(r["response"])[:500]
    except Exception as e:
        out["json_schema_ok"] = False
        out["json_schema_error"] = str(e)[:500]
    img = OUT / "scene_512.jpg"
    if not img.exists():
        import cv2

        im = cv2.imread(str(m["still"]))
        cv2.imwrite(str(img), cv2.resize(im, (512, 384)), [cv2.IMWRITE_JPEG_QUALITY, 85])
    try:
        r = await gw(
            f"{provider}_image",
            provider,
            model,
            {"t": "image", "img": gateway.sha256_file(img)},
            raw_chat(
                provider,
                model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "List the objects in this image in one sentence.",
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": data_url(img, "image/jpeg")},
                            },
                        ],
                    }
                ],
                max_tokens=2000,
            ),
        )
        out["image_ok"] = True
        out["image_text"] = chat_text(r["response"])[:400]
    except Exception as e:
        out["image_ok"] = False
        out["image_error"] = str(e)[:500]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "simulate",
                "description": "Run a program in the simulator.",
                "parameters": {
                    "type": "object",
                    "properties": {"code": {"type": "string"}},
                    "required": ["code"],
                },
            },
        }
    ]
    try:
        r = await gw(
            f"{provider}_tools",
            provider,
            model,
            {"t": "tools"},
            raw_chat(
                provider,
                model,
                messages=[
                    {
                        "role": "user",
                        "content": "Test the program `print(1)` by calling the simulate tool.",
                    }
                ],
                tools=tools,
                max_tokens=2000,
            ),
        )
        msg = (r["response"].get("choices") or [{}])[0].get("message") or {}
        out["tools_ok"] = bool(msg.get("tool_calls"))
        out["tool_calls"] = msg.get("tool_calls")
    except Exception as e:
        out["tools_ok"] = False
        out["tools_error"] = str(e)[:500]
    if provider == "modal":
        try:
            r = await gw(
                "modal_video",
                provider,
                model,
                {"t": "video", "clip": gateway.sha256_file(m["clip"])},
                raw_chat(
                    provider,
                    model,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "In one sentence: what moves in this video?",
                                },
                                {
                                    "type": "video_url",
                                    "video_url": {"url": data_url(m["clip"], "video/mp4")},
                                },
                            ],
                        }
                    ],
                    max_tokens=3000,
                ),
                est=0.1,
            )
            out["video_ok"] = True
            out["video_text"] = chat_text(r["response"])[:400]
            out["video_usage"] = r["response"].get("usage")
        except Exception as e:
            out["video_ok"] = False
            out["video_error"] = str(e)[:500]
    return out


def gateway_strict(schema: dict[str, Any]) -> dict[str, Any]:
    from demobot.schemas_util import strict_schema_dict

    return strict_schema_dict(schema)


async def p_baseten(m: dict[str, Path]) -> dict[str, Any]:
    return await p_open("baseten", m)


async def p_modal(m: dict[str, Path]) -> dict[str, Any]:
    return await p_open("modal", m)


async def p_sandbox(m: dict[str, Path]) -> dict[str, Any]:
    import modal

    out: dict[str, Any] = {}
    app = modal.App.lookup("demobot-probe", create_if_missing=True)
    image = modal.Image.debian_slim(python_version="3.11").pip_install("pybullet==3.2.6", "numpy<2")
    for label in ("first", "second"):
        t0 = time.monotonic()
        sb = modal.Sandbox.create(
            "python",
            "-c",
            "import pybullet, numpy; print('pybullet', pybullet.__file__ is not None)",
            image=image,
            app=app,
            timeout=600,
        )
        sb.wait()
        out[f"{label}_s"] = round(time.monotonic() - t0, 1)
        out[f"{label}_stdout"] = sb.stdout.read().strip()[:200]
        out[f"{label}_rc"] = sb.returncode
    return out


PROBES: dict[str, Callable[[dict[str, Path]], Awaitable[dict[str, Any]]]] = {
    "meta_hello": p_meta_hello,
    "spark_video": p_spark_video,
    "wonder_tools": p_wonder_tools,
    "sam": p_sam,
    "voice": p_voice,
    "image": p_image,
    "baseten": p_baseten,
    "modal": p_modal,
    "sandbox": p_sandbox,
}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--fresh", default="")
    args = ap.parse_args()
    FRESH.update(f for f in args.fresh.split(",") if f)
    only = [n for n in args.only.split(",") if n] or list(PROBES)
    media = make_media()
    results_path = OUT / "results.json"
    results: dict[str, Any] = json.loads(results_path.read_text()) if results_path.exists() else {}
    before = {p: budget.remaining("dev", p) for p in ("meta", "baseten", "modal")}
    for name in only:
        t0 = time.monotonic()
        try:
            results[name] = {"ok": True, **await PROBES[name](media)}
        except Exception as e:
            results[name] = {
                "ok": False,
                "failed": f"{type(e).__name__}: {str(e)[:600]}",
                "trace": traceback.format_exc()[-1500:],
            }
        results[name]["probe_s"] = round(time.monotonic() - t0, 1)
        print(
            f"{name}: {'ok' if results[name]['ok'] else 'FAILED ' + results[name]['failed'][:200]}",
            file=sys.stderr,
        )
        results_path.write_text(json.dumps(results, indent=1, default=str))
    after = {p: budget.remaining("dev", p) for p in ("meta", "baseten", "modal")}
    spent = {p: round(before[p][f"{p}_total"] - after[p][f"{p}_total"], 4) for p in before}
    print(json.dumps({"spent_this_run_usd": spent}), file=sys.stderr)
    results["_last_run_spent_usd"] = spent
    results_path.write_text(json.dumps(results, indent=1, default=str))


if __name__ == "__main__":
    _ = token_cost
    asyncio.run(main())
