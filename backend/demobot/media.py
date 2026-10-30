"""Stage 1: ingest. Validate the upload, trim idle head and tail, and write display.mp4,
analysis.mp4 (10 fps), audio.wav and keyframes (docs/04 §1)."""

import json
import subprocess
from collections.abc import AsyncIterable
from pathlib import Path
from typing import Any

import numpy as np

from demobot.errors import DemoBotError
from demobot.schemas import IngestInfo

MAX_MB = 120
MAX_RAW_S = 60.0
MAX_ACTIVE_S = 40.0
MIN_SIDE_PX = 480
SHORT_SIDE_PX = 720
ANALYSIS_FPS = 10
DISPLAY_FPS = 30
PAD_S = 1.0
ENERGY_FPS = 10
ENERGY_THRESHOLD = 2.0
SILENCE_RMS = 0.004  # mono float RMS below which the audio track is dropped
N_KEYFRAMES = 8
_ENERGY_W, _ENERGY_H = 160, 90
_VIDEO_CODECS = {"h264", "hevc", "mpeg4", "vp8", "vp9", "av1"}


def _run(cmd: list[str], stage: str = "ingest") -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(cmd, capture_output=True, check=True)
    except FileNotFoundError as e:
        raise DemoBotError("INTERNAL", f"{cmd[0]} is not installed", stage, http=500) from e
    except subprocess.CalledProcessError as e:
        msg = e.stderr.decode(errors="replace")[-300:]
        raise DemoBotError("MEDIA_ERROR", f"{cmd[0]} failed: {msg}", stage, http=500) from e


def probe(path: Path) -> dict[str, Any]:
    cmd = ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]
    try:
        out = subprocess.run(cmd, capture_output=True, check=True).stdout
    except subprocess.CalledProcessError as e:
        raise not_a_video() from e
    return json.loads(out)


def not_a_video() -> DemoBotError:
    return DemoBotError("NOT_A_VIDEO", "Upload an MP4, MOV or WebM video.", "ingest")


def too_large(limit_mb: int = MAX_MB) -> DemoBotError:
    return DemoBotError("FILE_TOO_LARGE", f"Files up to {limit_mb} MB.", "ingest", http=413)


def _rotation(stream: dict[str, Any]) -> int:
    for sd in stream.get("side_data_list") or []:
        if "rotation" in sd:
            return int(sd["rotation"])
    return int((stream.get("tags") or {}).get("rotate", 0))


def video_info(path: Path) -> dict[str, Any]:
    """Validated basics: duration, displayed width/height (rotation applied), audio presence."""
    if path.stat().st_size > MAX_MB * 1024 * 1024:
        raise too_large()
    info = probe(path)
    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if video is None or video.get("codec_name") not in _VIDEO_CODECS:
        raise not_a_video()
    duration = float(info.get("format", {}).get("duration") or video.get("duration") or 0)
    if duration > MAX_RAW_S:
        raise DemoBotError("CLIP_TOO_LONG", f"Keep the clip under {MAX_RAW_S:.0f} s.", "ingest")
    w, h = int(video["width"]), int(video["height"])
    if abs(_rotation(video)) in (90, 270):
        w, h = h, w
    if min(w, h) < MIN_SIDE_PX:
        raise DemoBotError("CLIP_TOO_SMALL", f"Record at least {MIN_SIDE_PX}p.", "ingest")
    return {
        "duration": duration,
        "width": w,
        "height": h,
        "has_audio": any(s.get("codec_type") == "audio" for s in info["streams"]),
    }


def motion_energy(path: Path) -> list[float]:
    """Mean absolute greyscale difference between consecutive frames at 10 fps (0–255)."""
    cmd = [
        "ffmpeg", "-v", "error", "-i", str(path), "-an",
        "-vf", f"fps={ENERGY_FPS},scale={_ENERGY_W}:{_ENERGY_H},format=gray",
        "-f", "rawvideo", "-",
    ]  # fmt: skip
    raw = _run(cmd).stdout
    size = _ENERGY_W * _ENERGY_H
    frames = np.frombuffer(raw[: len(raw) // size * size], np.uint8).reshape(-1, size)
    if len(frames) < 2:
        return []
    return np.abs(np.diff(frames.astype(np.int16), axis=0)).mean(axis=1).tolist()


def active_span(energies: list[float], duration: float) -> tuple[float, float]:
    """(start, end) seconds of the motion, padded by PAD_S each side; the whole clip if still."""
    active = [i for i, e in enumerate(energies) if e > ENERGY_THRESHOLD]
    if not active:
        return 0.0, duration
    start = max(0.0, active[0] / ENERGY_FPS - PAD_S)
    end = min(duration, (active[-1] + 2) / ENERGY_FPS + PAD_S)
    return start, end


def _scale_filter() -> str:
    s = SHORT_SIDE_PX
    return f"scale='if(gt(iw,ih),-2,{s})':'if(gt(iw,ih),{s},-2)'"


def audio_rms(path: Path) -> float:
    raw = _run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000",
                "-f", "f32le", "-"]).stdout  # fmt: skip
    pcm = np.frombuffer(raw[: len(raw) // 4 * 4], np.float32)
    return float(np.sqrt(np.mean(pcm**2))) if len(pcm) else 0.0


def to_wav(src: Path, dst: Path, start: float = 0.0, end: float | None = None) -> Path:
    """Mono 16-bit 16 kHz WAV, what Voice Transcribe wants."""
    span = ["-ss", f"{start:.3f}"] + (["-to", f"{end:.3f}"] if end is not None else [])
    _run(["ffmpeg", "-v", "error", "-y", *span, "-i", str(src), "-vn", "-ac", "1", "-ar",
          "16000", "-sample_fmt", "s16", str(dst)])  # fmt: skip
    return dst


def frame_count(path: Path) -> int:
    out = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_packets",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=nb_read_packets",
            "-of",
            "csv=p=0",
            str(path),
        ]
    ).stdout
    return int(out.decode().strip().split(",")[0] or 0)


def extract_frame(video: Path, t: float, dst: Path) -> Path:
    _run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0.0, t):.3f}", "-i", str(video),
          "-frames:v", "1", "-q:v", "2", str(dst)])  # fmt: skip
    return dst


def ingest(src: Path, out_dir: Path) -> IngestInfo:
    """Writes display.mp4, analysis.mp4, audio.wav (if any narration) and keyframes/."""
    info = video_info(src)
    start, end = active_span(motion_energy(src), info["duration"])
    if end - start > MAX_ACTIVE_S:
        raise DemoBotError(
            "CLIP_TOO_LONG", f"Keep the task itself under {MAX_ACTIVE_S:.0f} s.", "ingest"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    span = ["-ss", f"{start:.3f}", "-to", f"{end:.3f}"]
    display, analysis = out_dir / "display.mp4", out_dir / "analysis.mp4"
    audio = ["-c:a", "aac", "-b:a", "96k"] if info["has_audio"] else ["-an"]
    _run(["ffmpeg", "-v", "error", "-y", *span, "-i", str(src), "-vf",
          f"{_scale_filter()},fps={DISPLAY_FPS}", "-c:v", "libx264", "-preset", "veryfast",
          "-crf", "21", "-pix_fmt", "yuv420p", *audio, "-movflags", "+faststart",
          str(display)])  # fmt: skip
    _run(["ffmpeg", "-v", "error", "-y", *span, "-i", str(src), "-an", "-vf",
          f"{_scale_filter()},fps={ANALYSIS_FPS}", "-c:v", "libx264", "-preset", "veryfast",
          "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
          str(analysis)])  # fmt: skip
    has_audio = False
    if info["has_audio"]:
        wav = to_wav(src, out_dir / "audio.wav", start, end)
        has_audio = audio_rms(wav) > SILENCE_RMS
        if not has_audio:
            wav.unlink()
    a = video_info(analysis)
    n = frame_count(analysis)
    duration = n / ANALYSIS_FPS
    kdir = out_dir / "keyframes"
    kdir.mkdir(exist_ok=True)
    times = [round(float(t), 2) for t in np.linspace(0, max(0.0, duration - 0.15), N_KEYFRAMES)]
    keys = []
    for k, t in enumerate(times):
        extract_frame(analysis, t, kdir / f"kf_{k:02d}.jpg")
        keys.append(f"keyframes/kf_{k:02d}.jpg")
    return IngestInfo(
        source_name=src.name,
        width=a["width"],
        height=a["height"],
        raw_duration_s=info["duration"],
        trim_start_s=round(start, 3),
        trim_end_s=round(end, 3),
        duration_s=round(duration, 3),
        analysis_fps=ANALYSIS_FPS,
        analysis_frames=n,
        has_audio=has_audio,
        keyframes=keys,
        keyframe_times=times,
    )


async def save_upload(chunks: AsyncIterable[bytes], dest: Path, max_mb: int = MAX_MB) -> int:
    """Stream chunks to `dest`, aborting with FILE_TOO_LARGE past the limit."""
    written = 0
    try:
        with dest.open("wb") as f:
            async for chunk in chunks:
                written += len(chunk)
                if written > max_mb * 1024 * 1024:
                    raise too_large(max_mb)
                f.write(chunk)
    except DemoBotError:
        dest.unlink(missing_ok=True)
        raise
    return written
