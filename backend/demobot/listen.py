"""Stage 3: Listen. Muse Voice Transcribe on the clip's narration or a spoken correction
(docs/04 §3). English, Hindi and Bengali."""

import json
import re
import wave
from pathlib import Path
from typing import Any

from demobot import gateway, providers
from demobot.config import audio_cost, settings
from demobot.events import RunContext
from demobot.schemas import Segment, Transcript

KEYWORDS = [
    "pen", "pens", "box", "mug", "cup", "box cutter", "cutter", "spoon", "glue", "glue bottle",
    "tennis ball", "ball", "left", "right", "front", "behind", "inside", "line", "row", "swap",
]  # fmt: skip
LANGUAGES = ["English", "Hindi", "Bengali"]


def wav_seconds(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / float(w.getframerate())


def detect_language(text: str) -> str:
    """By script: Devanagari is Hindi, Bengali script is Bengali, otherwise English."""
    if re.search(r"[ঀ-৿]", text):
        return "Bengali"
    if re.search(r"[ऀ-ॿ]", text):
        return "Hindi"
    return "English" if text.strip() else "unknown"


def _num(d: dict[str, Any], *keys: str) -> float | None:
    for k in keys:
        if isinstance(d.get(k), int | float):
            return float(d[k])
    return None


def parse_transcript(raw: dict[str, Any], duration_s: float, source: str) -> Transcript:
    """The probe confirmed {transcript, audioDurationMs, turns[]}; the turn fields were never
    seen with speech, so they are read defensively (ms or s; several key spellings)."""
    text = str(raw.get("transcript") or "").strip()
    segments: list[Segment] = []
    for turn in raw.get("turns") or []:
        if not isinstance(turn, dict):
            continue
        t_text = str(turn.get("transcript") or turn.get("text") or "").strip()
        start_ms = _num(turn, "startMs", "start_ms", "startTimeMs", "audioStartMs")
        end_ms = _num(turn, "endMs", "end_ms", "endTimeMs", "audioEndMs")
        start_s = _num(turn, "start", "startTime", "start_s")
        end_s = _num(turn, "end", "endTime", "end_s")
        t0 = start_ms / 1000 if start_ms is not None else (start_s or 0.0)
        t1 = end_ms / 1000 if end_ms is not None else (end_s or duration_s)
        if t_text:
            segments.append(Segment(t0=round(t0, 2), t1=round(t1, 2), text=t_text))
    if text and not segments:
        segments = [Segment(t0=0.0, t1=round(duration_s, 2), text=text)]
    if not text and segments:
        text = " ".join(s.text for s in segments)
    langs = sorted({detect_language(s.text) for s in segments if s.text})
    return Transcript(
        text=text,
        language=detect_language(text),
        languages=langs,
        segments=segments,
        source="none" if not text else source,
    )


async def transcribe(
    ctx: RunContext, wav: Path | None, keywords: list[str] | None = None, source: str = "narration"
) -> Transcript:
    """Transcribe a mono 16-bit WAV; no file means no narration."""
    if wav is None or not wav.exists():
        return Transcript(text="", source="none")
    secs = wav_seconds(wav)
    req = {
        "model": settings.model_asr,
        "mode": "PUSH_TO_TALK",
        "audioEncoding": "WAV",
        "languageBias": LANGUAGES,
        "keywords": sorted(set(keywords or KEYWORDS)),
    }

    async def call(timeout: float) -> tuple[Any, float, dict[str, Any]]:
        resp = await providers.raw_post(
            "asr/transcribe",
            timeout=timeout,
            files={
                "request": (None, json.dumps(req), "application/json"),
                "audio": ("audio.wav", wav.read_bytes(), "audio/wav"),
            },
        )
        return resp.json(), audio_cost(secs), {"audio_s": secs}

    raw = await gateway.cached_call(
        ctx=ctx.at("listen"),
        purpose="listen",
        provider="meta",
        model=settings.model_asr,
        request={"wav": gateway.sha256_file(wav), "req": req, "source": source},
        estimate_usd=max(0.001, audio_cost(secs) * 2),
        call=call,
        validate=gateway.passthrough,
    )
    return parse_transcript(raw, secs, source)
