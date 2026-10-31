# 05. Agents: the coder, the supervisor and the red team

The agents are where DemoBot is "agentic" for real. Each one:
- runs a bounded tool loop;
- logs every observation, tool call and result as events;
- shows a one-sentence reasoning summary, never a hidden chain of thought;
- can be replayed exactly from cache.

## A. The coder: Muse Wonder (`program/synth.py`)

**Goal:** produce `run(scene, robot)` that achieves the TaskSpec goal on the demo layout **and** on new layouts.

### Inputs (stable prefix first, for prompt caching)

1. **System prompt** `prompts/coder.md`:
   - the role;
   - the skill API reference (generated from `program/api.py` docstrings);
   - the sandbox rules;
   - style rules: generalise with `kind` and `role` selectors, never hard-code demo coordinates, use `free_spot()` for open placements, check `robot.can_reach` before moving, and keep it under 60 lines.
2. **User message:**
   - `TaskSpec` (objects, steps, goal, generalisation rule);
   - a `GroundedDemo` summary table (object, start cm, end cm, step matches);
   - the transcript, if any;
   - 4 keyframes: start, two mid-step frames, end.

### Tools (JSON-schema function tools)

| Tool | Args | Returns |
| --- | --- | --- |
| `simulate` | `code`, `layout` (`"demo"` or a stress layout ID), `render` (bool) | `ok`, `error` (traceback trimmed to 20 lines), skill-call log, the goal clause table, the final state table, and whether perceptual verification ran. If `render` is set, the next user message attaches the top-down sim image. |
| `inspect_demo` | `t` (seconds) | That keyframe as an image (sent in the follow-up message), plus object positions at time t |
| `check_reach` | `x_cm`, `y_cm` | `reachable`, `margin_cm` |
| `list_layouts` | none | The IDs and one-line descriptions of the available stress layouts (after M9) |
| `submit` | `code`, `explanation` | Ends the loop. Accepted only if the last `simulate` call on `"demo"` with this exact code passed. |

### Loop rules

- At most **8 tool turns** per synthesis and at most 2 syntheses per run. Reset if Wonder is stuck: the same error twice in a row.
- Each `simulate` call is validated by the sandbox guard first (below). Guard rejections come back as tool errors.
- If the budget allows, Wonder's first draft is generated together with **2 alternative drafts from Muse Spark Open on Baseten**, in parallel. All three are simulated, and Wonder starts its loop from the best one. This is a small best-of-N.
  - If no Spark Open draft wins, log that honestly.
  - Record which draft won (`eval` reports it).
- Events emitted:
  - `tool_call` for each tool call;
  - `artifact` for each code version (with a diff from the previous version);
  - `metric` with the goal pass count per iteration.
- **Hardening mode** (`harden`): the same loop, starting from the current program. The input adds the failing stress layouts: layout JSON, sim render image, failed clauses and errors. The instruction is to fix the root cause, not special-case one layout. `simulate` accepts stress IDs.
- **Correction mode** (`correct`): the same loop. The input adds the correction transcript. Wonder must also return `goal_patch` (a list of clause edits), which is applied and validated before submitting.

### Sandbox (`program/sandbox.py`)

The generated code is untrusted.

1. **AST guard** (allowlist):
   - Allowed: module-level `def run(scene, robot):` plus helper `def`s; literals; arithmetic; comparisons; `if`/`for`/`while` with an iteration cap (instrumented); list, dict and set comprehensions; f-strings.
   - Allowed names: `scene`, `robot`, `math`, `log`, `range`, `len`, `min`, `max`, `abs`, `sorted`, `enumerate`, `zip`, `list`, `dict`, `set`, `tuple`, `float`, `int`, `str`, `round`, `sum`, `any`, `all`, `reversed`.
   - Forbidden: `import` (except `math`, which is pre-injected), attribute names starting with `_`, `exec`, `eval`, `open`, `compile`, `globals`, `getattr`, `setattr`, `__builtins__`, `lambda` at module level, `class`, `global`/`nonlocal`, `try` around the API (errors must surface).
2. **Execution:**
   - in a separate process (local) or a Modal Sandbox (parallel stress runs);
   - CPU time limit 20 s, memory limit 1 GB;
   - at most 40 skill calls;
   - only the API objects are injected.
3. **Determinism:** the seed is fixed per layout, so identical code plus layout gives identical results. Results are cached by `(code_hash, layout_hash, sim_version)`.

## B. The supervisor: Muse Spark Open (`agents/supervisor.py`)

**Trigger:** any failure class from Verify, an unresolved Watch uncertainty, a low-quality track, `no_motion_for_step`, or a failed real-world check.

**Observation given** (compact JSON plus at most 2 images):
- run summary;
- failure class and details;
- clause tables;
- track qualities;
- agreement score;
- previous decisions.

**Tools:**

| Tool | Effect | Cost guard |
| --- | --- | --- |
| `rewatch(t0, t1, question)` | Spark 1.3 answers a targeted question about a video window (re-uses the uploaded `file_id`; asks Spark to focus on the span) | ≤ 2 per run |
| `retrack(object, phrase)` | Reruns SAM for one object with a different phrase, e.g. an `alt_name` or a phrase the supervisor proposes | ≤ 2 per run |
| `revise_spec(patch)` | Applies a validated patch to the TaskSpec (rename, change target, change relation, drop a phantom step) | free |
| `reprogram(feedback)` | Re-enters the Wonder coder loop with feedback | ≤ 1 per run |
| `adjust_skill(params)` | Changes grasp height, approach offset or placement gap within bounds | free |
| `ask_user(question, options)` | Emits a `question` event. In live UI mode it waits up to 120 s for an answer (click or voice), otherwise falls through. | n/a |
| `accept(caveat)` | Accepts the run with a visible caveat, e.g. "judge dissent but all 3 checks pass" | n/a |
| `stop(reason)` | Gives up cleanly | n/a |

**Rules:**
- At most 4 decisions per run.
- Each decision is a `decision` event containing the observation summary, the tool, the args, the result and a one-sentence reason.
- After each action, rerun only the affected stages.
- There is a fixed policy fallback when no LLM is available:

  | Failure class | Fallback action |
  | --- | --- |
  | `spec_mismatch` | `rewatch` |
  | `program_bug` | `reprogram` |
  | `perception_gap` | `retrack` |
  | `judge_dissent` | `accept` with a caveat if all three checks pass |

- If Baseten does not support `tools` (PROBE), use the same tools as a JSON "action" schema with one action per turn.

## C. The red team: a Muse Spark Open swarm (`agents/redteam.py`)

Six personas run **in parallel** on Baseten, each asked for 2 layouts (12 in total):

| Persona | Tries to break the program by |
| --- | --- |
| `crowder` | Packing objects close together, so grasps and placements collide |
| `edge_walker` | Putting targets near the work-area edges and reach limits |
| `twin_maker` | Adding extra instances of a moved kind (e.g. 3 pens instead of 2), which tests generalisation |
| `distractor` | Adding 1–2 unseen objects the goal does not mention (they must not be moved) |
| `mirror` | Mirroring or rotating the scene, and moving containers to the opposite side |
| `squeezer` | Putting reference objects where "next to" or "line up" space is tight but feasible |

**Persona input:**
- the TaskSpec goal;
- the demo layout JSON;
- the work-area bounds;
- the reach map summary;
- the object size table;
- the rule that the layout **must still be solvable**.

**Output:** `Layout` JSON plus `why_hard` (one sentence).

**Validator (no LLM):**
- inside the work area;
- no overlaps (2 cm clearance);
- all objects reachable;
- containers can fit their goal objects;
- goal selectors resolve.

Invalid layouts get one repair request with the validator errors. If still invalid, drop the layout; never fake it.

**Run:** all valid layouts are simulated with the current program, in parallel. Goals are re-evaluated with the quantifiers on each layout's own initial state. Failures are clustered by `(failure clause, persona)` for the hardening prompt.

**UI:** a 4 × 3 grid of mini twins. Each tile shows the persona tag, a pass or fail badge, and replay on hover. A robustness bar animates from before to after.
