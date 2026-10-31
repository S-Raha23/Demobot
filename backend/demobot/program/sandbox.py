"""Running untrusted robot programs (docs/05 "Sandbox").

1. `guard()`: an AST allowlist. Rejections come back to Wonder as tool errors.
2. `execute()`: build the layout's scene, run `run(scene, robot)` with only the API injected,
   check the goal, export the twin. Used inside a worker process.
3. `simulate()`: runs `execute()` in a separate process with CPU, memory and wall limits, and
   caches results by (code, layout, goal, sim version).
"""

import ast
import asyncio
import builtins
import concurrent.futures as cf
import hashlib
import json
import math
import multiprocessing as mp
import resource
import time
import traceback
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from demobot import goal_dsl
from demobot.config import settings
from demobot.program.api import API_ERRORS, FORGE_ATTRS, Obj, SkillApiError, make_api
from demobot.schemas import GoalClause, Layout, SimResult
from demobot.sim import constants as C
from demobot.sim.scene import build_scene

SIM_VERSION = "sim3"  # place_at honours yaw
CPU_LIMIT_S = 20
TEST_CPU_LIMIT_S = 60  # forge tests push/turn with repeated IK moves; 20 s starved them (every push test timed out)
MEMORY_LIMIT_BYTES = 2 * 1024**3  # PyBullet + NumPy need more address space than 1 GB
WALL_TIMEOUT_S = 90
MAX_LOOP_TICKS = 20_000
MAX_CODE_CHARS = 12_000

SAFE_BUILTINS = (
    "range", "len", "min", "max", "abs", "sorted", "enumerate", "zip", "list", "dict", "set",
    "tuple", "float", "int", "str", "round", "sum", "any", "all", "reversed", "bool", "isinstance",
)  # fmt: skip
INJECTED = ("scene", "robot", "math", "log")
CONSTANTS = ("True", "False", "None")
FORBIDDEN_ATTRS = {"format", "format_map", "mro", "f_globals", "f_locals", "gi_frame", "cr_frame"}

_ALLOWED_NODES: tuple[type[ast.AST], ...] = (
    ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.Assign, ast.AugAssign,
    ast.AnnAssign, ast.For, ast.While, ast.If, ast.Break, ast.Continue, ast.Pass, ast.Expr,
    ast.Call, ast.Name, ast.Load, ast.Store, ast.Attribute, ast.Subscript, ast.Slice,
    ast.Constant, ast.List, ast.Tuple, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp,
    ast.GeneratorExp, ast.comprehension, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare,
    ast.IfExp, ast.JoinedStr, ast.FormattedValue, ast.keyword, ast.Lambda, ast.Starred,
    ast.Import, ast.alias, ast.Assert, ast.NamedExpr,
    ast.operator, ast.unaryop, ast.boolop, ast.cmpop, ast.expr_context,
)  # fmt: skip
_NODE_MESSAGES = {
    ast.ClassDef: "classes are not allowed",
    ast.Try: "try/except is not allowed: let skill errors surface so they can be fixed",
    ast.With: "with is not allowed",
    ast.Global: "global is not allowed",
    ast.Nonlocal: "nonlocal is not allowed",
    ast.ImportFrom: "imports are not allowed (math is already available)",
    ast.Raise: "raise is not allowed",
    ast.Delete: "del is not allowed",
    ast.AsyncFunctionDef: "async is not allowed",
    ast.Await: "await is not allowed",
    ast.Yield: "generators are not allowed",
    ast.YieldFrom: "generators are not allowed",
}


class GuardError(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def _defined_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, ast.FunctionDef):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
    return names


def guard(
    code: str, mode: str = "program", skill: str | None = None, extra_names: Iterable[str] = ()
) -> ast.Module:
    """Parse and check code against the allowlist; returns the tree or raises GuardError listing
    every problem with its line number. mode: "program" (def run(scene, robot); forge-tier
    primitives are not allowed), "skill" (a forged skill: def <skill>(robot, scene, ...), forge tier
    allowed) or "tests" (def test_<x>(robot, scene, skill) functions)."""
    if len(code) > MAX_CODE_CHARS:
        raise GuardError([f"the program is longer than {MAX_CODE_CHARS} characters"])
    try:
        tree = ast.parse(code, "<program>")
    except SyntaxError as e:
        raise GuardError([f"line {e.lineno}: syntax error: {e.msg}"]) from None
    problems: list[str] = []

    def bad(node: ast.AST, msg: str) -> None:
        problems.append(f"line {getattr(node, 'lineno', '?')}: {msg}")

    for stmt in tree.body:
        if isinstance(stmt, ast.FunctionDef | ast.Import):
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            continue  # docstring
        if isinstance(stmt, ast.Assign | ast.AnnAssign) and _is_literal(stmt.value):
            continue  # module-level constants
        bad(stmt, "only functions, `import math` and constant assignments may be at module level")
    funcs = [s for s in tree.body if isinstance(s, ast.FunctionDef)]
    if mode == "program":
        run = [f for f in funcs if f.name == "run"]
        if not run:
            problems.append("define `def run(scene, robot):`")
        elif [a.arg for a in run[0].args.args] != ["scene", "robot"]:
            bad(run[0], "run must take exactly (scene, robot)")
    elif mode == "skill":
        fn = [f for f in funcs if f.name == skill]
        if not fn:
            problems.append(f"define `def {skill}(robot, scene, ...):`")
        elif [a.arg for a in fn[0].args.args][:2] != ["robot", "scene"]:
            bad(fn[0], f"{skill} must start with (robot, scene, ...)")
    else:
        tests = [f for f in funcs if f.name.startswith("test_")]
        if not tests:
            problems.append("define at least one `def test_<name>(robot, scene, skill):`")
        for f in tests:
            if [a.arg for a in f.args.args] != ["robot", "scene", "skill"]:
                bad(f, f"{f.name} must take exactly (robot, scene, skill)")
    known = (
        set(SAFE_BUILTINS)
        | set(INJECTED)
        | set(CONSTANTS)
        | _defined_names(tree)
        | set(extra_names)
        | {"Obj"}
    )
    for node in ast.walk(tree):
        if type(node) in _NODE_MESSAGES:
            bad(node, _NODE_MESSAGES[type(node)])
            continue
        if not isinstance(node, _ALLOWED_NODES):
            bad(node, f"{type(node).__name__} is not allowed")
            continue
        if isinstance(node, ast.Import) and [a.name for a in node.names] != ["math"]:
            bad(node, "only `import math` is allowed (it is already available)")
        if isinstance(node, ast.Import) and any(a.asname for a in node.names):
            bad(node, "import aliases are not allowed")
        if isinstance(node, ast.Attribute) and (
            node.attr.startswith("_") or node.attr in FORBIDDEN_ATTRS
        ):
            bad(node, f"attribute `{node.attr}` is not allowed")
        if mode == "program" and isinstance(node, ast.Attribute) and node.attr in FORGE_ATTRS:
            bad(node, f"`{node.attr}` is a forge-tier primitive: only forged skills may use it")
        if isinstance(node, ast.Name):
            if node.id.startswith("_"):
                bad(node, f"names starting with _ are not allowed (`{node.id}`)")
            elif isinstance(node.ctx, ast.Load) and node.id not in known:
                bad(node, f"`{node.id}` is not available (use log() instead of print())"
                    if node.id == "print" else f"`{node.id}` is not available")  # fmt: skip
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "__" in node.value:
            bad(node, "strings containing __ are not allowed")
    if problems:
        raise GuardError(sorted(set(problems), key=lambda s: (len(s.split(":")[0]), s)))
    return tree


def _is_literal(node: ast.AST | None) -> bool:
    if node is None:
        return True
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.List | ast.Tuple | ast.Set):
        return all(_is_literal(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all(
            _is_literal(k) and _is_literal(v) for k, v in zip(node.keys, node.values, strict=True)
        )
    if isinstance(node, ast.UnaryOp):
        return _is_literal(node.operand)
    return False


class _Ticker(ast.NodeTransformer):
    """Insert `_tick()` at the top of every loop body (after the guard, so the name is ours)."""

    def _tick(self) -> ast.Expr:
        return ast.Expr(ast.Call(ast.Name("_tick", ast.Load()), [], []))

    def visit_For(self, node: ast.For) -> ast.AST:
        self.generic_visit(node)
        node.body.insert(0, self._tick())
        return node

    def visit_While(self, node: ast.While) -> ast.AST:
        self.generic_visit(node)
        node.body.insert(0, self._tick())
        return node


class LoopLimit(SkillApiError):
    """A loop ran too many times."""


def _trim_traceback(e: BaseException) -> str:
    frames = [f for f in traceback.extract_tb(e.__traceback__) if f.filename == "<program>"]
    lines = [f"line {f.lineno}, in {f.name}" for f in frames][-10:]
    return "\n".join([*lines, f"{type(e).__name__}: {e}"])[-2000:]


# ---------- execution ----------
def _safe_env(tick: Callable[[], None]) -> dict[str, Any]:
    return {
        "__builtins__": {n: getattr(builtins, n) for n in SAFE_BUILTINS},
        "_tick": tick,
        "math": math,
        "Obj": Obj,
    }


def load_skills(
    forged: dict[str, str], env: dict[str, Any], sim: Any
) -> dict[str, Callable[..., Any]]:
    """Forged skills as functions a program can call: name(robot, scene, ...). While one runs, the
    forge tier is open, the objects passed to it may be touched (and open containers among them
    become movable), and everything else must stay put."""
    out: dict[str, Callable[..., Any]] = {}
    envs: list[dict[str, Any]] = []
    for name, src in forged.items():
        tree = ast.fix_missing_locations(
            _Ticker().visit(guard(src, mode="skill", skill=name, extra_names=forged))
        )
        tree.body = [st for st in tree.body if not isinstance(st, ast.Import)]
        senv = _safe_env(env["_tick"]) | {"log": env["log"]}
        exec(compile(tree, f"<skill {name}>", "exec"), senv)
        envs.append(senv)
        fn = senv[name]

        def wrapper(
            robot: Any, scene: Any, *args: Any, _fn: Callable[..., Any] = fn, **kw: Any
        ) -> Any:
            targets = {a.name for a in (*args, *kw.values()) if isinstance(a, Obj)}
            scene._forge.append(targets)
            sim.set_movable(targets, True)
            try:
                return _fn(robot, scene, *args, **kw)
            finally:
                scene._forge.pop()
                sim.set_movable(targets, False)

        out[name] = wrapper
    for senv in envs:  # forged skills may call each other
        senv.update(out)
    return out


def execute(
    code: str,
    layout: Layout,
    goal: list[GoalClause],
    out_dir: Path | None = None,
    render: bool = False,
    calibration_json: str | None = None,
    forged: dict[str, str] | None = None,
) -> SimResult:
    """Run a program on a layout in this process. Never raises for program errors. `forged`:
    the promoted forged skills (name -> source) the program may call."""
    t0 = time.monotonic()
    forged = forged or {}
    try:
        tree = guard(code, extra_names=forged)
    except GuardError as e:
        return SimResult(ok=False, error=str(e), error_type="GuardError", layout_id=layout.id)
    tree.body = [s for s in tree.body if not isinstance(s, ast.Import)]  # math is injected
    tree = ast.fix_missing_locations(_Ticker().visit(tree))
    sim = build_scene(layout)
    try:
        recorder = sim.record()
        initial = goal_dsl.to_state(sim.state())
        calls: list[Any] = []
        logs: list[str] = []
        ticks = [0]

        def _tick() -> None:
            ticks[0] += 1
            if ticks[0] > MAX_LOOP_TICKS:
                raise LoopLimit(f"loops ran more than {MAX_LOOP_TICKS} times")

        env: dict[str, Any] = {
            "__builtins__": {n: getattr(builtins, n) for n in SAFE_BUILTINS},
            "_tick": _tick,
            **make_api(sim, calls, logs),
        }
        error = error_type = None
        try:
            env |= load_skills(forged, env, sim)
            exec(compile(tree, "<program>", "exec"), env)
            env["run"](env["scene"], env["robot"])
        except (*API_ERRORS, LoopLimit) as e:
            error, error_type = _trim_traceback(e), type(e).__name__
        except RecursionError as e:
            error, error_type = _trim_traceback(e), "RecursionError"
        except Exception as e:
            error, error_type = _trim_traceback(e), type(e).__name__
        if error is None:
            env["robot"].home()
        sim.step(C.SETTLE_STEPS)
        final = sim.state()
        results = goal_dsl.evaluate(goal, goal_dsl.to_state(final), initial, sim=True)
        res = SimResult(
            ok=error is None,
            error=error,
            error_type=error_type,
            layout_id=layout.id,
            skill_calls=calls,
            logs=logs,
            final_state=final,
            goal_results=results,
            goal_ok=error is None and goal_dsl.all_hold(results),
            collisions=[c.error for c in calls if c.error and c.error.startswith("Collision")],
            duration_s=round(sim.time_s, 2),
        )
        if out_dir is not None:
            from demobot.sim import render as render_mod
            from demobot.sim.twin_export import write_twin

            out_dir.mkdir(parents=True, exist_ok=True)
            res.twin_trajectory = str(
                write_twin(sim, recorder, layout, out_dir / f"twin_{layout.id}.json")
            )
            if render:
                res.renders = render_mod.render_all(
                    sim, layout, out_dir, layout.id, calibration_json
                )
        res.wall_s = round(time.monotonic() - t0, 2)
        return res
    finally:
        sim.close()


def execute_test(skill: str, skill_code: str, tests_code: str, test: str, layout: Layout,
                 out_dir: Path | None = None) -> dict[str, Any]:  # fmt: skip
    """Run one forge test on one layout: test(robot, scene, skill) on a fresh scene. Returns
    {passed, skipped, error, error_type, calls} (and a twin + top-down render when out_dir)."""
    try:
        ttree = guard(tests_code, mode="tests", extra_names=[skill])
    except GuardError as e:
        return {"passed": False, "skipped": False, "error": str(e), "error_type": "GuardError"}
    ttree.body = [s for s in ttree.body if not isinstance(s, ast.Import)]
    ttree = ast.fix_missing_locations(_Ticker().visit(ttree))
    sim = build_scene(layout)
    try:
        recorder = sim.record() if out_dir is not None else None
        calls: list[Any] = []
        logs: list[str] = []
        ticks = [0]

        def _tick() -> None:
            ticks[0] += 1
            if ticks[0] > MAX_LOOP_TICKS:
                raise LoopLimit(f"loops ran more than {MAX_LOOP_TICKS} times")

        env = _safe_env(_tick) | make_api(sim, calls, logs)
        out: dict[str, Any] = {"passed": False, "skipped": False, "error": None, "error_type": None}
        try:
            fn = load_skills({skill: skill_code}, env, sim)[skill]
            tenv = _safe_env(_tick) | {"log": env["log"], skill: fn}
            exec(compile(ttree, "<tests>", "exec"), tenv)
            got = tenv[test](env["robot"], env["scene"], fn)
            sim.step(C.SETTLE_STEPS)
            out["skipped"] = got == "skip"
            out["passed"] = got != "skip"
        except AssertionError as e:
            out["error"], out["error_type"] = f"assertion failed: {e}"[:400], "AssertionError"
        except GuardError as e:
            out["error"], out["error_type"] = str(e)[:400], "GuardError"
        except Exception as e:
            out["error"], out["error_type"] = _trim_traceback(e)[:400], type(e).__name__
        out["calls"] = [c.skill for c in calls][:40]
        if out_dir is not None and recorder is not None:
            from demobot.sim import render as render_mod
            from demobot.sim.twin_export import write_twin

            out_dir.mkdir(parents=True, exist_ok=True)
            out["twin"] = str(write_twin(sim, recorder, layout, out_dir / f"twin_{layout.id}.json"))
            out["renders"] = render_mod.render_all(sim, layout, out_dir, layout.id, None)
        return out
    finally:
        sim.close()


async def run_test(skill: str, skill_code: str, tests_code: str, test: str, layout: Layout,
                   out_dir: Path | None = None, workers: int = 4) -> dict[str, Any]:  # fmt: skip
    payload = json.dumps({"kind": "test", "skill": skill, "skill_code": skill_code, "tests_code": tests_code, "test": test,
                          "layout": layout.model_dump(mode="json"), "out_dir": str(out_dir) if out_dir else None,
                          "cpu_limit_s": TEST_CPU_LIMIT_S})  # fmt: skip
    fut = asyncio.get_running_loop().run_in_executor(pool(workers), _worker_run, payload)
    try:
        return dict(json.loads(await asyncio.wait_for(fut, WALL_TIMEOUT_S)))
    except (TimeoutError, cf.process.BrokenProcessPool) as e:
        _reset_pool()
        return {"passed": False, "skipped": False, "error": f"the test {'took too long' if isinstance(e, TimeoutError) else 'used too much CPU or memory'}",
                "error_type": "Timeout"}  # fmt: skip


# ---------- the process pool ----------
def _worker_init() -> None:
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))
    from demobot.sim.skills import _seed_bank

    _seed_bank("working")  # warm the IK bank once per worker
    _seed_bank("full")


def _worker_run(payload: str) -> str:
    """One task: a fresh CPU budget of CPU_LIMIT_S on top of what this worker used so far."""
    used = resource.getrusage(resource.RUSAGE_SELF)
    spent = math.ceil(used.ru_utime + used.ru_stime)
    _, hard = resource.getrlimit(resource.RLIMIT_CPU)
    a = json.loads(payload)
    resource.setrlimit(resource.RLIMIT_CPU, (spent + int(a.get("cpu_limit_s", CPU_LIMIT_S)), hard))
    if a.get("kind") == "test":
        return json.dumps(execute_test(a["skill"], a["skill_code"], a["tests_code"], a["test"],
                                       Layout.model_validate(a["layout"]), Path(a["out_dir"]) if a["out_dir"] else None))  # fmt: skip
    res = execute(
        a["code"],
        Layout.model_validate(a["layout"]),
        [GoalClause.model_validate(g) for g in a["goal"]],
        Path(a["out_dir"]) if a["out_dir"] else None,
        a["render"],
        a["calibration_json"],
        a.get("forged") or {},
    )
    return res.model_dump_json()


_pool: cf.ProcessPoolExecutor | None = None
_pool_size = 0


def pool(workers: int = 2) -> cf.ProcessPoolExecutor:
    global _pool, _pool_size
    if _pool is None or _pool_size < workers:
        if _pool is not None:
            _pool.shutdown(wait=False, cancel_futures=True)
        _pool = cf.ProcessPoolExecutor(
            max_workers=workers, mp_context=mp.get_context("spawn"), initializer=_worker_init
        )
        _pool_size = workers
    return _pool


def _reset_pool() -> None:
    global _pool
    if _pool is not None:
        for proc in list(getattr(_pool, "_processes", {}).values()):
            proc.kill()
        _pool.shutdown(wait=False, cancel_futures=True)
    _pool = None


def sim_key(
    code: str,
    layout: Layout,
    goal: list[GoalClause],
    render: bool,
    forged: dict[str, str] | None = None,
) -> str:
    blob = json.dumps(
        {
            "code": code,
            "layout": layout.model_dump(mode="json"),
            "goal": [g.model_dump(mode="json") for g in goal],
            "render": render,
            "v": SIM_VERSION,
            **({"forged": forged} if forged else {}),
        },
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


async def simulate(
    code: str,
    layout: Layout,
    goal: list[GoalClause],
    *,
    render: bool = False,
    calibration_json: str | None = None,
    workers: int = 2,
    use_cache: bool = True,
    cpu_limit_s: int = CPU_LIMIT_S,
    forged: dict[str, str] | None = None,
) -> SimResult:
    """Run a program in a worker process; cached by (code, layout, goal, render, sim version,
    forged skills). Every promoted forged skill is available unless `forged` says otherwise.
    Artifacts (twin, renders) live in data/cache/sim/<key>/."""
    if forged is None:
        from demobot.program.forge import load_forged

        forged = load_forged()
    key = sim_key(code, layout, goal, render, forged)
    out_dir = settings.data_path / "cache" / "sim" / key
    cached = out_dir / "result.json"
    if use_cache and cached.exists():
        return SimResult.model_validate_json(cached.read_text())
    payload = json.dumps(
        {
            "code": code,
            "layout": layout.model_dump(mode="json"),
            "goal": [g.model_dump(mode="json") for g in goal],
            "out_dir": str(out_dir),
            "render": render,
            "calibration_json": calibration_json,
            "cpu_limit_s": cpu_limit_s,
            "forged": forged,
        }
    )
    loop = asyncio.get_running_loop()
    fut = loop.run_in_executor(pool(workers), _worker_run, payload)
    try:
        raw = await asyncio.wait_for(fut, WALL_TIMEOUT_S)
    except (TimeoutError, cf.process.BrokenProcessPool) as e:
        _reset_pool()
        why = "took too long" if isinstance(e, TimeoutError) else "used too much CPU or memory"
        return SimResult(ok=False, error=f"the program {why} and was stopped", error_type="Timeout",
                         layout_id=layout.id)  # fmt: skip
    res = SimResult.model_validate_json(raw)
    out_dir.mkdir(parents=True, exist_ok=True)
    cached.write_text(raw)
    return res
