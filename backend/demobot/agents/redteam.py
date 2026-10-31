"""The red team: a Muse Spark Open swarm invents hard but solvable layouts to break the program,
and Muse Wonder hardens it (docs/05 §C, docs/04 §10)."""

import asyncio
import json
from collections import Counter
from typing import Any

from pydantic import BaseModel, Field

from demobot import gateway, goal_dsl, providers
from demobot.config import settings
from demobot.errors import DemoBotError
from demobot.events import RunContext
from demobot.llm import chat_text, parse_json
from demobot.program import sandbox
from demobot.schemas import GoalClause, Layout, SceneObject, SimResult
from demobot.schemas_util import strict_schema
from demobot.sim.layouts import validate as validate_layout
from demobot.sim.skills import insert_mode

PERSONAS: dict[str, str] = {
    "crowder": "Pack the objects close together (but at least 2.5 cm apart) so grasps and placements risk collisions.",
    "edge_walker": "Put objects and their targets near the edges of the work area and the limits of the robot's reach.",
    "twin_maker": "Add one extra copy of a moved kind of object (new name, same kind and size), testing that the program generalises.",
    "distractor": "Add one or two unrelated objects that the goal does not mention; they must not be moved.",
    "mirror": "Mirror or rotate the scene, and move containers or references to the opposite side.",
    "squeezer": "Leave just enough room for the goal: tight space next to references or for a row, but still feasible.",
}
LAYOUTS_PER_PERSONA = 2
CLEARANCE_CM = 2.0


class ProposedObject(BaseModel):
    name: str
    x: float
    y: float
    yaw: float = 0.0
    new_kind: str = Field(
        "", description="only for a new object: its kind; empty for existing objects"
    )
    copy_of: str = Field(
        "", description="only for a twin: the existing object it copies; empty otherwise"
    )
    size_cm: list[float] = Field(
        default_factory=list, description="only for a new distractor: [w, d, h]"
    )


class ProposedLayout(BaseModel):
    why_hard: str
    objects: list[ProposedObject]


class Proposal(BaseModel):
    layouts: list[ProposedLayout]


def _prompt(persona: str, layout: Layout, goal: list[GoalClause]) -> str:
    wa = layout.work_area
    sizes = "\n".join(f"- {o.name}: kind {o.kind}, role {o.role}, {o.shape} {o.w:.1f}×{o.d:.1f}×{o.h:.1f} cm, now at ({o.x:.1f}, {o.y:.1f})"
                      for o in layout.objects)  # fmt: skip
    return (
        f"You are a red-team tester for a robot program. Persona: {persona}. {PERSONAS[persona]}\n\n"
        f"The program must achieve this goal on any layout of these objects:\n{json.dumps([g.model_dump(exclude_none=True) for g in goal])}\n\n"
        f"Objects (table centimetres; +x right, +y towards the robot):\n{sizes}\n\n"
        f"Work area: x {wa.x0:.0f}..{wa.x1:.0f}, y {wa.y0:.0f}..{wa.y1:.0f}. The robot base is at ({layout.robot_base_cm[0]:.0f}, "
        f"{layout.robot_base_cm[1]:.0f}) and reaches 25–80 cm from it.\n\n"
        f"Propose {LAYOUTS_PER_PERSONA} different starting layouts that are as hard as possible for a careless program, "
        "but still solvable: every object fully inside the work area, at least 2.5 cm between any two objects, all reachable, "
        "nothing already satisfying the goal, nothing stacked. List every existing object with its new x, y and yaw "
        "(degrees). Containers and references may move too. Add new objects only if your persona says so. "
        'Return JSON {"layouts": [{"why_hard": "<one sentence>", "objects": [...]}]}.'
    )


def build(base: Layout, p: ProposedLayout, persona: str, idx: int) -> Layout:
    by = {o.name: o for o in base.objects}
    objs: dict[str, SceneObject] = {}
    for po in p.objects:
        if po.name in by:
            objs[po.name] = by[po.name].model_copy(
                update={"x": round(po.x, 1), "y": round(po.y, 1), "yaw": round(po.yaw, 1)}
            )
        elif po.copy_of in by:
            src = by[po.copy_of]
            objs[po.name] = src.model_copy(
                update={
                    "name": po.name,
                    "x": po.x,
                    "y": po.y,
                    "yaw": po.yaw,
                    "texture": src.texture,
                }
            )
        elif po.new_kind:
            w, d, h = [*po.size_cm, 5.0, 5.0, 3.0][:3] if po.size_cm else (5.0, 5.0, 3.0)
            objs[po.name] = SceneObject(name=po.name, kind=po.new_kind.lower(), role="distractor", x=po.x, y=po.y, yaw=po.yaw,
                                        w=max(1.0, w), d=max(1.0, d), h=max(0.5, h), color="#8a8f98")  # fmt: skip
    for name, o in by.items():  # an object the persona forgot stays where it was
        objs.setdefault(name, o)
    return base.model_copy(update={"id": f"red-{idx:02d}", "source": f"redteam:{persona}", "description": p.why_hard[:200],
                                   "objects": list(objs.values())})  # fmt: skip


def check(layout: Layout, goal: list[GoalClause]) -> list[str]:
    """The validator (no LLM): bounds, overlaps, reach, containers that can take their goal
    objects, goal selectors that resolve, and a goal not already satisfied."""
    problems = validate_layout(layout)
    state = goal_dsl.to_state(layout.objects)
    for i, a in enumerate(layout.objects):
        for b in layout.objects[i + 1 :]:
            if (
                goal_dsl.footprint_gap(a, b) < CLEARANCE_CM
                and f"{a.name} and {b.name} overlap" not in problems
            ):
                problems.append(f"{a.name} and {b.name} are closer than {CLEARANCE_CM} cm")
    for c in goal:
        if c.select.name and c.select.name not in state:
            problems.append(f"the goal needs {c.select.name}")
        if c.target and c.target.name and c.target.name not in state:
            problems.append(f"the goal needs {c.target.name}")
        if c.pred == "inside" and c.target:
            for box in goal_dsl.select(c.target, state):
                for o in goal_dsl.select(c.select, state):
                    if insert_mode(o, box) == "upright" and o.h > box.h * 3:
                        problems.append(f"{o.name} cannot fit in {box.name}")
    if goal and goal_dsl.all_hold(goal_dsl.evaluate(goal, state, state)):
        problems.append("the goal already holds")
    return sorted(set(problems))


async def propose(
    ctx: RunContext, persona: str, base: Layout, goal: list[GoalClause]
) -> list[tuple[Layout, str]]:
    """Two valid layouts from one persona (one repair round; invalid ones are dropped)."""
    prompt = _prompt(persona, base, goal)
    fmt = {
        "type": "json_schema",
        "json_schema": {"name": "Proposal", "schema": strict_schema(Proposal), "strict": True},
    }
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    out: list[tuple[Layout, str]] = []
    for attempt in range(2):
        req = {"stage": "redteam", "persona": persona, "messages": messages}

        def route(
            provider: str,
            model: str,
            req: dict[str, Any] = req,
            messages: list[dict[str, Any]] = messages,
        ) -> gateway.Route:
            return gateway.Route(provider, model, req, 0.03, providers.chat_call(provider, model, messages=messages,
                                 response_format=fmt, max_tokens=12000, temperature=0.8), f"{model} @ {provider}")  # fmt: skip

        def validate(raw: Any) -> Proposal:
            try:
                return Proposal.model_validate(parse_json(chat_text(raw), "stress"))
            except DemoBotError:
                raise
            except Exception as e:
                raise DemoBotError("INVALID_MODEL_OUTPUT", str(e)[:300], stage="stress") from e

        try:
            prop, _ = await gateway.chain_call(ctx=ctx, purpose=f"redteam:{persona}", validate=validate,
                                               routes=[route("baseten", settings.model_spark_open),
                                                       route("modal", settings.model_spark_open_modal)])  # fmt: skip
        except DemoBotError as e:
            ctx.emit("log", payload={"message": f"red-team persona {persona} failed ({e.code})"})
            return out
        bad: list[str] = []
        for p in prop.layouts[: LAYOUTS_PER_PERSONA - len(out)]:
            lay = build(base, p, persona, 0)
            problems = check(lay, goal)
            if problems:
                bad.append(f"layout '{p.why_hard[:60]}': " + "; ".join(problems)[:300])
            else:
                out.append((lay, p.why_hard))
        if len(out) >= LAYOUTS_PER_PERSONA or not bad or attempt == 1:
            if bad:
                ctx.emit(
                    "log",
                    payload={
                        "message": f"{persona}: dropped {len(bad)} invalid layout(s) after repair"
                    },
                )
            return out
        messages = [*messages, {"role": "assistant", "content": prop.model_dump_json()},
                    {"role": "user", "content": "The validator rejected these layouts:\n" + "\n".join(bad)
                     + f"\nReturn {LAYOUTS_PER_PERSONA - len(out)} corrected layout(s) in the same JSON format."}]  # fmt: skip
    return out


async def red_team(
    ctx: RunContext, base: Layout, goal: list[GoalClause]
) -> list[tuple[Layout, str, str]]:
    """All personas in parallel: (layout with id red-NN, persona, why_hard)."""
    ctx = ctx.at("stress")
    results = await asyncio.gather(*(propose(ctx, p, base, goal) for p in PERSONAS))
    out: list[tuple[Layout, str, str]] = []
    for persona, layouts in zip(PERSONAS, results, strict=True):
        for lay, why in layouts:
            out.append((lay.model_copy(update={"id": f"red-{len(out):02d}"}), persona, why))
    return out


async def simulate_all(ctx: RunContext, code: str, layouts: list[Layout], goal: list[GoalClause], version: int,
                       tag: str = "stress") -> list[SimResult]:  # fmt: skip
    """Every layout in parallel on the local process pool; goals re-evaluated on each layout's own
    initial state (the simulator does that)."""
    ctx = ctx.at(tag)

    async def one(lay: Layout) -> SimResult:
        res = await sandbox.simulate(code, lay, goal, render=True, workers=4)
        passed = sum(r.holds for r in res.goal_results)
        ctx.emit("tool_call", payload={"agent": "redteam", "iteration": version, "tool": "simulate",
                                       "args": {"layout": lay.id, "program": version, "persona": lay.source.split(":")[-1]},
                                       "result": {"ok": res.goal_ok, "layout": lay.id, "clauses_passed": passed,
                                                  "clauses_total": len(res.goal_results),
                                                  "error": (res.error or "").splitlines()[-1] if res.error else None}})  # fmt: skip
        return res

    return list(await asyncio.gather(*(one(lay) for lay in layouts)))


def clusters(cases: list[tuple[Layout, SimResult]]) -> list[dict[str, Any]]:
    """Failures grouped by (first failing clause or error, persona)."""
    keys: Counter[tuple[str, str]] = Counter()
    for lay, res in cases:
        if res.goal_ok:
            continue
        what = res.error_type or next(
            (r.detail for r in res.goal_results if not r.holds), "goal failed"
        )
        keys[(what[:120], lay.source.split(":")[-1])] += 1
    return [{"failure": k[0], "persona": k[1], "count": n} for k, n in keys.most_common()]


def harden_brief(cases: list[tuple[Layout, SimResult]]) -> str:
    lines = ["## Red-team layouts where the current program fails",
             "Fix the root cause so the program works on every layout; do not special-case one layout. "
             "You can simulate on these layout ids as well as \"demo\"; submit only after \"demo\" passes."]  # fmt: skip
    for lay, res in cases:
        if res.goal_ok:
            continue
        failed = [r.detail for r in res.goal_results if not r.holds]
        err = (res.error or "").splitlines()[-1] if res.error else ""
        objs = ", ".join(f"{o.name} ({o.x:.0f}, {o.y:.0f})" for o in lay.objects)
        lines.append(
            f"- {lay.id} [{lay.source}] {lay.description}\n  objects: {objs}\n  error: {err}\n  failed: {'; '.join(failed)[:300]}"
        )
    return "\n".join(lines)
