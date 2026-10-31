"""Build the synthetic evaluation set: n clips cycling through the 5 task families.

uv run python -m synth.make_set --n 10 --seed 7 [--out data/synth/set7] [--workers 3]
"""

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from synth.demo import FAMILIES, make_clip

ROOT = Path(__file__).resolve().parents[1]


def _one(args: tuple[str, int, str]) -> dict[str, object]:
    family, seed, out = args
    t0 = time.monotonic()
    truth = make_clip(family, seed, Path(out))
    return {"dir": out, "family": family, "seed": seed, "summary": truth["summary"],
            "duration_s": truth["duration_s"], "objects": len(truth["objects"]),
            "steps": len(truth["steps"]), "secs": round(time.monotonic() - t0, 1)}  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=None)
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    out = Path(a.out) if a.out else ROOT / "data" / "synth" / f"set{a.seed}"
    jobs = [(FAMILIES[i % len(FAMILIES)], a.seed * 1000 + i, str(out / f"{i:02d}_{FAMILIES[i % len(FAMILIES)]}"))
            for i in range(a.n)]  # fmt: skip
    with ProcessPoolExecutor(a.workers) as ex:
        rows = list(ex.map(_one, jobs))
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.json").write_text(json.dumps(rows, indent=1))
    for r in rows:
        print(
            f"{r['dir']}: {r['summary']} ({r['duration_s']} s, {r['secs']} s to render)",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
