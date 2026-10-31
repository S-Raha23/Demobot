"""Bake finished runs into backend/tests/fixtures/runs/ (and so the Docker image) for replay.

    uv run python scripts/bake_runs.py syn7-01_next_to:pen-left-of-box [syn7-00_place_in:pens-in-cup ...]

Large files the UI never loads (the upload, the raw display video, the analysis clip, fault-
injection sims) are left out. Run ids inside events and artifacts are rewritten to the new id.
"""

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from demobot.config import settings  # noqa: E402

DEST = ROOT / "backend" / "tests" / "fixtures" / "runs"
SKIP = shutil.ignore_patterns("input", "display_raw.mp4", "analysis.mp4", "*.video.mp4", "fault-*",
                              "correction_upload_*", "clean_plate.jpg")  # fmt: skip


def bake(src_id: str, new_id: str) -> Path:
    src = settings.data_path / "runs" / src_id
    dst = DEST / new_id
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=SKIP)
    lines = []
    for line in (dst / "events.jsonl").read_text().splitlines():
        if line.strip():
            e = json.loads(line)
            e["run_id"] = new_id
            lines.append(json.dumps(e, separators=(",", ":"), ensure_ascii=False))
    (dst / "events.jsonl").write_text("\n".join(lines) + "\n")
    meta = json.loads((dst / "run.json").read_text())
    meta |= {"run_id": new_id, "baked_from": src_id, "status": "done", "fixture": False,
             "note": "real model calls; the input clip is synthetic" if "synthetic" in str(meta.get("source", "")) or src_id.startswith("syn")
             else "real model calls on a real clip"}  # fmt: skip
    (dst / "run.json").write_text(json.dumps(meta, indent=1))
    card = dst / "artifacts" / "card.json"
    if card.exists():
        c = json.loads(card.read_text())
        c["skill_id"] = c["run_id"] = new_id
        card.write_text(json.dumps(c, indent=1))
        meta["title"] = c["title"]  # what was learned, not the clip's file name
        (dst / "run.json").write_text(json.dumps(meta, indent=1))
    size = sum(f.stat().st_size for f in dst.rglob("*") if f.is_file()) / 1e6
    print(f"{src_id} -> {dst.relative_to(ROOT)} ({size:.1f} MB)")
    return dst


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        src_id, _, new_id = arg.partition(":")
        bake(src_id, new_id or src_id)
