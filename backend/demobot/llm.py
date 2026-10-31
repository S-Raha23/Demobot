"""Small helpers shared by the stages that call language and vision models."""

import base64
import hashlib
import json
from functools import cache
from pathlib import Path
from typing import Any

import cv2

from demobot.errors import DemoBotError

PROMPTS = Path(__file__).parent / "prompts"


@cache
def prompt(name: str) -> tuple[str, str]:
    """(text, short sha) of prompts/<name>.md; the sha goes into cache keys, so editing a
    prompt never serves a stale cached answer."""
    text = (PROMPTS / f"{name}.md").read_text()
    return text, hashlib.sha256(text.encode()).hexdigest()[:10]


def output_text(resp: dict[str, Any]) -> str:
    """The text of a Responses API result (its output_text items, joined)."""
    parts = []
    for item in resp.get("output") or []:
        for c in item.get("content") or []:
            if c.get("type") == "output_text":
                parts.append(c.get("text", ""))
    return "".join(parts)


def chat_text(resp: dict[str, Any]) -> str:
    return (((resp.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""


def parse_json(text: str, stage: str) -> Any:
    """A JSON object from model text (fences and leading prose tolerated)."""
    t = text.strip()
    if "```" in t:
        t = t.split("```")[1].removeprefix("json").strip()
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b <= a:
        raise DemoBotError("INVALID_MODEL_OUTPUT", "no JSON object in the answer", stage=stage)
    try:
        return json.loads(t[a : b + 1])
    except json.JSONDecodeError as e:
        raise DemoBotError("INVALID_MODEL_OUTPUT", f"bad JSON: {e}", stage=stage) from e


def jpeg_data_url(path: Path, width: int = 512, quality: int = 85) -> str:
    img = cv2.imread(str(path))
    if img is None:
        raise DemoBotError("MEDIA_ERROR", f"cannot read {path.name}")
    h, w = img.shape[:2]
    if w > width:
        img = cv2.resize(img, (width, round(h * width / w)), interpolation=cv2.INTER_AREA)
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


def video_data_url(path: Path) -> str:
    return "data:video/mp4;base64," + base64.b64encode(path.read_bytes()).decode()
