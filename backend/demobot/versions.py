"""Skill versions of a run (docs/11 Fix 0, items 2 and 3).

v1 is the skill learned from the demo (taskspec.json and its program). Every spoken correction adds
a version (its own taskspec file and program) and never overwrites v1, so the library, Try-it and
the run page always show one consistent record: title, goal and program from the same version.

    artifacts/skills.json: [{"version": 1, "label": "from your demo", "title": ..., "taskspec":
        "taskspec.json", "program_version": 3}, {"version": 2, "label": "corrected by voice", ...}]
"""

import json
from pathlib import Path
from typing import Any

from demobot.schemas import Program, TaskSpec


def _programs(d: Path) -> list[dict[str, Any]]:
    p = d / "artifacts" / "programs.json"
    return json.loads(p.read_text()) if p.exists() else []


def _demo_program(d: Path) -> int | None:
    """The program the demo skill uses: the one a first correction started from, else the latest
    one that passed the demo."""
    c = d / "artifacts" / "correction_1.json"
    if c.exists():
        return int(json.loads(c.read_text())["program_before"])
    ok = [p["version"] for p in _programs(d) if p.get("passed_demo")]
    allv = [p["version"] for p in _programs(d)]
    return max(ok) if ok else (max(allv) if allv else None)


def load(d: Path) -> list[dict[str, Any]]:
    p = d / "artifacts" / "skills.json"
    if p.exists():
        return list(json.loads(p.read_text()))
    meta = json.loads((d / "run.json").read_text()) if (d / "run.json").exists() else {}
    card = d / "artifacts" / "card.json"
    title = json.loads(card.read_text()).get("title") if card.exists() else meta.get("title")
    return [{"version": 1, "label": "from your demo", "title": title or meta.get("title", ""),
             "taskspec": "taskspec.json", "program_version": _demo_program(d)}]  # fmt: skip


def save(d: Path, versions: list[dict[str, Any]]) -> None:
    (d / "artifacts" / "skills.json").write_text(json.dumps(versions, indent=1, ensure_ascii=False))


def get(d: Path, version: int | None = None) -> dict[str, Any]:
    vs = load(d)
    if version is None:
        return vs[0]
    for v in vs:
        if v["version"] == version:
            return v
    raise KeyError(version)


def spec(d: Path, v: dict[str, Any]) -> TaskSpec:
    return TaskSpec.model_validate_json((d / "artifacts" / v["taskspec"]).read_text())


def program(d: Path, v: dict[str, Any]) -> Program | None:
    want = v.get("program_version")
    for p in _programs(d):
        if p["version"] == want:
            return Program.model_validate(p)
    return None
