"""Record the demo video from the real UI, following the shot list in docs/10-submission.md.

    uv run python scripts/record_demo.py [--run pen-left-of-box] [--url URL] [--skip-record]

Writes media/demo/demo_final.mp4 (3:00) and media/demo/demo_30s.mp4 (the 30-second cut for the X
post). A replay-mode server (no model calls) serves a recorded run; scripts/record_demo.cjs records
takes of it in headless Chrome; ffmpeg cuts the takes into shots, burns in the captions and adds the
title and closing cards. Every number on the closing card comes from eval/results.json. Replays are
labelled as replays, and the label says whether the input clip was synthetic (run.json "note").
If media/demo/voiceover.wav exists it is mixed in; otherwise the audio track is silent.

Needs: frontend/dist (cd frontend && npx vite build), node with Playwright installed in frontend/,
and ffmpeg. Set PW_CHROME to a Chrome binary when Playwright's own Chromium cannot start.
"""

import argparse
import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "media" / "demo"
TAKES = ROOT / "data" / "demo_takes"
PORT = 8765
W, H, FPS = 1920, 1080, 30
BG = "0x0b1020"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
REPO = "https://github.com/S-Raha23/Demobot"


def run_dir(run: str) -> Path:
    for d in (ROOT / "data" / "runs" / run, ROOT / "backend" / "tests" / "fixtures" / "runs" / run):
        if (d / "run.json").exists():
            return d
    sys.exit(f"no run named {run}")


def correction_text(d: Path) -> str | None:
    for line in (d / "events.jsonl").read_text().splitlines():
        e = json.loads(line)
        if e["type"] == "artifact" and e["payload"].get("name") == "correction_transcript":
            return str(e["payload"]["text"])[:40]
    return None


@contextlib.contextmanager
def server() -> Iterator[None]:
    """A replay-mode API (DEMOBOT_FIXTURES=1: no paid calls are possible) unless one is running."""
    health = f"http://127.0.0.1:{PORT}/api/health"

    def up() -> bool:
        try:
            with urllib.request.urlopen(health, timeout=1) as r:
                return bool(r.status == 200)
        except OSError:
            return False

    if up():
        yield
        return
    env = {**os.environ, "DEMOBOT_MODE": "replay", "DEMOBOT_FIXTURES": "1"}
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "demobot.api:app",
        "--app-dir",
        "backend",
        "--port",
        str(PORT),
    ]
    p = subprocess.Popen(
        cmd, cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        for _ in range(60):
            if up():
                break
            time.sleep(0.5)
        else:
            sys.exit("the replay server did not start")
        yield
    finally:
        p.terminate()


def plan(run: str, corr: str | None) -> dict[str, Any]:
    stages = ["watch", "perceive", "program", "verify", "stress", "harden"]
    marks: list[dict[str, Any]] = [{"name": s, "stage": s, "status": "running"} for s in stages]
    marks.append({"name": "finished", "selector": '[data-testid="replay-again"]'})
    if corr:
        marks.append({"name": "correction", "text": corr})
    return {
        "base": f"http://127.0.0.1:{PORT}",
        "width": W,
        "height": H,
        "takes": [
            {"name": "hook", "url": f"/run/{run}?skip=1", "marks": [], "actions": [{"wait": 2000}],
             "end": {"after_s": 12}, "rects": {"real": '[data-testid="real-panel"]', "twin": '[data-testid="twin-panel"]'}},
            {"name": "main", "url": f"/run/{run}?speed=4", "marks": marks, "end": {"mark": "finished", "after_s": 2},
             "max_s": 420},
            {"name": "try", "url": f"/try/{run}", "marks": [{"name": "done", "text": "achieved"}],
             "actions": [{"wait": 3000}, {"click": '[data-testid="try-shuffle"]'}, {"wait": 2500},
                         {"click": '[data-testid="try-run"]'}, {"waitMark": "done"}],
             "end": {"after_s": 3}, "max_s": 120},
        ],
    }  # fmt: skip


def record(run: str, corr: str | None) -> None:
    TAKES.mkdir(parents=True, exist_ok=True)
    plan_path = TAKES / "plan.json"
    plan_path.write_text(json.dumps(plan(run, corr), indent=1))
    with server():
        subprocess.run(
            ["node", str(ROOT / "scripts" / "record_demo.cjs"), str(plan_path), str(TAKES)],
            check=True,
        )


def marks(take: str) -> dict[str, Any]:
    return dict(json.loads((TAKES / take / "marks.json").read_text()))


def ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


class Shots:
    """Renders shots to numbered clips in a work directory, all 1920×1080, 30 fps, no audio."""

    def __init__(self, work: Path, label: str):
        self.work, self.label = work, label
        self.files: list[Path] = []

    def _text(self, text: str) -> str:
        f = self.work / f"t{len(list(self.work.glob('t*.txt')))}.txt"
        f.write_text(text)
        return str(f)

    def _caption(self, caption: str, label: str | None) -> str:
        parts = []
        if caption:
            parts.append(f"drawtext=expansion=none:fontfile={FONT_BOLD}:textfile={self._text(caption)}:fontsize=44:fontcolor=white:"
                         "x=(w-text_w)/2:y=h-130:box=1:boxcolor=black@0.62:boxborderw=22:line_spacing=10")  # fmt: skip
        if label:
            parts.append(f"drawtext=expansion=none:fontfile={FONT}:textfile={self._text(label)}:fontsize=22:fontcolor=white@0.85:"
                         "x=28:y=24:box=1:boxcolor=black@0.5:boxborderw=10")  # fmt: skip
        return ",".join(parts)

    def _out(self) -> Path:
        f = self.work / f"s{len(self.files):02d}.mp4"
        self.files.append(f)
        return f

    def take(self, take: str, a: float, b: float, dur: float, caption: str,
             crop: tuple[int, int, int, int] | None = None) -> None:  # fmt: skip
        """Seconds a..b of a take, sped up (or slowed, at most 1.5×) to fill `dur` seconds."""
        b = max(b, a + 0.5)
        k = min(1.5, dur / (b - a))
        vf = [f"trim=start={a:.2f}:end={b:.2f}", f"setpts=(PTS-STARTPTS)*{k:.4f}", f"fps={FPS}"]
        if crop:
            vf.append("crop={2}:{3}:{0}:{1}".format(*crop))
        vf += [f"scale={W}:{H}:force_original_aspect_ratio=decrease", f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={BG}",
               f"tpad=stop_mode=clone:stop_duration={dur:.2f}"]  # fmt: skip
        cap = self._caption(caption, self.label)
        if cap:
            vf.append(cap)
        src = TAKES / take / "frames.ffconcat"
        ff("-f", "concat", "-safe", "0", "-i", str(src), "-vf", ",".join(vf), "-t", f"{dur:.2f}",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-an", str(self._out()))  # fmt: skip

    def card(self, lines: list[tuple[str, int, bool]], dur: float, image: Path | None = None,
             caption: str = "") -> None:  # fmt: skip
        """A title card: lines of (text, size, bold) centred on a dark (or darkened, blurred image) background."""
        if image:
            inputs = ["-loop", "1", "-t", f"{dur:.2f}", "-i", str(image)]
            vf = [f"scale={W}:{H}:force_original_aspect_ratio=increase", f"crop={W}:{H}", "boxblur=18:2",
                  "colorchannelmixer=rr=0.35:gg=0.35:bb=0.35"]  # fmt: skip
        else:
            inputs = ["-f", "lavfi", "-t", f"{dur:.2f}", "-i", f"color=c={BG}:s={W}x{H}:r={FPS}"]
            vf = []
        total = sum(int(s * 1.5) for _, s, _ in lines)
        y = (H - total) // 2
        for text, size, bold in lines:
            font = FONT_BOLD if bold else FONT
            vf.append(f"drawtext=expansion=none:fontfile={font}:textfile={self._text(text)}:fontsize={size}:fontcolor=white:"
                      f"x=(w-text_w)/2:y={y}")  # fmt: skip
            y += int(size * 1.5)
        cap = self._caption(caption, None)
        if cap:
            vf.append(cap)
        vf += [f"fps={FPS}", "fade=t=in:st=0:d=0.4", f"fade=t=out:st={dur - 0.4:.2f}:d=0.4"]
        ff(*inputs, "-vf", ",".join(vf), "-t", f"{dur:.2f}", "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "18", "-pix_fmt", "yuv420p", "-an", str(self._out()))  # fmt: skip

    def still(self, image: Path, dur: float, caption: str) -> None:
        vf = [f"scale={W - 240}:{H - 300}:force_original_aspect_ratio=decrease", f"pad={W}:{H}:(ow-iw)/2:90:color={BG}",
              f"fps={FPS}", self._caption(caption, None)]  # fmt: skip
        ff("-loop", "1", "-t", f"{dur:.2f}", "-i", str(image), "-vf", ",".join(vf), "-t", f"{dur:.2f}",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-an", str(self._out()))  # fmt: skip

    def join(self, out: Path, voiceover: Path | None) -> None:
        lst = self.work / "list.txt"
        lst.write_text("".join(f"file '{f}'\n" for f in self.files))
        silent = self.work / "joined.mp4"
        ff("-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(silent))
        audio = (
            ["-i", str(voiceover)]
            if voiceover
            else ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        )
        ff("-i", str(silent), *audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
           "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(out))  # fmt: skip


def crop_of(rects: dict[str, Any]) -> tuple[int, int, int, int] | None:
    boxes = [r for r in rects.values() if r]
    if not boxes:
        return None
    x0 = min(r["x"] for r in boxes)
    y0 = min(r["y"] for r in boxes)
    x1 = max(r["x"] + r["width"] for r in boxes)
    y1 = max(r["y"] + r["height"] for r in boxes)
    return int(x0), int(y0), int(x1 - x0) // 2 * 2, int(y1 - y0) // 2 * 2


def headline() -> list[str]:
    r = json.loads((ROOT / "eval" / "results.json").read_text()).get("headline") or {}
    out = []
    if r.get("robust_before") is not None and r.get("robust_after") is not None:
        out.append(
            f"Red-team robustness {r['robust_before']:.0%} → {r['robust_after']:.0%} after hardening"
        )
    if r.get("cost_per_skill") is not None:
        out.append(f"${r['cost_per_skill']:.2f} of model calls per learned skill")
    if r.get("open_weight_share") is not None:
        out.append(f"{r['open_weight_share']:.0%} of model calls on open weights (Muse Spark Open)")
    if out:
        out.append(f"eval/results.md · {r.get('finished')} {r.get('source')} clips run end to end")
    return out


def build(run: str, url: str, short: bool) -> Path:
    d = run_dir(run)
    meta = json.loads((d / "run.json").read_text())
    note = meta.get("note") or ""
    label = "Replay of a recorded run" + (f" · {note}" if note else "")
    mm, hook = marks("main"), marks("hook")
    end = mm.get("finished", mm["_length"])

    def at(name: str, default: float) -> float:
        return float(mm.get(name, default))

    corr = mm.get("correction")
    red_end = corr if corr is not None else at("finished", end)
    voice_end = min(end, corr + 22) if corr is not None else None
    hook_crop = crop_of(hook.get("_rects", {}))
    ref = d / "artifacts" / "reference_frame.jpg"
    card_png = d / "artifacts" / "card.png"
    close = [("DemoBot", 92, True), ("Show it once.", 52, False), ("", 30, False)]
    close += [(t, 34, False) for t in headline()]
    close += [("", 30, False), ("Built on Meta's Muse Spark, Muse Wonder, SAM 3.1, Muse Voice, Muse Image", 30, False),
              ("and open-weight Muse Spark Open · simulated robot, robot-agnostic program", 30, False),
              ("", 20, False), (url, 34, True)]  # fmt: skip
    with tempfile.TemporaryDirectory() as tmp:
        s = Shots(Path(tmp), label)
        if short:
            s.take(
                "hook", 1.5, hook["_length"], 8, "I showed it once. It learned the task.", hook_crop
            )
            s.take(
                "main",
                at("program", 0),
                at("verify", end),
                7,
                "Muse Wonder writes the robot program and debugs it",
            )
            s.take(
                "main",
                at("stress", 0),
                red_end,
                7,
                "Open-weight Muse Spark agents attack it. Wonder hardens it.",
            )
            s.card(close[:3] + close[3:-5] + [("", 20, False), (url, 34, True)], 8)
        else:
            s.take(
                "hook",
                1.5,
                hook["_length"],
                12,
                "I showed it once. It learned the task.",
                hook_crop,
            )
            s.card([("Programming a robot takes a specialist.", 58, True), ("Everyone else has a phone.", 58, False)],
                   11, image=ref if ref.exists() else None)  # fmt: skip
            s.take("main", at("watch", 0), at("program", end), 25,
                   "Muse Spark watches and listens. SAM 3.1 tracks every object and my hand, in centimetres.")  # fmt: skip
            s.take("main", at("program", 0), at("verify", end), 30,
                   "Muse Wonder writes a robot program, tests it in simulation, and debugs it on its own.")  # fmt: skip
            s.take("main", at("verify", 0), at("stress", end), 25,
                   "It checks itself with the same eyes: SAM looks at the simulation as it looked at me.")  # fmt: skip
            s.take("main", at("stress", 0), red_end, 25 if voice_end else 45,
                   "Open-weight Muse Spark agents attack the program with hard layouts. Wonder hardens it.")  # fmt: skip
            if corr is not None and voice_end is not None:
                s.take(
                    "main", corr - 1, voice_end, 20, "Correct it in plain words, typed or spoken."
                )
            s.take(
                "try",
                2.5,
                marks("try")["_length"],
                13,
                "Move anything. It re-plans, in simulation, for free.",
            )
            if card_png.exists():
                s.still(
                    card_png,
                    5,
                    "The skill card (Muse Image). The skill exports as a robot-agnostic program.",
                )
            s.card(close, 14)
        OUT.mkdir(parents=True, exist_ok=True)
        out = OUT / ("demo_30s.mp4" if short else "demo_final.mp4")
        vo = OUT / "voiceover.wav"
        s.join(out, vo if vo.exists() and not short else None)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="pen-left-of-box")
    ap.add_argument("--url", default=REPO)
    ap.add_argument("--skip-record", action="store_true", help="reuse the takes in data/demo_takes")
    a = ap.parse_args()
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is required")
    corr = correction_text(run_dir(a.run))
    if not a.skip_record:
        record(a.run, corr)
    for short in (False, True):
        out = build(a.run, a.url, short)
        dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
                             capture_output=True, text=True).stdout.strip()  # fmt: skip
        print(f"{out.relative_to(ROOT)}: {float(dur):.1f} s")


if __name__ == "__main__":
    main()
