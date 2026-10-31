import subprocess
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from demobot import media
from demobot.errors import DemoBotError


def make_clip(path: Path, seconds: float, size: str = "640x480", src: str = "testsrc2",
              fps: int = 10, audio: bool = False) -> Path:  # fmt: skip
    sep = ":" if "=" in src else "="
    lavfi = f"{src}{sep}size={size}:rate={fps}:duration={seconds}"
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", lavfi]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=300:duration={seconds}"]
    cmd += ["-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast", "-shortest"]
    subprocess.run([*cmd, str(path)], check=True)
    return path


def code(fn, *a) -> str:  # type: ignore[no-untyped-def]
    with pytest.raises(DemoBotError) as e:
        fn(*a)
    return e.value.code


def test_rejects_small_long_and_non_video(tmp_path: Path) -> None:
    assert code(media.video_info, make_clip(tmp_path / "s.mp4", 1, "320x240")) == "CLIP_TOO_SMALL"
    long = make_clip(tmp_path / "l.mp4", 61, "640x480", "color=c=gray", fps=1)
    assert code(media.video_info, long) == "CLIP_TOO_LONG"
    png = tmp_path / "x.mp4"
    png.write_bytes(b"not a video at all")
    assert code(media.video_info, png) == "NOT_A_VIDEO"


def test_active_span_pads_and_clamps() -> None:
    energies = [0.0] * 30 + [10.0] * 20 + [0.0] * 30  # motion from 3.0 s to 5.0 s
    start, end = media.active_span(energies, 8.0)
    assert start == pytest.approx(2.0) and end == pytest.approx(6.1)
    assert media.active_span([0.0] * 10, 1.0) == (0.0, 1.0)


def test_ingest_writes_all_outputs(tmp_path: Path) -> None:
    src = make_clip(tmp_path / "in.mp4", 3, "1280x720", audio=True)
    info = media.ingest(src, tmp_path / "out")
    out = tmp_path / "out"
    assert (out / "display_raw.mp4").exists() and (out / "analysis.mp4").exists()
    assert (info.width, info.height) == (1280, 720)
    assert info.analysis_frames == pytest.approx(info.duration_s * 10, abs=1)
    assert info.has_audio and (out / "audio.wav").exists()
    assert len(info.keyframes) == 8 and all((out / k).exists() for k in info.keyframes)


def test_portrait_clip_keeps_short_side_720(tmp_path: Path) -> None:
    info = media.ingest(make_clip(tmp_path / "p.mp4", 2, "1080x1920"), tmp_path / "out")
    assert (info.width, info.height) == (720, 1280) and not info.has_audio


async def test_save_upload_aborts_past_limit(tmp_path: Path) -> None:
    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(3):
            yield b"x" * (1024 * 1024)

    dest = tmp_path / "up.mp4"
    with pytest.raises(DemoBotError) as e:
        await media.save_upload(chunks(), dest, max_mb=2)
    assert e.value.code == "FILE_TOO_LARGE" and not dest.exists()
