"""The supervisor: Muse Spark Open decides how to recover when a run fails (docs/05 §B).

A bounded tool loop (at most 4 decisions), every decision a visible `decision` event with its
observation, tool, arguments, result and a one-sentence reason. If no model is available, a fixed
policy decides. After each action only the affected stages are rerun.
"""

import json
from dataclasses import dataclass, field
from typing import Any

from demobot import gateway, goal_dsl, providers
from demobot.config import settings
from demobot.errors import DemoBotError
from demobot.llm import jpeg_data_url, output_text
from demobot.schemas import AgentDecision, GoalClause, GroundedDemo, TaskSpec, Verification

MAX_DECISIONS = 4
BUDGET = {"rewatch": 2, "retrack": 2, "reprogram": 1}
FIXED_POLICY = {"spec_mismatch": "rewatch", "program_bug": "reprogram", "perception_gap": "retrack",
                "judge_dissent": "accept"}  # fmt: skip

SYSTEM = """You are the supervisor of DemoBot, a system that learns a robot program from one video of a person doing a tabletop task.
A run has failed a check. Decide the single best next action, using exactly one tool call per turn.

Failure classes:
- spec_mismatch: the task specification does not match what the person actually did (the goal fails on the measured real final state). Investigate with rewatch, then fix it with revise_spec.
- program_bug: the robot program fails the goal in simulation. Use reprogram with concrete feedback.
- perception_gap: the simulated result looks wrong to the vision model. Try retrack with a better phrase, or accept if the symbolic and real-world checks pass and the gap is explained.
- judge_dissent: the visual judge disagrees although the checks pass. Read its reasons; accept with a caveat if they concern something outside the goal (a distractor, rendering style), otherwise investigate.

Be economical: each tool has a budget. Accept only when the evidence supports the goal, and say so plainly in the caveat. Stop if recovery is not possible.
Keep the reason for each decision to one sentence."""

TOOLS: list[dict[str, Any]] = [
    {"type": "function", "function": {"name": "rewatch", "description": "Ask Muse Spark 1.3 a targeted question about a time window of the demo video.",
     "parameters": {"type": "object", "properties": {"t0": {"type": "number"}, "t1": {"type": "number"}, "question": {"type": "string"},
                                                     "reason": {"type": "string"}}, "required": ["t0", "t1", "question", "reason"]}}},
    {"type": "function", "function": {"name": "retrack", "description": "Rerun SAM 3.1 for one object with a different noun phrase, then re-measure and re-verify.",
     "parameters": {"type": "object", "properties": {"object": {"type": "string"}, "phrase": {"type": "string"}, "reason": {"type": "string"}},
                    "required": ["object", "phrase", "reason"]}}},
    {"type": "function", "function": {"name": "revise_spec", "description": "Replace the goal clauses of the task specification (goal DSL), then re-check the real final state and re-verify. Use after rewatch has confirmed what happened.",
     "parameters": {"type": "object", "properties": {"goal": {"type": "array", "items": {"type": "object"}}, "summary": {"type": "string"},
                                                     "reason": {"type": "string"}}, "required": ["goal", "reason"]}}},
    {"type": "function", "function": {"name": "reprogram", "description": "Send the program back to the Muse Wonder coder with feedback, then re-verify.",
     "parameters": {"type": "object", "properties": {"feedback": {"type": "string"}, "reason": {"type": "string"}}, "required": ["feedback", "reason"]}}},
    {"type": "function", "function": {"name": "ask_user", "description": "Ask the person a multiple-choice question (shown in the UI; may get no answer).",
     "parameters": {"type": "object", "properties": {"question": {"type": "string"}, "options": {"type": "array", "items": {"type": "string"}},
                                                     "reason": {"type": "string"}}, "required": ["question", "options", "reason"]}}},
    {"type": "function", "function": {"name": "accept", "description": "Accept the run with a visible caveat.",
     "parameters": {"type": "object", "properties": {"caveat": {"type": "string"}, "reason": {"type": "string"}}, "required": ["caveat", "reason"]}}},
    {"type": "function", "function": {"name": "stop", "description": "Give up cleanly.",
     "parameters": {"type": "object", "properties": {"reason": {"type": "string"}}, "required": ["reason"]}}},
]  # fmt: skip


@dataclass
class Outcome:
    accepted: bool
    caveat: str = ""
    decisions: list[AgentDecision] = field(default_factory=list)
    stopped: str = ""


def observation(run: Any, error: DemoBotError) -> dict[str, Any]:
    """The compact JSON the supervisor sees."""
    art = run.art
    spec = run.read("taskspec.json", TaskSpec)
    obs: dict[str, Any] = {"task": spec.summary, "failed_stage": error.stage, "error": f"{error.code}: {error.message}",
                           "goal": [c.model_dump(exclude_none=True) for c in spec.goal],
                           "steps": [f"{s.t_start:.1f}-{s.t_end:.1f}s {s.action} {s.object}" + (f" -> {s.target}" if s.target else "")
                                     + (f" ({s.relation})" if s.relation else "") for s in spec.steps],
                           "objects": [f"{o.name} ({o.kind}, {o.role})" for o in spec.objects]}  # fmt: skip
    if (art / "verify.json").exists():
        v = Verification.model_validate_json((art / "verify.json").read_text())
        obs["failure_class"] = v.failure_class
        for k in ("symbolic", "real_world", "perceptual"):
            c = getattr(v, k)
            obs[k] = {"ok": c.ok, "inconclusive": c.inconclusive, "detail": c.detail,
                      "clauses": [{"holds": r.holds, "detail": r.detail} for r in c.clauses]}  # fmt: skip
        obs["judge"] = v.judge.model_dump() if v.judge else None
    if (art / "tracks.json").exists():
        obs["tracks"] = {t["name"]: {"phrase": t["phrase"], "quality": t["quality"], "flags": t["flags"]}
                         for t in json.loads((art / "tracks.json").read_text())["tracks"]}  # fmt: skip
    if (art / "grounded.json").exists():
        gd = run.read("grounded.json", GroundedDemo)
        obs["grounding_flags"] = gd.flags
        obs["real_final_cm"] = {o.name: [o.x, o.y] for o in gd.final}
    if (art / "crosswatch.json").exists():
        obs["crosswatch_agreement"] = json.loads((art / "crosswatch.json").read_text()).get(
            "agreement"
        )
    return obs


class Supervisor:
    def __init__(self, run: Any, error: DemoBotError) -> None:
        self.run = run
        self.ctx = run.ctx.at("supervise")
        self.error = error
        self.used = {k: 0 for k in BUDGET}
        self.out = Outcome(accepted=False)
        self.history: list[dict[str, Any]] = []

    # ---------- deciding ----------
    async def decide(self, obs: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
        """(tool, args, who) from Spark Open (Baseten, then Modal), else the fixed policy."""
        art = self.run.art
        images = [p for p in (art / "reference_frame.jpg",) if p.exists()]
        if (art / "verify.json").exists():
            r = json.loads((art / "verify.json").read_text()).get("renders", {}).get("camera")
            if r and (self.run.dir / r).exists():
                images.append(self.run.dir / r)
        content: list[dict[str, Any]] = [{"type": "text", "text": "Observation:\n" + json.dumps(obs, indent=1)[:12000]
                                          + "\n\nBudgets left: " + json.dumps({k: BUDGET[k] - self.used[k] for k in BUDGET})
                                          + "\nPrevious decisions: " + json.dumps(self.history)[:3000]}]  # fmt: skip
        content += [
            {"type": "image_url", "image_url": {"url": jpeg_data_url(p)}} for p in images[:2]
        ]
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}]
        req = {
            "stage": "supervise",
            "obs": obs,
            "history": self.history,
            "images": [gateway.sha256_file(p) for p in images[:2]],
        }

        def route(provider: str, model: str, label: str) -> gateway.Route:
            call = providers.chat_call(provider, model, affinity_key=self.run.run_id, messages=messages, tools=TOOLS,
                                       tool_choice="required", max_tokens=3000)  # fmt: skip
            return gateway.Route(provider, model, req, 0.03, call, label)

        def validate(raw: Any) -> tuple[str, dict[str, Any]]:
            msg = ((raw.get("choices") or [{}])[0].get("message")) or {}
            calls = msg.get("tool_calls") or []
            if not calls:
                raise DemoBotError("INVALID_MODEL_OUTPUT", "no tool call", stage="supervise")
            fn = calls[0]["function"]
            try:
                return fn["name"], json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError as e:
                raise DemoBotError(
                    "INVALID_MODEL_OUTPUT", f"bad arguments: {e}", stage="supervise"
                ) from e

        try:
            (tool, args), used = await gateway.chain_call(
                ctx=self.ctx, purpose="supervise",
                routes=[route("baseten", settings.model_spark_open, "Muse Spark Open @ Baseten"),
                        route("modal", settings.model_spark_open_modal, "Muse Spark Open @ Modal")],
                validate=validate,
            )  # fmt: skip
            return tool, args, used.name()
        except DemoBotError as e:
            cls = obs.get("failure_class") or {"PROGRAM_FAILED": "program_bug"}.get(
                self.error.code, "spec_mismatch"
            )
            tool = FIXED_POLICY.get(cls, "stop")
            self.ctx.emit("log", payload={"fallback": True, "purpose": "supervise", "from": "Muse Spark Open", "to": "fixed policy",
                                          "code": e.code, "message": f"supervisor model unavailable ({e.code}); fixed policy: {tool}"})  # fmt: skip
            return tool, self.policy_args(tool, obs), "fixed policy"

    def policy_args(self, tool: str, obs: dict[str, Any]) -> dict[str, Any]:
        spec = self.run.read("taskspec.json", TaskSpec)
        if tool == "rewatch":
            t0 = min((s.t_start for s in spec.steps), default=0.0)
            t1 = max((s.t_end for s in spec.steps), default=5.0)
            return {"t0": t0, "t1": t1, "question": "Where does each moved object end up, relative to the other objects?",
                    "reason": "fixed policy for a spec mismatch"}  # fmt: skip
        if tool == "reprogram":
            return {"feedback": "The program failed the goal in simulation: " + json.dumps(obs.get("symbolic", {}))[:800],
                    "reason": "fixed policy for a program bug"}  # fmt: skip
        if tool == "retrack":
            weak = min(
                (obs.get("tracks") or {"": {"quality": 1}}).items(),
                key=lambda kv: kv[1].get("quality", 1),
            )[0]
            alt = next((a for o in spec.objects if o.name == weak for a in o.alt_names), weak)
            return {"object": weak, "phrase": alt, "reason": "fixed policy for a perception gap"}
        if tool == "accept":
            three = all(
                (obs.get(k) or {}).get("ok") for k in ("symbolic", "real_world", "perceptual")
            )
            if not three:
                return {"reason": "fixed policy: the checks do not all pass"} | {"_stop": True}
            return {
                "caveat": "The judge disagreed, but all three checks pass.",
                "reason": "fixed policy for judge dissent",
            }
        return {"reason": "fixed policy"}

    # ---------- acting ----------
    async def act(self, tool: str, args: dict[str, Any]) -> str:
        from demobot import pipeline

        run = self.run
        if tool in BUDGET:
            if self.used[tool] >= BUDGET[tool]:
                return f"refused: the {tool} budget is used up"
            self.used[tool] += 1
        if tool == "accept":
            if args.get("_stop"):
                self.out.stopped = args.get("reason", "")
                return "cannot accept: the checks do not all pass"
            self.out.accepted, self.out.caveat = True, str(args.get("caveat", ""))
            return f"accepted with caveat: {self.out.caveat}"
        if tool == "stop":
            self.out.stopped = str(args.get("reason", "stopped"))
            return "stopped"
        if tool == "ask_user":
            self.ctx.emit("question", payload={"id": f"q{len(self.history)}", "text": args.get("question", ""),
                                               "options": args.get("options", [])})  # fmt: skip
            return "no answer (the run is not attended)"
        if tool == "rewatch":
            return await self.rewatch(
                float(args.get("t0", 0)), float(args.get("t1", 0)), str(args.get("question", ""))
            )
        if tool == "retrack":
            return await self.retrack(str(args.get("object", "")), str(args.get("phrase", "")))
        if tool == "revise_spec":
            spec = run.read("taskspec.json", TaskSpec)
            try:
                goal = [GoalClause.model_validate(g) for g in args.get("goal", [])]
            except Exception as e:
                return f"rejected: the goal does not parse ({str(e)[:200]})"
            from demobot.watch import check_spec

            new = spec.model_copy(
                update={"goal": goal, "summary": args.get("summary") or spec.summary}
            )
            problems = check_spec(new, 1e9)
            if problems:
                return "rejected: " + "; ".join(problems)[:400]
            run.write("taskspec.json", new)
            gd = run.read("grounded.json", GroundedDemo)
            gd.real_world = goal_dsl.evaluate(
                goal, goal_dsl.to_state(gd.final), goal_dsl.to_state(gd.initial)
            )
            run.write("grounded.json", gd)
            real_ok = goal_dsl.all_hold(gd.real_world)
            if not real_ok:
                return "spec revised, but the revised goal still fails on the real final state: " + \
                    "; ".join(r.detail for r in gd.real_world if not r.holds)[:300]  # fmt: skip
            return (
                "spec revised; the goal now holds on the real final state. "
                + await self.reverify(reprogram_if_needed=True)
            )
        if tool == "reprogram":
            await pipeline.stage_program(run, feedback=str(args.get("feedback", "")))
            return "new program: " + await self.reverify()
        return f"unknown tool {tool}"

    async def rewatch(self, t0: float, t1: float, question: str) -> str:
        from demobot import providers as prov

        clip = self.run.art / "analysis.mp4"
        sha = gateway.sha256_file(clip)

        async def call(timeout: float) -> tuple[Any, float, dict[str, Any]]:
            fid = await prov.upload_file(clip, sha)
            c = prov.responses_call(settings.model_spark, reasoning={"effort": "medium"}, max_output_tokens=6000,
                                    input=[{"role": "user", "content": [
                                        {"type": "input_text", "text": f"Focus on {t0:.1f}-{t1:.1f} s of this video. {question} "
                                         "Answer in at most three sentences; directions as seen in the video (top = behind)."},
                                        {"type": "input_file", "file_id": fid}]}])  # fmt: skip
            return await c(timeout)

        raw = await gateway.cached_call(ctx=self.ctx, purpose="rewatch", provider="meta", model=settings.model_spark,
                                        request={"stage": "rewatch", "clip": sha, "t0": t0, "t1": t1, "q": question},
                                        estimate_usd=0.08, call=call, validate=gateway.passthrough)  # fmt: skip
        return "Spark 1.3: " + output_text(raw)[:600]

    async def retrack(self, name: str, phrase: str) -> str:
        from demobot import ground as ground_mod
        from demobot import pipeline
        from demobot.perceive import quality, sam_video, split_tracks, to_track
        from demobot.schemas import IngestInfo, Track

        run = self.run
        info = run.read("ingest.json", IngestInfo)
        raw = json.loads((run.art / "tracks.json").read_text())
        if name not in {t["name"] for t in raw["tracks"]}:
            return f"no object {name!r}"
        clip = run.art / "analysis.mp4"
        per = split_tracks(
            await sam_video(self.ctx, clip, gateway.sha256_file(clip), phrase), info.analysis_frames
        )
        if not per:
            return f"SAM found nothing for '{phrase}'"
        oid, inst = max(per.items(), key=lambda kv: quality(kv[1], info.analysis_frames))
        stab = (
            json.loads((run.art / "stabilise.json").read_text())["M"]
            if (run.art / "stabilise.json").exists()
            else None
        )
        tr = to_track(name, phrase, oid, inst, info.analysis_frames, info.analysis_fps, stab, [])
        raw["tracks"] = [
            json.loads(tr.model_dump_json()) if t["name"] == name else t for t in raw["tracks"]
        ]
        (run.art / "tracks.json").write_text(json.dumps(raw))
        _ = (ground_mod, Track)
        await pipeline.stage_ground(run)
        await pipeline.stage_twin_build(run)
        return (
            f"retracked {name} as '{phrase}' (quality {tr.quality:.2f}); " + await self.reverify()
        )

    async def reverify(self, reprogram_if_needed: bool = False) -> str:
        from demobot import pipeline

        try:
            summary = await pipeline.stage_verify(self.run)
            return "verify passes: " + summary
        except DemoBotError as e:
            if (
                reprogram_if_needed
                and "program_bug" in e.message
                and self.used["reprogram"] < BUDGET["reprogram"]
            ):
                self.used["reprogram"] += 1
                await pipeline.stage_program(
                    self.run, feedback="The goal was revised; write the program for the new goal."
                )
                return "reprogrammed for the revised goal; " + await self.reverify()
            return f"verify still fails: {e.message}"

    async def loop(self) -> Outcome:
        for step in range(1, MAX_DECISIONS + 1):
            obs = observation(self.run, self.error)
            tool, args, who = await self.decide(obs)
            reason = str(args.pop("reason", ""))[:300]
            result = await self.act(tool, dict(args))
            if result.startswith("verify passes") or "verify passes" in result:
                self.out.accepted = True
            d = AgentDecision(agent="supervisor", step=step, observation=_obs_summary(obs), reasoning_summary=reason or f"{who} chose {tool}",
                              tool=tool, args={k: v for k, v in args.items() if not k.startswith("_")}, result=result[:600])  # fmt: skip
            self.out.decisions.append(d)
            self.ctx.emit("decision", payload=d.model_dump(mode="json") | {"by": who})
            self.history.append({"tool": tool, "args": d.args, "result": d.result})
            if self.out.accepted or self.out.stopped:
                break
        return self.out


def _obs_summary(obs: dict[str, Any]) -> str:
    parts = [f"{obs.get('failure_class') or obs.get('error')}"]
    for k in ("symbolic", "real_world", "perceptual"):
        if k in obs:
            parts.append(f"{k} {'✓' if obs[k]['ok'] else '✗'}")
    if obs.get("judge"):
        parts.append(f"judge {'✓' if obs['judge']['same_goal_achieved'] else '✗'}")
    return ", ".join(parts)


async def supervise(run: Any, error: DemoBotError) -> Outcome:
    return await Supervisor(run, error).loop()
