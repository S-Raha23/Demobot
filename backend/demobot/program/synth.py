"""Stage 8: Program. Muse Wonder writes and debugs the robot program with tools, the simulator in
the loop (docs/05 §A). The same loop hardens a program against red-team layouts and applies
spoken corrections (mode "harden" / "correct").

The loop is stateless: every turn sends the whole conversation, so each turn has a deterministic
cache key and a restarted run replays at $0 (Meta's prompt caching keeps the shared prefix cheap).
"""

import asyncio
import difflib
import hashlib
import inspect
import json
import math
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from demobot import gateway, providers
from demobot.config import settings
from demobot.errors import DemoBotError
from demobot.events import RunContext
from demobot.llm import jpeg_data_url, parse_json, prompt
from demobot.program import api as skill_api
from demobot.program import sandbox
from demobot.schemas import (
    GoalClause,
    GroundedDemo,
    Layout,
    Program,
    SimResult,
    TaskSpec,
    Transcript,
)
from demobot.sim import constants as C

MAX_TURNS = 8
WONDER_MAX_OUT = 16000
TURN_ESTIMATE = 0.25
DRAFTS = 2

TOOLS: list[dict[str, Any]] = [
    {"type": "function", "name": "simulate",
     "description": "Run a program in the PyBullet simulator on a layout. Returns ok, the error (trimmed traceback), "
                    "the robot calls, the goal clause table and the final object positions.",
     "parameters": {"type": "object", "properties": {
         "code": {"type": "string", "description": "the full program, defining run(scene, robot)"},
         "layout": {"type": "string", "description": "\"demo\" or a stress layout id from list_layouts"},
         "render": {"type": "boolean", "description": "also return a top-down image of the final state"}},
         "required": ["code", "layout", "render"], "additionalProperties": False}},
    {"type": "function", "name": "inspect_demo",
     "description": "See the human's demo at time t (seconds): a keyframe image and the measured object positions.",
     "parameters": {"type": "object", "properties": {"t": {"type": "number"}}, "required": ["t"],
                    "additionalProperties": False}},
    {"type": "function", "name": "check_reach",
     "description": "Whether the robot can reach a table point (cm), with the margin to the edge of its reach.",
     "parameters": {"type": "object", "properties": {"x_cm": {"type": "number"}, "y_cm": {"type": "number"}},
                    "required": ["x_cm", "y_cm"], "additionalProperties": False}},
    {"type": "function", "name": "list_layouts",
     "description": "The ids and one-line descriptions of the layouts you can simulate on.",
     "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "function", "name": "submit",
     "description": "Submit the final program. Accepted only if your last simulate on \"demo\" with exactly this code passed every clause.",
     "parameters": {"type": "object", "properties": {"code": {"type": "string"}, "explanation": {"type": "string"}},
                    "required": ["code", "explanation"], "additionalProperties": False}},
]  # fmt: skip


def api_reference() -> str:
    """The skill API, generated from program/api.py (signatures and docstrings)."""
    lines = []
    for cls in (skill_api.Obj, skill_api.Scene, skill_api.Robot):
        lines.append(f"class {cls.__name__}:")
        doc = inspect.getdoc(cls) or ""
        lines += [f"    # {d}" for d in doc.splitlines() if d.strip()]
        for name, fn in inspect.getmembers(cls, inspect.isfunction):
            if name.startswith("_"):
                continue
            sig = str(inspect.signature(fn)).replace("self, ", "").replace("(self)", "()")
            sig = sig.replace("demobot.program.api.", "")
            lines.append(f"    def {name}{sig}")
            for d in (inspect.getdoc(fn) or "").splitlines():
                lines.append(f"        # {d}")
    lines.append("def log(msg: str) -> None  # a line in the run log, shown in the UI")
    lines.append(
        "# Errors: "
        + ", ".join(e.__name__ for e in skill_api.API_ERRORS)
        + " (each with a clear message)"
    )
    return "```python\n" + "\n".join(lines) + "\n```"


def system_prompt() -> tuple[str, str]:
    text, sha = prompt("coder")
    examples, sha2 = prompt("coder_examples")
    return text.replace("{api}", api_reference()).replace("{examples}", examples), sha + sha2


# ---------- the context of one synthesis ----------
@dataclass
class SynthInput:
    spec: TaskSpec
    grounded: GroundedDemo
    layouts: dict[str, Layout]  # "demo" first
    transcript: Transcript
    keyframes: list[tuple[float, Path]]  # (t, image)
    calibration_json: str | None
    art: Path  # the run's artifacts dir (programs/, sim/ are written here)
    mode: str = "synth"  # synth | harden | correct
    start_code: str | None = None
    extra: str = ""  # harden: failing layouts; correct: the correction
    first_version: int = 1
    drafts: bool = True


@dataclass
class SynthOutcome:
    program: Program | None
    versions: list[Program] = field(default_factory=list)
    results: dict[str, dict[str, Any]] = field(default_factory=dict)  # "v<N>:<layout>" -> summary
    submitted: bool = False
    turns: int = 0
    drafts: list[dict[str, Any]] = field(default_factory=list)
    winner: str = "wonder"
    trace: list[dict[str, Any]] = field(default_factory=list)


def _clause_text(c: GoalClause) -> str:
    sel = c.select.name or c.select.kind or c.select.role or ", ".join(c.select.names or [])
    tgt = (
        (c.target.name or c.target.kind or c.target.role)
        if c.target
        else (str(c.point_cm) if c.point_cm else "")
    )
    return f"{c.quant} {sel} {c.pred.replace('_', ' ')} {tgt}".strip()


def summarize(res: SimResult) -> dict[str, Any]:
    """What the model sees from one simulation."""
    passed = sum(r.holds for r in res.goal_results)
    return {
        "ok": res.ok,
        "goal_passed": res.goal_ok,
        "clauses_passed": f"{passed}/{len(res.goal_results)}",
        "error": res.error,
        "clauses": [{"clause": _clause_text(r.clause), "holds": r.holds, "detail": r.detail} for r in res.goal_results],
        "robot_calls": [f"{c.skill}({', '.join(f'{k}={v}' for k, v in c.args.items())})" + ("" if c.ok else f" FAILED: {c.error}")
                        for c in res.skill_calls][:25],
        "final_positions": [{"name": o.name, "x": o.x, "y": o.y, "z": o.z} for o in res.final_state],
        "logs": res.logs[:10],
    }  # fmt: skip


def _hash_items(items: list[Any]) -> str:
    """Cache-key digest of a conversation, with image data replaced by its hash."""

    def strip(v: Any) -> Any:
        if isinstance(v, dict):
            return {k: (hashlib.sha256(x.encode()).hexdigest()[:16] if k == "image_url" and isinstance(x, str) else strip(x))
                    for k, x in v.items()}  # fmt: skip
        if isinstance(v, list):
            return [strip(x) for x in v]
        return v

    return hashlib.sha256(json.dumps(strip(items), sort_keys=True).encode()).hexdigest()


def _demo_table(si: SynthInput) -> str:
    rows = [
        "| object | kind | role | start (x, y) cm | end (x, y) cm | size w×d×h cm |",
        "|---|---|---|---|---|---|",
    ]
    end = {o.name: o for o in si.grounded.final}
    for o in si.grounded.initial:
        e = end.get(o.name, o)
        rows.append(f"| {o.name} | {o.kind} | {o.role} | ({o.x:.1f}, {o.y:.1f}) | ({e.x:.1f}, {e.y:.1f}) | "
                    f"{o.w:.1f}×{o.d:.1f}×{o.h:.1f} |")  # fmt: skip
    return "\n".join(rows)


class Loop:
    def __init__(self, ctx: RunContext, si: SynthInput) -> None:
        self.ctx = ctx.at("program")
        self.si = si
        self.goal = si.spec.goal
        self.version = si.first_version - 1
        self.code_version: dict[str, int] = {}
        self.out = SynthOutcome(program=None)
        self.last_demo: tuple[str, bool] | None = None
        self.errors: list[str] = []

    # ---------- tools ----------
    async def simulate(
        self, code: str, layout_id: str, render: bool
    ) -> tuple[dict[str, Any], list[str]]:
        layout = self.si.layouts.get(layout_id)
        if layout is None:
            return {"error": f"no layout {layout_id!r}; use list_layouts"}, []
        if code not in self.code_version:
            self.version += 1
            self.code_version[code] = self.version
            self._save_version(code)
        v = self.code_version[code]
        res = await sandbox.simulate(code, layout, self.goal, render=render or layout_id == "demo",
                                     calibration_json=self.si.calibration_json)  # fmt: skip
        res = self._keep_artifacts(res, layout_id, v)
        summary = summarize(res)
        self.out.results[f"v{v}:{layout_id}"] = summary | {"result": res.model_dump(mode="json")}
        if layout_id == "demo":
            self.last_demo = (code, res.goal_ok)
            prog = next(p for p in self.out.versions if p.version == v)
            prog.passed_demo = res.goal_ok
        passed = sum(r.holds for r in res.goal_results)
        self.ctx.emit("tool_call", payload={"agent": "coder", "iteration": self.out.turns, "tool": "simulate",
                                            "args": {"layout": layout_id, "program": v, "render": render},
                                            "result": {"ok": res.goal_ok, "error": (res.error or "").splitlines()[-1] if res.error else None,
                                                       "clauses_passed": passed, "clauses_total": len(res.goal_results),
                                                       "layout": layout_id}})  # fmt: skip
        if layout_id == "demo":
            self.ctx.emit("metric", payload={"name": "clauses_passed", "value": passed, "total": len(res.goal_results),
                                             "iteration": self.out.turns, "program": v})  # fmt: skip
        images = [res.renders["top"]] if render and res.renders.get("top") else []
        return summary | {"program_version": v}, images

    def _save_version(self, code: str) -> None:
        v = self.version
        prev = next((p for p in reversed(self.out.versions)), None)
        parent = prev.code if prev else (self.si.start_code or "")
        diff = "".join(
            difflib.unified_diff(
                parent.splitlines(True), code.splitlines(True), f"v{v - 1}.py", f"v{v}.py"
            )
        )
        author = {"synth": "wonder", "harden": "wonder-harden", "correct": "wonder-correction"}[
            self.si.mode
        ]
        p = Program(version=v, parent_version=prev.version if prev else (v - 1 if v > 1 else None), code=code,
                    author=author, diff_from_parent=diff)  # fmt: skip
        self.out.versions.append(p)
        path = self.si.art / "programs" / f"v{v}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(code)
        self.ctx.emit("artifact", payload={"name": path.name, "path": f"artifacts/programs/{path.name}", "kind": "code",
                                           "label": f"Program v{v}", "diff": diff[:4000]})  # fmt: skip

    def _keep_artifacts(self, res: SimResult, layout_id: str, v: int) -> SimResult:
        """Copy the sim's twin and renders into the run (paths relative to the run dir)."""
        dest = self.si.art / "sim" / f"{layout_id}_v{v}"
        dest.mkdir(parents=True, exist_ok=True)
        renders = {}
        for k, src in res.renders.items():
            shutil.copy(src, dest / Path(src).name)
            renders[k] = f"artifacts/sim/{dest.name}/{Path(src).name}"
        twin = None
        if res.twin_trajectory:
            shutil.copy(res.twin_trajectory, dest / Path(res.twin_trajectory).name)
            twin = f"artifacts/sim/{dest.name}/{Path(res.twin_trajectory).name}"
        res = res.model_copy(update={"renders": renders, "twin_trajectory": twin})
        (dest / "result.json").write_text(res.model_dump_json(indent=1))
        if twin and layout_id == "demo":
            self.ctx.emit("artifact", payload={"name": Path(twin).name, "path": twin, "kind": "trajectory",
                                               "label": f"Robot run, v{v}"})  # fmt: skip
        return res

    def inspect_demo(self, t: float) -> tuple[dict[str, Any], list[str]]:
        kf = min(self.si.keyframes, key=lambda k: abs(k[0] - t))
        pos = {}
        for o in self.si.grounded.initial:
            p = (o.x, o.y)
            for s in self.si.grounded.segments:
                if s.object == o.name and s.t1 <= t:
                    p = s.to_cm
                elif s.object == o.name and s.t0 <= t < s.t1:
                    a = (t - s.t0) / max(1e-6, s.t1 - s.t0)
                    p = (
                        s.from_cm[0] + a * (s.to_cm[0] - s.from_cm[0]),
                        s.from_cm[1] + a * (s.to_cm[1] - s.from_cm[1]),
                    )
            pos[o.name] = {"x": round(p[0], 1), "y": round(p[1], 1)}
        self.ctx.emit("tool_call", payload={"agent": "coder", "iteration": self.out.turns, "tool": "inspect_demo",
                                            "args": {"t": t}, "result": {"ok": True, "frame_t": kf[0]}})  # fmt: skip
        return {"keyframe_t": kf[0], "positions_cm": pos}, [str(kf[1])]

    def check_reach(self, x: float, y: float) -> dict[str, Any]:
        base = self.si.layouts["demo"].robot_base_cm
        d = math.dist(base, (x, y)) / 100
        margin = min(d - C.REACH_MIN_M, C.REACH_MAX_M - d) * 100
        self.ctx.emit("tool_call", payload={"agent": "coder", "iteration": self.out.turns, "tool": "check_reach",
                                            "args": {"x_cm": x, "y_cm": y}, "result": {"ok": margin >= 0}})  # fmt: skip
        return {"reachable": margin >= 0, "margin_cm": round(margin, 1)}

    def list_layouts(self) -> list[dict[str, str]]:
        return [
            {"id": k, "description": v.description or v.source} for k, v in self.si.layouts.items()
        ]

    def submit(self, code: str, explanation: str) -> dict[str, Any]:
        ok = self.last_demo is not None and self.last_demo[0] == code and self.last_demo[1]
        self.ctx.emit("tool_call", payload={"agent": "coder", "iteration": self.out.turns, "tool": "submit",
                                            "args": {"program": self.code_version.get(code)}, "result": {"ok": ok}})  # fmt: skip
        if not ok:
            return {
                "accepted": False,
                "error": 'Rejected: your last simulate on "demo" must be this exact code and pass every clause.',
            }
        prog = next(p for p in self.out.versions if p.version == self.code_version[code])
        prog.explanation = explanation
        self.out.program, self.out.submitted = prog, True
        return {"accepted": True}

    # ---------- the loop ----------
    async def run_tool(self, name: str, args: dict[str, Any]) -> tuple[Any, list[str]]:
        try:
            if name == "simulate":
                return await self.simulate(
                    str(args.get("code", "")),
                    str(args.get("layout", "demo")),
                    bool(args.get("render")),
                )
            if name == "inspect_demo":
                return self.inspect_demo(float(args.get("t", 0)))
            if name == "check_reach":
                return self.check_reach(float(args.get("x_cm", 0)), float(args.get("y_cm", 0))), []
            if name == "list_layouts":
                return self.list_layouts(), []
            if name == "submit":
                return self.submit(str(args.get("code", "")), str(args.get("explanation", ""))), []
        except (ValueError, TypeError) as e:
            return {"error": f"bad arguments: {e}"}, []
        return {"error": f"no tool {name!r}"}, []

    def first_message(self, draft: dict[str, Any] | None) -> list[dict[str, Any]]:
        si = self.si
        text = (
            f"## Task\n{si.spec.model_dump_json(indent=1)}\n\n## Measured in the demo\n{_demo_table(si)}\n\n"
            f"## Narration\n{si.transcript.text or '(none)'}\n\n"
            "## Layouts\n" + json.dumps(self.list_layouts()) + "\n"
        )
        if si.start_code:
            text += f"\n## Current program\n```python\n{si.start_code}\n```\n"
        if si.extra:
            text += "\n" + si.extra + "\n"
        if draft:
            text += (f"\n## A teammate's draft (Muse Spark Open), simulated on demo: {draft['summary']['clauses_passed']} clauses\n"
                     f"```python\n{draft['code']}\n```\nUse it if it helps.\n")  # fmt: skip
        text += "\nKeyframes of the demo follow (time in seconds)."
        parts: list[dict[str, Any]] = [{"type": "input_text", "text": text}]
        for t, p in si.keyframes:
            parts += [
                {"type": "input_text", "text": f"t = {t:.1f} s"},
                {"type": "input_image", "image_url": jpeg_data_url(p)},
            ]
        return parts

    async def run(self) -> SynthOutcome:
        system, sha = system_prompt()
        draft = await self.best_draft() if self.si.drafts and self.si.mode == "synth" else None
        items: list[dict[str, Any]] = [{"role": "system", "content": system},
                                       {"role": "user", "content": self.first_message(draft)}]  # fmt: skip
        for turn in range(1, MAX_TURNS + 1):
            self.out.turns = turn
            req = {"stage": self.si.mode, "prompt": sha, "conversation": _hash_items(items)}
            call = providers.responses_call(settings.model_wonder, input=items, tools=TOOLS, reasoning={"effort": "high"},
                                            max_output_tokens=WONDER_MAX_OUT)  # fmt: skip
            raw = await gateway.cached_call(ctx=self.ctx, purpose=f"{self.si.mode}:turn{turn}", provider="meta",
                                            model=settings.model_wonder, request=req, estimate_usd=TURN_ESTIMATE,
                                            call=call, validate=gateway.passthrough)  # fmt: skip
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
                        self.ctx.emit("log", payload={"message": text[:300], "agent": "coder"})
            self.out.trace.append({"turn": turn, "calls": [c["name"] for c in calls]})
            if not calls:
                items.append(
                    {
                        "role": "user",
                        "content": 'Use the tools: simulate your program on "demo", then submit it.',
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
                err = result.get("error") if isinstance(result, dict) else None
                if err:
                    self.errors.append(str(err).splitlines()[-1])
            if self.out.submitted:
                break
            nudge = ""
            if len(self.errors) >= 2 and self.errors[-1] == self.errors[-2]:
                nudge = "You hit the same error twice in a row. Step back and rethink the approach before simulating again."
                self.errors.append("")
            if images or nudge:
                content: list[dict[str, Any]] = [
                    {"type": "input_text", "text": nudge or "The image you asked for."}
                ]
                for img in images:
                    content.append(
                        {
                            "type": "input_image",
                            "image_url": jpeg_data_url(
                                Path(img) if Path(img).is_absolute() else self.si.art.parent / img
                            ),
                        }
                    )
                items.append({"role": "user", "content": content})
            if turn == MAX_TURNS - 1 and not self.out.submitted:
                items.append(
                    {
                        "role": "user",
                        "content": "One tool call left: submit your best passing program now.",
                    }
                )
        if self.out.program is None:  # no accepted submit: the best demo-passing version, if any
            passing = [p for p in self.out.versions if p.passed_demo]
            if passing:
                self.out.program = passing[-1]
                self.ctx.emit(
                    "log",
                    payload={
                        "message": f"Wonder did not submit; using v{passing[-1].version}, which passed the demo"
                    },
                )
        if draft and self.out.program and self.out.program.code.strip() == draft["code"].strip():
            self.out.winner = "spark-open-draft"
        return self.out

    async def best_draft(self) -> dict[str, Any] | None:
        """Best-of-N: two Spark Open drafts on Baseten, simulated; the best goes to Wonder."""
        system, sha = system_prompt()
        user = (f"## Task\n{self.si.spec.model_dump_json()}\n\n## Measured in the demo\n{_demo_table(self.si)}\n\n"
                'Return JSON {"code": "<the full program>", "explanation": "<one sentence>"}. No tools are available.')  # fmt: skip

        async def one(i: int) -> dict[str, Any] | None:
            call = providers.chat_call(
                "baseten", settings.model_spark_open,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                response_format={"type": "json_object"}, max_tokens=6000, temperature=0.4 + 0.3 * i,
            )  # fmt: skip
            try:
                raw = await gateway.cached_call(ctx=self.ctx, purpose=f"draft:{i}", provider="baseten",
                                                model=settings.model_spark_open,
                                                request={"stage": "draft", "i": i, "prompt": sha, "user": user},
                                                estimate_usd=0.03, call=call, validate=gateway.passthrough)  # fmt: skip
                d = parse_json(
                    ((raw.get("choices") or [{}])[0].get("message") or {}).get("content") or "",
                    "program",
                )
                return {
                    "code": str(d.get("code", "")),
                    "explanation": str(d.get("explanation", "")),
                    "i": i,
                }
            except DemoBotError as e:
                self.ctx.emit("log", payload={"message": f"Spark Open draft {i} failed ({e.code})"})
                return None

        drafts = [
            d for d in await asyncio.gather(*(one(i) for i in range(DRAFTS))) if d and d["code"]
        ]
        best = None
        for d in drafts:
            res = await sandbox.simulate(d["code"], self.si.layouts["demo"], self.goal)
            d["summary"] = summarize(res)
            d["passed"] = sum(r.holds for r in res.goal_results)
            self.out.drafts.append(
                {k: v for k, v in d.items() if k != "summary"}
                | {"goal_ok": res.goal_ok, "error": res.error}
            )
            self.ctx.emit("tool_call", payload={"agent": "coder", "iteration": 0, "tool": "simulate",
                                                "args": {"layout": "demo", "draft": d["i"], "author": "Muse Spark Open"},
                                                "result": {"ok": res.goal_ok, "clauses_passed": d["passed"],
                                                           "clauses_total": len(res.goal_results)}})  # fmt: skip
            if best is None or d["passed"] > best["passed"]:
                best = d
        return best


async def synthesize(ctx: RunContext, si: SynthInput) -> SynthOutcome:
    return await Loop(ctx, si).run()
