"""Stage: card. Muse Image turns the real final frame into an illustrated skill card (anchored edit),
and the skill joins the library (docs/04 §13–14)."""

import base64
import io
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from demobot import gateway, providers
from demobot.config import settings
from demobot.errors import DemoBotError
from demobot.events import RunContext
from demobot.schemas import GoalClause, SkillCard, TaskSpec
from demobot.verify import clause_words


def _name(sel: Any) -> str:
    from demobot.perceive import base_phrase

    if sel is None:
        return "the spot"
    if sel.name:
        return "the " + base_phrase(sel.name)
    if sel.kind:
        return f"every {sel.kind}"
    if sel.names:
        return " and ".join("the " + base_phrase(n) for n in sel.names)
    return f"every {sel.role} item" if sel.role else "the items"


def _rel(pred: str) -> str:
    return {"left_of": "left of", "right_of": "right of", "in_front_of": "in front of", "behind": "behind",
            "inside": "in", "near": "near"}.get(pred, pred)  # fmt: skip


def title_of(spec: TaskSpec) -> str:
    """An imperative title from the goal: 'Put every pen in the white cup'."""
    parts = []
    for c in spec.goal[:2]:
        if c.pred == "swapped":
            parts.append(f"Swap {_name(c.select)}")
        elif c.pred == "collinear":
            parts.append("Line up " + _name(c.select).replace("every moved item", "the items"))
        else:
            parts.append(f"Put {_name(c.select)} {_rel(c.pred)} {_name(c.target)}")
    t = "; ".join(parts) or spec.summary.rstrip(".")
    t = t.replace("Put every", "Put each") if len(spec.goal) > 1 else t
    return t if len(t) <= 56 else t[:53].rsplit(" ", 1)[0] + "…"


def steps_of(goal: list[GoalClause]) -> list[str]:
    """At most 3 steps of at most 8 words each, from the generalised goal."""
    if len(goal) > 1:
        return [
            f"Put {_name(c.select).replace('every ', 'each ')} {_rel(c.pred)} {_name(c.target)}"[
                :60
            ]
            for c in goal[:3]
        ]
    c = goal[0] if goal else None
    if c is None:
        return []
    obj, tgt = _name(c.select), _name(c.target)
    if c.pred == "inside":
        return [f"Find {obj.replace('every ', 'each ')}", "Pick it up", f"Drop it into {tgt}"]
    if c.pred == "swapped":
        names = (c.select.names or ["a", "b"]) + ["", ""]
        a_, b_ = _name(type(c.select)(name=names[0])), _name(type(c.select)(name=names[1]))
        return [
            f"Park {a_} in a free spot",
            f"Move {b_} into its place",
            f"Put {a_} in the freed spot",
        ]
    if c.pred == "collinear":
        return [
            "Find the items to line up",
            "Clear a row across the table",
            "Place them left to right",
        ]
    return [
        f"Find {obj}",
        f"Clear the space {_rel(c.pred)} {tgt}",
        f"Place it {_rel(c.pred)} {tgt}",
    ]


def card_prompt(title: str, steps: list[str]) -> str:
    numbered = "; ".join(f"{i + 1}. {s}" for i, s in enumerate(steps))
    return (
        f"Turn this photo into a clean, friendly instruction card titled '{title}', with these numbered steps: "
        f"{numbered}. Keep the same objects in the same places, drawn in flat colours on a white background, "
        "with a small icon-style robot arm in one corner. No other text."
    )


async def generate(ctx: RunContext, frame: Path, title: str, steps: list[str], out: Path) -> bool:
    """Muse Image anchored edit; False if it was refused or failed (the caller draws a template)."""
    prompt = card_prompt(title, steps)

    async def call(timeout: float) -> tuple[Any, float, dict[str, Any]]:
        with frame.open("rb") as f:
            resp = (
                await providers.client("meta")
                .with_options(timeout=timeout)
                .images.edit(model=settings.model_image, image=f, prompt=prompt)
            )
        d = providers.dump(resp)
        return {"b64": (d.get("data") or [{}])[0].get("b64_json")}, 0.01, {"images": 1}

    try:
        raw = await gateway.cached_call(ctx=ctx, purpose="card", provider="meta", model=settings.model_image,
                                        request={"stage": "card", "frame": gateway.sha256_file(frame), "prompt": prompt},
                                        estimate_usd=0.02, call=call, validate=gateway.passthrough)  # fmt: skip
    except DemoBotError as e:
        ctx.emit("log", payload={"fallback": True, "purpose": "card", "from": "Muse Image", "to": "template card",
                                 "code": e.code, "message": f"Muse Image unavailable ({e.code}); drawing a template card"})  # fmt: skip
        return False
    if not raw.get("b64"):
        return False
    Image.open(io.BytesIO(base64.b64decode(raw["b64"]))).convert("RGB").save(out)
    return True


def template(frame: Path, title: str, steps: list[str], out: Path) -> None:
    """The fallback card: the real final frame with the title and steps beneath it."""
    img = Image.open(frame).convert("RGB")
    w = 1024
    img = img.resize((w, round(img.height * w / img.width)))
    card = Image.new("RGB", (w, img.height + 90 + 46 * len(steps)), "white")
    card.paste(img, (0, 0))
    d = ImageDraw.Draw(card)
    big: Any
    small: Any
    try:
        big = ImageFont.truetype("DejaVuSans-Bold.ttf", 34)
        small = ImageFont.truetype("DejaVuSans.ttf", 26)
    except OSError:
        big = small = ImageFont.load_default()
    d.text((28, img.height + 22), title, fill="#111827", font=big)
    for i, s in enumerate(steps):
        d.text((28, img.height + 76 + 46 * i), f"{i + 1}. {s}", fill="#374151", font=small)
    card.save(out)


async def make_card(ctx: RunContext, run_dir: Path, spec: TaskSpec, robustness: float | None, cost: float,
                    program_version: int) -> SkillCard:  # fmt: skip
    art = run_dir / "artifacts"
    frame = art / "reference_frame.jpg"
    title, steps = title_of(spec), steps_of(spec.goal)
    out = art / "card.png"
    made = await generate(ctx, frame, title, steps, out) if frame.exists() else False
    if not made and frame.exists():
        template(frame, title, steps, out)
    card = SkillCard(skill_id=run_dir.name, title=title, description=spec.generalization or spec.summary,
                     image="artifacts/card.png" if out.exists() else None, goal_text="; ".join(clause_words(c) for c in spec.goal),
                     program_version=program_version, robustness=robustness, cost_to_learn_usd=round(cost, 4), run_id=run_dir.name)  # fmt: skip
    (art / "card.json").write_text(card.model_dump_json(indent=1))
    (art / "card_meta.json").write_text(
        json.dumps({"by": "Muse Image" if made else "template", "steps": steps})
    )
    return card
