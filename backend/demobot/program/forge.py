"""Skill Forge (docs/11 F1): when no combination of the robot's primitives can do a task (the box
is wider than the gripper, the goal needs a turn in place), Muse Wonder invents a new skill from
low-level forge-tier primitives, writes tests for it, runs them on randomised layouts, and promotes
it into the toolkit only if it passes 9/10 fresh layouts and no existing skill gets worse.

Promoted skills live in backend/demobot/skills/forged/<name>.py (+ <name>_tests.py and index.json);
every program may call them from then on, and the skill API document lists them.
"""

import ast
import asyncio
import json
import random
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from demobot import gateway, providers
from demobot.config import ROOT, settings
from demobot.events import RunContext
from demobot.llm import jpeg_data_url
from demobot.schemas import GoalClause, Layout
from demobot.sim.layouts import random_layout, repair, validate

FORGED_DIR = ROOT / "backend" / "demobot" / "skills" / "forged"
MAX_TURNS = 10
N_LAYOUTS = 10
PROMOTE_PASSES = 9  # of N_LAYOUTS fresh layouts
TURN_ESTIMATE = 0.3
BASE_API_VERSION = 1


# ---------- the toolkit on disk ----------
def index() -> list[dict[str, Any]]:
    p = FORGED_DIR / "index.json"
    return list(json.loads(p.read_text())) if p.exists() else []


def load_forged() -> dict[str, str]:
    """name -> source of every promoted skill."""
    out = {}
    for e in index():
        f = FORGED_DIR / f"{e['name']}.py"
        if f.exists():
            out[e["name"]] = f.read_text()
    return out


def skill_api_version() -> str:
    return f"{BASE_API_VERSION}.{len(index())}"


def _doc(code: str, name: str) -> tuple[str, str]:
    """(signature, first docstring line) of `name` in `code`."""
    for node in ast.parse(code).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            args = ", ".join(a.arg for a in node.args.args)
            return f"{name}({args})", (ast.get_docstring(node) or "").strip()
    return f"{name}(robot, scene, ...)", ""


def reference() -> str:
    """The forged skills, for the coder prompt and skill_api.md."""
    lines = []
    for e in index():
        f = FORGED_DIR / f"{e['name']}.py"
        if not f.exists():
            continue
        sig, doc = _doc(f.read_text(), e["name"])
        lines.append(
            f"def {sig}  # invented by DemoBot {e['promoted_at'][:10]}, {e['pass_rate'] * 100:.0f}% on fresh layouts\n    # {doc}"
        )
    return "\n".join(lines)


# ---------- requests and outcomes ----------
@dataclass
class ForgeRequest:
    name: str
    signature: str
    purpose: str
    evidence: str
    target: str = ""  # the object the skill is mainly about, if any


@dataclass
class ForgeOutcome:
    request: ForgeRequest
    promoted: bool = False
    code: str = ""
    tests: str = ""
    pass_rate: float = 0.0
    regression: dict[str, Any] = field(default_factory=dict)
    explanation: str = ""
    turns: int = 0
    versions: list[dict[str, Any]] = field(default_factory=list)
    grid: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""


# ---------- tests ----------
def test_names(tests_code: str) -> list[str]:
    try:
        tree = ast.parse(tests_code)
    except SyntaxError:
        return []
    return [
        n.name for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
    ]


def sparse(base: Layout, target: str, keep_others: int = 2) -> Layout:
    """The forge's test table: the skill's object plus a couple of small others (randomised per
    seed), so a test has room to do something; a crowded table would make most tests skip."""
    if not target or target not in {o.name for o in base.objects}:
        return base
    others = sorted((o for o in base.objects if o.name != target), key=lambda o: o.w * o.d)[
        :keep_others
    ]
    return base.model_copy(
        update={"objects": [o for o in base.objects if o.name == target] + others}
    )


def test_layouts(base: Layout, seeds: list[int]) -> list[Layout]:
    out = []
    for s in seeds:
        lay = repair(random_layout(base, s))[0]
        if not validate(lay):
            out.append(
                lay.model_copy(
                    update={
                        "id": f"forge-{s}",
                        "source": "forge",
                        "description": f"random layout, seed {s}",
                    }
                )
            )
    return out


async def run_tests(
    name: str, code: str, tests: str, layouts: list[Layout], art: Path | None, keep: int = 3
) -> dict[str, Any]:
    """Every test on every layout (each on a fresh scene, in parallel). A layout passes if no test
    fails and at least one ran (tests may return "skip" when a layout does not apply)."""
    from demobot.program import sandbox

    names = test_names(tests)
    if not names:
        return {"error": "write_tests first: no test_<name>(robot, scene, skill) functions"}
    jobs = []
    for i, lay in enumerate(layouts):
        for j, t in enumerate(names):
            out = (
                art / "forge" / name / f"{lay.id}"
                if art is not None and i < keep and j == 0
                else None
            )
            jobs.append((lay, t, sandbox.run_test(name, code, tests, t, lay, out)))
    results = await asyncio.gather(*(j[2] for j in jobs))
    per: dict[str, list[dict[str, Any]]] = {}
    for (lay, t, _), r in zip(jobs, results, strict=True):
        per.setdefault(lay.id, []).append(r | {"test": t})
    grid, failures = [], []
    for lay in layouts:
        rs = per.get(lay.id, [])
        ran = [r for r in rs if not r.get("skipped")]
        ok = bool(ran) and all(r.get("passed") for r in ran)
        cell: dict[str, Any] = {"layout": lay.id, "passed": ok, "skipped": not ran}
        for r in rs:
            if r.get("twin") and art is not None:
                cell["twin"] = str(Path(r["twin"]).relative_to(art.parent))
                top = (r.get("renders") or {}).get("top")
                cell["top"] = str(Path(top).relative_to(art.parent)) if top else None
        grid.append(cell)
        failures += [
            {"layout": lay.id, "test": r["test"], "error": r.get("error")}
            for r in ran
            if not r.get("passed")
        ]
    passed = sum(c["passed"] for c in grid)
    skips = {
        t: sum(1 for rs in per.values() for r in rs if r["test"] == t and r.get("skipped"))
        for t in names
    }
    return {"pass_rate": round(passed / max(1, len(grid)), 3), "passed": passed, "total": len(grid),
            "layouts_where_every_test_skipped": sum(c["skipped"] for c in grid), "skips_per_test": skips,
            "failures": failures[:8], "grid": grid}  # fmt: skip


async def regression_gate(name: str, code: str, n_random: int = 3) -> dict[str, Any]:
    """Every library skill's program, on its demo layout plus n random layouts, with and without
    the new skill available: none may get worse."""
    from demobot.api import list_runs, run_dir
    from demobot.program import sandbox
    from demobot.versions import get, program, spec

    current = load_forged()
    with_new = current | {name: code}
    checked, worse = 0, []
    for r in list_runs():
        if not r.get("card"):
            continue
        d = run_dir(r["run_id"])
        try:
            v = get(d)
            prog, goal = program(d, v), spec(d, v).goal
            scene = json.loads((d / "artifacts" / "twin_scene.json").read_text())
        except Exception:
            continue
        if prog is None:
            continue
        base = repair(Layout.model_validate(scene["layout"]))[0]
        for lay in [base, *test_layouts(base, [1000 + k for k in range(n_random)])]:
            a = await sandbox.simulate(prog.code, lay, goal, forged=current)
            b = await sandbox.simulate(prog.code, lay, goal, forged=with_new)
            checked += 1
            if a.goal_ok and not b.goal_ok:
                worse.append(f"{r['run_id']}:{lay.id}")
    return {"checked": checked, "worse": worse, "ok": not worse}


def promote_files(out: ForgeOutcome, run_id: str, art: Path | None = None) -> None:
    """The skill, its tests, its test grid and up to 3 twin recordings of its tests, all in the repo
    (so the deployed site shows them without the run that forged it)."""
    import shutil

    FORGED_DIR.mkdir(parents=True, exist_ok=True)
    (FORGED_DIR / f"{out.request.name}.py").write_text(out.code)
    (FORGED_DIR / f"{out.request.name}_tests.py").write_text(out.tests)
    twins = FORGED_DIR / f"{out.request.name}_twins"
    twins.mkdir(exist_ok=True)
    grid = []
    for k, c in enumerate(out.grid):
        cell = {"layout": c["layout"], "passed": c["passed"], "skipped": c.get("skipped", False)}
        if c.get("twin") and art is not None and (art.parent / c["twin"]).exists():
            shutil.copy(art.parent / c["twin"], twins / f"{k}.json")
            cell["twin"] = k
        grid.append(cell)
    idx = [e for e in index() if e["name"] != out.request.name]
    idx.append({"name": out.request.name, "signature": out.request.signature, "purpose": out.request.purpose,
                "evidence": out.request.evidence, "pass_rate": out.pass_rate, "regression": out.regression,
                "promoted_at": datetime.now(UTC).isoformat(timespec="seconds"), "run_id": run_id,
                "explanation": out.explanation, "grid": grid})  # fmt: skip
    (FORGED_DIR / "index.json").write_text(json.dumps(idx, indent=1))
    if not (FORGED_DIR / "__init__.py").exists():
        (FORGED_DIR / "__init__.py").write_text(
            '"""Skills DemoBot invented (Skill Forge, docs/11 F1)."""\n'
        )


# ---------- the Wonder loop ----------
FORGE_API = """Forge-tier primitives (only inside your skill; normal programs cannot use them):
robot.ee_pose() -> (x, y, z, yaw)             # gripper in table cm (z above the table) and degrees
robot.move_ee(x, y, z, yaw=None, speed=1.0)   # straight-line move with IK; slower speed = gentler; raises NotReachable,
                                              # or Collision if anything except the objects passed to your skill moves > 1 cm
robot.grip("open" | "close", width_cm=None)   # "close" grasps an object between the fingers, else just closes them
robot.wait(seconds)                           # let physics settle (max 3 s)
scene.pose(obj) -> (x, y, z, yaw)             # an object's pose now
scene.in_contact(a, b_or_"robot") -> bool
scene.gripper_width_max() -> float            # about 8 cm
Plus the normal API (scene.get, scene.objects, scene.free_spot, robot.pick, robot.place_at, ...), `math` and `log`.
Table frame: +x right, +y towards the robot, cm. Objects passed to your skill may be touched and moved (an open
container becomes a free body while your skill runs); everything else must stay put."""

PHYSICS_NOTES = """Physics notes (PyBullet, Franka Panda):
- Push: keep the gripper OPEN and turn it so the two fingers lie across the push direction (yaw 0 for a push along x;
  in general yaw = the push direction's angle in degrees): two contacts 8 cm apart keep the object from turning. Approach
  from behind the object (the side opposite the push direction), a few cm clear of it, at z = 0.5 x its height; move in a
  straight line at low speed (0.3) through its centre; finish with a small retreat, then lift. The approach path must not
  cross other objects. Allow +-2 cm and +-10 degrees in tests.
- Rotate in place: open, move above the centre, lower to grasp height, grip("close"), lift 1 cm, move_ee with the new yaw, lower,
  grip("open"), lift. The object turns with the gripper.
- Stack: place_at with z = the top of the base object, then wait(1) and check it is still upright and on top."""

TOOLS: list[dict[str, Any]] = [
    {"type": "function", "name": "write_skill",
     "description": "Define the skill: Python source with `def <name>(robot, scene, ...)` (and helpers). Returns guard problems, if any.",
     "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"], "additionalProperties": False}},
    {"type": "function", "name": "write_tests",
     "description": "Define >= 3 tests: `def test_<name>(robot, scene, skill):` each picks an object and a feasible target on the "
                    "layout it is given (use scene.free_spot / scene.bounds), calls skill(robot, scene, ...), and asserts the outcome "
                    "with `assert` (pose within tolerance via scene.pose, no other object displaced > 1 cm, object upright). "
                    "Return \"skip\" when the layout does not allow the test.",
     "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"], "additionalProperties": False}},
    {"type": "function", "name": "run_tests",
     "description": "Run every test on n randomised layouts in parallel. Returns the pass rate, the failures with errors, and top-down "
                    "images of the first failing layouts.",
     "parameters": {"type": "object", "properties": {"n_layouts": {"type": "integer"}}, "required": ["n_layouts"], "additionalProperties": False}},
    {"type": "function", "name": "inspect_physics",
     "description": "Mass, friction, size and pose of an object as the simulator models it.",
     "parameters": {"type": "object", "properties": {"object": {"type": "string"}}, "required": ["object"], "additionalProperties": False}},
    {"type": "function", "name": "promote",
     "description": f"Promote the skill into the toolkit. Accepted only if it passes >= {PROMOTE_PASSES}/{N_LAYOUTS} fresh layouts "
                    "(new seeds) and no existing library skill gets worse with it available.",
     "parameters": {"type": "object", "properties": {"explanation": {"type": "string"}}, "required": ["explanation"], "additionalProperties": False}},
]  # fmt: skip


class ForgeLoop:
    def __init__(
        self, ctx: RunContext, req: ForgeRequest, base: Layout, art: Path | None, run_id: str
    ) -> None:
        self.ctx = ctx.at("forge")
        self.req = req
        self.base = base
        self.art = art
        self.run_id = run_id
        self.out = ForgeOutcome(request=req)
        self.seed = 7000 + random.Random(req.name).randint(0, 999)

    def _emit(self, tool: str, args: dict[str, Any], result: dict[str, Any]) -> None:
        self.ctx.emit(
            "tool_call",
            payload={
                "agent": "forge",
                "iteration": self.out.turns,
                "tool": tool,
                "args": args,
                "result": result,
            },
        )

    def write_skill(self, code: str) -> dict[str, Any]:
        from demobot.program.sandbox import GuardError, guard

        try:
            guard(code, mode="skill", skill=self.req.name, extra_names=load_forged())
        except GuardError as e:
            self._emit("write_skill", {}, {"ok": False})
            return {"error": str(e)[:1500]}
        self.out.code = code
        self.out.versions.append(
            {
                "kind": "skill",
                "version": sum(v["kind"] == "skill" for v in self.out.versions) + 1,
                "code": code,
            }
        )
        self._emit("write_skill", {"version": self.out.versions[-1]["version"]}, {"ok": True})
        self.ctx.emit("artifact", payload={"name": f"{self.req.name}.py", "path": "", "kind": "code", "label": f"Forged skill {self.req.name}",
                                           "code": code[:6000]})  # fmt: skip
        return {"ok": True}

    def write_tests(self, code: str) -> dict[str, Any]:
        from demobot.program.sandbox import GuardError, guard

        try:
            guard(code, mode="tests", extra_names=[self.req.name])
        except GuardError as e:
            return {"error": str(e)[:1500]}
        names = test_names(code)
        if len(names) < 3:
            return {"error": f"write at least 3 tests (got {len(names)})"}
        self.out.tests = code
        self._emit("write_tests", {"tests": names}, {"ok": True})
        return {"ok": True, "tests": names}

    async def run_tests(self, n: int, fresh: bool = False) -> tuple[dict[str, Any], list[str]]:
        if not self.out.code:
            return {"error": "write_skill first"}, []
        n = max(3, min(N_LAYOUTS, n))
        self.seed += 100
        pool = test_layouts(
            sparse(self.base, self.req.target), [self.seed + k for k in range(n * 4)]
        )[: n * 2]
        res = await run_tests(self.req.name, self.out.code, self.out.tests, pool, self.art)
        if "error" in res:
            return res, []
        # score n layouts where a test actually ran (one where every test skipped is replaced, not counted);
        # too few such layouts count as failures
        ran = [c for c in res["grid"] if not c["skipped"]][:n]
        passed = sum(c["passed"] for c in ran)
        res = res | {
            "grid": ran,
            "passed": passed,
            "total": n,
            "pass_rate": round(passed / n, 3),
            "layouts_tried": len(pool),
        }
        if len(ran) < n:
            res["note"] = (
                f"only {len(ran)} of {len(pool)} layouts ran any test; the other {n - len(ran)} needed layouts count as "
                "FAILURES. Your tests skip too often: choose the push direction and distance from what the layout allows "
                "(try +-x, +-y, shorter distances) and skip only when nothing is feasible."
            )
        self.out.pass_rate = res["pass_rate"]
        self.out.grid = res["grid"]
        self._emit("run_tests", {"n_layouts": n, "fresh": fresh}, {"ok": res["passed"] >= PROMOTE_PASSES * n / N_LAYOUTS,
                                                                    "passed": res["passed"], "total": res["total"]})  # fmt: skip
        self.ctx.emit(
            "metric",
            payload={
                "name": "forge_pass_rate",
                "value": res["pass_rate"],
                "passed": res["passed"],
                "total": res["total"],
            },
        )
        imgs = [c["top"] for c in res["grid"] if not c["passed"] and c.get("top")][:2]
        return {k: v for k, v in res.items() if k != "grid"}, imgs

    def inspect_physics(self, name: str) -> dict[str, Any]:
        from demobot.sim import constants as C
        from demobot.sim.scene import OPEN_CONTAINER_KG, mass_kg

        o = next((o for o in self.base.objects if o.name == name), None)
        if o is None:
            return {"error": f"no object {name!r}; objects: {[x.name for x in self.base.objects]}"}
        self._emit("inspect_physics", {"object": name}, {"ok": True})
        return {"name": o.name, "shape": o.shape, "size_cm": [o.w, o.d, o.h], "yaw": o.yaw, "open_container": o.is_open,
                "mass_kg": OPEN_CONTAINER_KG if o.is_open else round(mass_kg(o), 3), "lateral_friction": C.LATERAL_FRICTION,
                "gripper_width_max_cm": 2 * C.FINGER_OPEN * 100}  # fmt: skip

    async def promote(self, explanation: str) -> dict[str, Any]:
        if not self.out.code or not self.out.tests:
            return {"accepted": False, "error": "write_skill and write_tests first"}
        res, _ = await self.run_tests(N_LAYOUTS, fresh=True)
        if "error" in res:
            return {"accepted": False, **res}
        if res["passed"] < PROMOTE_PASSES:
            self._emit("promote", {}, {"ok": False, "passed": res["passed"]})
            return {"accepted": False, "error": f"only {res['passed']}/{res['total']} fresh layouts passed (need {PROMOTE_PASSES})",
                    "failures": res["failures"]}  # fmt: skip
        gate = await regression_gate(self.req.name, self.out.code)
        self.out.regression = gate
        self.ctx.emit(
            "metric",
            payload={
                "name": "forge_regression",
                "value": gate["ok"],
                "checked": gate["checked"],
                "worse": gate["worse"],
            },
        )
        if not gate["ok"]:
            self._emit("promote", {}, {"ok": False, "regression": gate["worse"][:5]})
            return {
                "accepted": False,
                "error": f"regression: {len(gate['worse'])} library runs got worse",
                "worse": gate["worse"][:8],
            }
        self.out.promoted, self.out.explanation = True, explanation
        promote_files(self.out, self.run_id, self.art)
        self._emit("promote", {}, {"ok": True, "passed": res["passed"], "total": res["total"]})
        self.ctx.emit("skill_forged", payload={"name": self.req.name, "signature": self.req.signature, "pass_rate": self.out.pass_rate,
                                               "regression": gate, "skill_api_version": skill_api_version(), "explanation": explanation})  # fmt: skip
        return {"accepted": True, "skill_api_version": skill_api_version()}

    async def run_tool(self, name: str, args: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        try:
            if name == "write_skill":
                return self.write_skill(str(args.get("code", ""))), []
            if name == "write_tests":
                return self.write_tests(str(args.get("code", ""))), []
            if name == "run_tests":
                return await self.run_tests(int(args.get("n_layouts", N_LAYOUTS)))
            if name == "inspect_physics":
                return self.inspect_physics(str(args.get("object", ""))), []
            if name == "promote":
                return await self.promote(str(args.get("explanation", ""))), []
        except (ValueError, TypeError) as e:
            return {"error": f"bad arguments: {e}"}, []
        return {"error": f"no tool {name!r}"}, []

    def first_message(self) -> str:
        from demobot.program.synth import api_reference

        objs = "\n".join(f"- {o.name}: {o.kind}, {o.shape} {o.w:.1f}x{o.d:.1f}x{o.h:.1f} cm at ({o.x:.1f}, {o.y:.1f}), yaw {o.yaw:.0f}"
                         + (", open container" if o.is_open else "") for o in self.base.objects)  # fmt: skip
        return (f"## The capability gap\nName: {self.req.name}\nTarget object: {self.req.target or '(any)'}\nSignature: {self.req.signature}\nPurpose: {self.req.purpose}\n"
                f"Evidence: {self.req.evidence}\n\n## The table (example layout; tests run on randomised ones)\n{objs}\n\n"
                f"## Normal skill API\n{api_reference()}\n\n## {FORGE_API}\n\n{PHYSICS_NOTES}\n\n"
                "Tests run on randomised layouts of the target plus a couple of small objects; a layout counts as passed only "
                "if at least one test ran there and none failed, so keep feasibility checks reasonable (return \"skip\" only "
                "when the test truly cannot run).\n"
                f"Write the skill, write >= 3 tests, run them, fix what fails, and promote when it passes "
                f">= {PROMOTE_PASSES}/{N_LAYOUTS}. You have {MAX_TURNS} turns.")  # fmt: skip

    async def run(self) -> ForgeOutcome:
        system = ("You are Muse Wonder inside DemoBot's Skill Forge. The robot lacks a skill it needs; you invent it from "
                  "low-level primitives, test it on randomised simulated layouts, and promote it only when it is reliable. "
                  "Be precise and physical. Use the tools; keep code short and readable.")  # fmt: skip
        items: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": self.first_message()},
        ]
        self.ctx.emit("stage_start", payload={"skill": self.req.name})
        self.ctx.emit("artifact", payload={"name": "capability_gap", "path": "", "kind": "json", "label": "Capability gap",
                                           "skill": self.req.name, "signature": self.req.signature, "purpose": self.req.purpose,
                                           "evidence": self.req.evidence})  # fmt: skip
        t0 = time.monotonic()
        for turn in range(1, MAX_TURNS + 1):
            self.out.turns = turn
            req = {"stage": "forge", "skill": self.req.name, "conversation": hash_items(items)}
            call = providers.responses_call(settings.model_wonder, input=items, tools=TOOLS, reasoning={"effort": "high"},
                                            max_output_tokens=16000)  # fmt: skip
            raw = await gateway.cached_call(ctx=self.ctx, purpose=f"forge:turn{turn}", provider="meta", model=settings.model_wonder,
                                            request=req, estimate_usd=TURN_ESTIMATE, call=call, validate=gateway.passthrough)  # fmt: skip
            calls = []
            for o in raw.get("output") or []:
                if o.get("type") == "function_call":
                    calls.append(o)
                    items.append(
                        {
                            "type": "function_call",
                            "call_id": o["call_id"],
                            "name": o["name"],
                            "arguments": o["arguments"],
                        }
                    )
                elif o.get("type") == "message":
                    text = "".join(
                        c.get("text", "")
                        for c in o.get("content") or []
                        if c.get("type") == "output_text"
                    )
                    if text.strip():
                        items.append({"role": "assistant", "content": text})
                        self.ctx.emit("log", payload={"message": text[:300], "agent": "forge"})
            if not calls:
                items.append(
                    {
                        "role": "user",
                        "content": "Use the tools: write_skill, write_tests, run_tests, then promote.",
                    }
                )
                continue
            images: list[str] = []
            for c in calls:
                try:
                    args = json.loads(c.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                result, imgs = await self.run_tool(c["name"], args)
                images += imgs
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": c["call_id"],
                        "output": json.dumps(result)[:12000],
                    }
                )
            if self.out.promoted:
                break
            if images and self.art is not None:
                content: list[dict[str, Any]] = [
                    {
                        "type": "input_text",
                        "text": "Top-down images of failing test layouts (final state).",
                    }
                ]
                content += [
                    {"type": "input_image", "image_url": jpeg_data_url(self.art.parent / i)}
                    for i in images
                ]
                items.append({"role": "user", "content": content})
            if turn == MAX_TURNS - 1 and not self.out.promoted:
                items.append(
                    {
                        "role": "user",
                        "content": "Last turn: promote now if the tests pass, otherwise explain what is missing.",
                    }
                )
        if not self.out.promoted:
            self.out.reason = f"not promoted after {self.out.turns} turns (best pass rate {self.out.pass_rate:.0%})"
        self.ctx.emit("stage_end", payload={"ok": self.out.promoted, "summary": f"{self.req.name}: " + (
            f"promoted, {self.out.pass_rate:.0%} on fresh layouts" if self.out.promoted else self.out.reason),
            "duration_s": round(time.monotonic() - t0, 1)})  # fmt: skip
        return self.out


def hash_items(items: list[Any]) -> str:
    from demobot.program.synth import _hash_items

    return _hash_items(items)


async def forge(
    ctx: RunContext, req: ForgeRequest, base: Layout, art: Path | None = None, run_id: str = ""
) -> ForgeOutcome:
    """Invent, test and (maybe) promote one skill; at most MAX_TURNS Wonder turns."""
    out = await ForgeLoop(ctx, req, base, art, run_id or ctx.run_id or "").run()
    if art is not None:
        rec = {"request": req.__dict__, "promoted": out.promoted, "code": out.code, "tests": out.tests, "pass_rate": out.pass_rate,
               "regression": out.regression, "explanation": out.explanation, "turns": out.turns, "versions": out.versions,
               "grid": out.grid, "reason": out.reason, "skill_api_version": skill_api_version()}  # fmt: skip
        (art / f"forge_{req.name}.json").write_text(json.dumps(rec, indent=1))
        ctx.emit("artifact", payload={"name": f"forge_{req.name}.json", "path": f"artifacts/forge_{req.name}.json", "kind": "json",
                                      "label": f"Skill Forge: {req.name}"})  # fmt: skip
    return out


_ = (GoalClause,)
