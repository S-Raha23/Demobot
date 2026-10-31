"""One-off: turn runs whose corrections overwrote the demo skill into versioned skills (docs/11
Fix 0, item 2). taskspec.json goes back to the demo skill; each correction's spec becomes
taskspec_v<n>.json; skills.json lists the versions; run.json gets back the demo title and program.

    uv run python scripts/migrate_skill_versions.py [run dirs...]   (default: all runs)
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def migrate(d: Path) -> str:
    art = d / "artifacts"
    corr = sorted(art.glob("correction_*.json"), key=lambda p: int(re.findall(r"\d+", p.name)[0]))
    if not corr or (art / "skills.json").exists():
        return "skip"
    meta = json.loads((d / "run.json").read_text())
    title = str(meta.get("title", ""))
    m = re.search(r"\((?:corrected by \w+; )?demo: (.*)\)$", title)
    card = art / "card.json"
    demo_title = (
        json.loads(card.read_text()).get("title") if card.exists() else (m.group(1) if m else title)
    )
    current = (art / "taskspec.json").read_text()  # the spec after the last correction
    specs = []
    for k in range(1, len(corr) + 1):
        before = art / f"taskspec_before_correction_{k}.json"
        specs.append(before.read_text() if before.exists() else None)
    demo_spec = specs[0] or current
    versions = [{"version": 1, "label": "from your demo", "title": demo_title, "taskspec": "taskspec.json",
                 "program_version": json.loads(corr[0].read_text())["program_before"]}]  # fmt: skip
    for k, c in enumerate(corr, start=1):
        rec = json.loads(c.read_text())
        after = specs[k] if k < len(specs) and specs[k] else current
        name = f"taskspec_v{k + 1}.json"
        (art / name).write_text(after)
        sp = json.loads(after)
        how = "voice" if (art / f"correction_{k}.wav").exists() else "text"
        versions.append({"version": k + 1, "label": f"corrected by {how}", "title": str(rec.get("gloss") or sp["summary"]).rstrip("."),
                         "taskspec": name, "program_version": rec["program_after"], "said": rec["transcript"]["text"],
                         "language": rec["transcript"].get("language", ""), "from_version": k})  # fmt: skip
        rec |= {"version": k + 1, "taskspec": name}
        c.write_text(json.dumps(rec, indent=1, ensure_ascii=False))
    (art / "taskspec.json").write_text(demo_spec)
    (art / "skills.json").write_text(json.dumps(versions, indent=1, ensure_ascii=False))
    meta["title"] = demo_title
    meta["program_version"] = versions[0]["program_version"]
    (d / "run.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    return f"{len(versions)} versions"


def main() -> None:
    dirs = [Path(a) for a in sys.argv[1:]] or [
        *sorted((ROOT / "backend" / "tests" / "fixtures" / "runs").iterdir()),
        *sorted((ROOT / "data" / "runs").iterdir()),
    ]
    for d in dirs:
        if (d / "run.json").exists():
            print(f"{d.name}: {migrate(d)}")


if __name__ == "__main__":
    main()
