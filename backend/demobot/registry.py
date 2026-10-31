"""The table's object registry and the crop check (docs/11 Fix 0, items 1 and 4).

Watch names the same physical object differently from clip to clip ("white box" / "white plastic
tub", "green ball" / "yellow tennis ball"), and a teal box cutter next to two teal pens is easily
called a third pen. After SAM has tracked the objects, one cheap vision call sees a crop of every
tracked object and says which registry object it is. The TaskSpec, the tracks and the final masks
are then rewritten to the canonical names and kinds, so "every pen" selects the pens and nothing
else, and every run, card and Try-it page uses the same names.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from pydantic import BaseModel

from demobot import gateway, providers
from demobot.config import ROOT, settings
from demobot.errors import DemoBotError
from demobot.events import RunContext
from demobot.llm import chat_text, output_text, parse_json
from demobot.schemas import GoalClause, Selector, TaskSpec, Track
from demobot.schemas_util import strict_schema

DEFAULT = ROOT / "backend" / "demobot" / "table_registry.json"
ORDINALS = ("left", "middle", "right")


@dataclass
class Entry:
    name: str  # canonical, e.g. "teal pen"
    kind: str
    color: str
    size_cm: tuple[float, float, float]
    count: int
    looks: str  # what tells it apart, for the crop check
    shape: str = "box"  # box | cylinder | sphere: the twin's stand-in


def load(path: Path | None = None) -> list[Entry]:
    """The table's registry: data/registry/table.json if the person made one, else the default."""
    p = path or settings.data_path / "registry" / "table.json"
    raw = json.loads((p if p.exists() else DEFAULT).read_text())
    return [Entry(e["name"], e["kind"], e["color"], tuple(e["size_cm"]), int(e.get("count", 1)), e["looks"], e.get("shape", "box"))
            for e in raw["objects"]]  # fmt: skip


def entry_for(name: str, entries: list[Entry] | None = None) -> Entry | None:
    """The registry entry behind a canonical object name ("left teal pen" -> "teal pen")."""
    base = re.sub(rf"^({'|'.join(ORDINALS)}) |\s\d+$", "", name.strip().lower())
    return next((e for e in (entries if entries is not None else load()) if e.name == base), None)


class Label(BaseModel):
    crop: int
    object: str  # a registry name, or "other"
    confidence: float


class Labels(BaseModel):
    labels: list[Label]


def crop_grid(
    video: Path, tracks: list[Track], tile: int = 200
) -> tuple[np.ndarray, list[str]] | None:
    """One image with a numbered crop of every tracked object (from an early frame where it is
    seen, before the hand reaches it), and the track names in crop order."""
    cap = cv2.VideoCapture(str(video))
    frames: list[np.ndarray] = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f)
    cap.release()
    tiles: list[np.ndarray] = []
    names: list[str] = []
    for t in tracks:
        if t.name == "hand" or "not_found" in t.flags:
            continue
        seen = [
            (k, f.bbox_px)
            for k, f in enumerate(t.frames)
            if f.bbox_px is not None and k < len(frames)
        ]
        if not seen:
            continue
        k, box = seen[min(len(seen) - 1, 2)]
        x0, y0, x1, y1 = box
        pad = 0.35 * max(x1 - x0, y1 - y0) + 8
        h, w = frames[k].shape[:2]
        c = frames[k][
            max(0, int(y0 - pad)) : min(h, int(y1 + pad)),
            max(0, int(x0 - pad)) : min(w, int(x1 + pad)),
        ]
        if c.size == 0:
            continue
        s = tile / max(c.shape[:2])
        c = cv2.resize(c, (max(1, int(c.shape[1] * s)), max(1, int(c.shape[0] * s))))
        canvas = np.full((tile + 28, tile, 3), 24, np.uint8)
        canvas[28 : 28 + c.shape[0], : c.shape[1]] = c
        cv2.putText(
            canvas, str(len(tiles) + 1), (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2
        )
        tiles.append(canvas)
        names.append(t.name)
    if not tiles:
        return None
    cols = min(4, len(tiles))
    rows = -(-len(tiles) // cols)
    grid = np.full((rows * (tile + 28), cols * tile, 3), 24, np.uint8)
    for i, im in enumerate(tiles):
        row, col = divmod(i, cols)
        grid[row * (tile + 28) : (row + 1) * (tile + 28), col * tile : (col + 1) * tile] = im
    return grid, names


async def identify(ctx: RunContext, grid_path: Path, n: int, entries: list[Entry]) -> list[Label]:
    """Which registry object is each numbered crop (one vision call, cached)."""
    menu = "\n".join(f"- {e.name} ({e.count} on this table): {e.looks}" for e in entries)
    text = (
        f"The image shows {n} numbered crops of objects on a table (number in the top-left of each crop). "
        f"The objects that can be on this table are:\n{menu}\n- other: anything not listed (e.g. the person's hand).\n"
        "For every crop, say which object it is (the object in the centre of the crop). Look closely at shape and compare "
        "the crops with each other: a pen is a thin round rod with a clip and a tip; a box cutter is flatter and wider, with a "
        "blade slider and no clip. Each object exists only as many times as listed, so two crops cannot both be the one "
        "box cutter. "
        'Return JSON {"labels": [{"crop": number, "object": name or "other", "confidence": 0..1}]}.'
    )
    url = (
        "data:image/jpeg;base64," + __import__("base64").b64encode(grid_path.read_bytes()).decode()
    )
    req = {"stage": "identify", "text": text, "img": gateway.sha256_file(grid_path)}
    fmt = {
        "type": "json_schema",
        "json_schema": {"name": "Labels", "schema": strict_schema(Labels), "strict": True},
    }
    content = [{"type": "text", "text": text}, {"type": "image_url", "image_url": {"url": url}}]

    def chat(provider: str, model: str) -> gateway.Call:
        return providers.chat_call(provider, model, affinity_key=ctx.run_id, messages=[{"role": "user", "content": content}],
                                   response_format=fmt, max_tokens=2500, reasoning_effort="low")  # fmt: skip

    spark = providers.responses_call(
        settings.model_spark,
        input=[{"role": "user", "content": [{"type": "input_text", "text": text}, {"type": "input_image", "image_url": url}]}],
        text={"format": {"type": "json_schema", "name": "Labels", "schema": Labels.model_json_schema()}},
        reasoning={"effort": "low"}, max_output_tokens=2500,
    )  # fmt: skip

    def validate(raw: Any) -> list[Label]:
        t = output_text(raw) if "output" in raw else chat_text(raw)
        try:
            return Labels.model_validate(parse_json(t, "perceive")).labels
        except DemoBotError:
            raise
        except Exception as e:
            raise DemoBotError("INVALID_MODEL_OUTPUT", str(e)[:300], stage="perceive") from e

    routes = [
        gateway.Route("baseten", settings.model_spark_open, req, 0.01, chat("baseten", settings.model_spark_open), "Muse Spark Open @ Baseten"),
        gateway.Route("modal", settings.model_spark_open_modal, req, 0.01, chat("modal", settings.model_spark_open_modal), "Muse Spark Open @ Modal"),
        gateway.Route("meta", settings.model_spark, req, 0.01, spark, "Muse Spark 1.3"),
    ]  # fmt: skip
    labels, _ = await gateway.chain_call(
        ctx=ctx, purpose="identify", routes=routes, validate=validate
    )
    return labels


def _first_x(t: Track) -> float:
    return next((f.centroid_px[0] for f in t.frames if f.centroid_px), 0.0)


def plan_renames(spec: TaskSpec, tracks: list[Track], labels: dict[str, tuple[str, float]],
                 entries: list[Entry]) -> dict[str, Entry | None]:  # fmt: skip
    """Old object name -> registry entry (None: keep as is). Several objects of one entry get
    ordinal names left to right; an entry seen more often than it exists keeps only its most
    confident matches (the rest stay as they were, so nothing is silently dropped)."""
    by_name = {e.name: e for e in entries}
    by_entry: dict[str, list[tuple[float, str]]] = {}
    for o in spec.objects:
        lab = labels.get(o.name)
        if lab and lab[0] in by_name and lab[1] >= 0.4:
            by_entry.setdefault(lab[0], []).append((lab[1], o.name))
    out: dict[str, Entry | None] = {o.name: None for o in spec.objects}
    for ename, cands in by_entry.items():
        keep = sorted(cands, reverse=True)[: by_name[ename].count]
        for _, nm in keep:
            out[nm] = by_name[ename]
    return out


def new_names(spec: TaskSpec, tracks: list[Track], plan: dict[str, Entry | None]) -> dict[str, str]:
    xs = {t.name: _first_x(t) for t in tracks}
    groups: dict[str, list[str]] = {}
    for old, e in plan.items():
        if e is not None:
            groups.setdefault(e.name, []).append(old)
    names: dict[str, str] = {}
    for ename, olds in groups.items():
        if len(olds) == 1:
            names[olds[0]] = ename
            continue
        ordered = sorted(olds, key=lambda nm: xs.get(nm, 0.0))
        words = (
            ("left", "right")
            if len(ordered) == 2
            else ORDINALS
            if len(ordered) == 3
            else tuple(str(i + 1) for i in range(len(ordered)))
        )
        for w, nm in zip(words, ordered, strict=False):
            names[nm] = f"{w} {ename}" if not w.isdigit() else f"{ename} {w}"
    return names


def _sel(s: Selector | None, names: dict[str, str], kinds: dict[str, str]) -> Selector | None:
    if s is None:
        return None
    return s.model_copy(update={"name": names.get(s.name, s.name) if s.name else s.name,
                                "names": [names.get(n, n) for n in s.names] if s.names else s.names,
                                "kind": kinds.get(s.kind, s.kind) if s.kind else s.kind})  # fmt: skip


def apply(spec: TaskSpec, plan: dict[str, Entry | None], names: dict[str, str]) -> TaskSpec:
    """The TaskSpec with canonical names and kinds everywhere (objects, steps, goal)."""
    # a goal's kind selector follows what its objects really are: "pen" stays "pen", and an
    # object that was called a pen but is a cutter no longer matches it
    votes: dict[str, dict[str, int]] = {}
    for o in spec.objects:
        e = plan.get(o.name)
        if e is not None:
            votes.setdefault(o.kind, {}).setdefault(e.kind, 0)
            votes[o.kind][e.kind] += 1
    # a kind that is itself a registry kind keeps it ("pen" stays "pen" even if one "pen" was the cutter)
    kinds = {old: old if old in v else max(v, key=lambda k: v[k]) for old, v in votes.items()}
    objects = []
    for o in spec.objects:
        e = plan.get(o.name)
        if e is None:
            objects.append(o)
            continue
        objects.append(o.model_copy(update={"name": names[o.name], "kind": e.kind, "color": e.color,
                                            "alt_names": sorted({o.name, *o.alt_names} - {names[o.name]})}))  # fmt: skip
    steps = [st.model_copy(update={"object": names.get(st.object, st.object),
                                   "target": names.get(st.target, st.target) if st.target else st.target}) for st in spec.steps]  # fmt: skip
    goal = [GoalClause.model_validate(c.model_dump() | {
        "select": _sel(c.select, names, kinds), "target": _sel(c.target, names, kinds),
        "order": [names.get(n, n) for n in c.order] if c.order else c.order}) for c in spec.goal]  # fmt: skip
    summary = spec.summary
    for old, new in sorted(names.items(), key=lambda kv: -len(kv[0])):
        summary = re.sub(rf"\b{re.escape(old)}\b", new, summary)
    return spec.model_copy(
        update={"objects": objects, "steps": steps, "goal": goal, "summary": summary}
    )
