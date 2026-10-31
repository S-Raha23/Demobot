# 02. Architecture

## Stack

| Layer | Choice |
| --- | --- |
| Backend | Python 3.11, `uv`, FastAPI, Pydantic v2, SQLite (stdlib `sqlite3` or SQLModel) for the ledger and run index |
| Vision / maths | OpenCV contrib (ArUco), NumPy, SciPy (least squares), `meta-sam-parser` (Meta's official SAM output parser, PyPI) |
| Simulation | PyBullet with `pybullet_data/franka_panda/panda.urdf` (OBJ visual meshes included) |
| Model clients | `openai` SDK (Meta Responses and Chat Completions, Baseten, Modal are all OpenAI-compatible); `httpx` for Voice Transcribe |
| Parallel and sandboxed execution | Modal Sandboxes for running untrusted generated programs plus PyBullet in parallel; a local `multiprocessing` sandbox as the fallback |
| Frontend | React 18, Vite, TypeScript, Tailwind v4, `three` plus `urdf-loader` for the 3D twin, Server-Sent Events for live runs |
| Media | `ffmpeg` / `ffprobe` |
| Deploy | One Docker image on a Hugging Face Space (port 7860), FastAPI serving the built frontend |
| No Streamlit | The organisers list Streamlit apps among projects to avoid |

## Repository layout

```
The_Demobot/
  CLAUDE.md  PROMPT.md  HUMAN_TASKS.md  PROGRESS.md  README.md  Makefile  pyproject.toml  .env.example
  .claude/settings.json            # permissions so the build needs few approvals
  docs/                            # this spec, decisions.md, probe-results.md (generated)
  backend/demobot/
    config.py  errors.py  logging.py  events.py  schemas.py  goal_dsl.py
    gateway.py  budget.py  providers.py        # all paid calls; ledger; caps; fallbacks; fixtures
    media.py  calibrate.py                     # ingest, probe, transcode, markers, metric plane
    watch.py  listen.py  perceive.py  ground.py # Spark 1.3, Voice, SAM 3.1, tracks to cm and events
    program/  api.py  sandbox.py  synth.py      # skill API exposed to programs; AST guard; Wonder loop
    verify.py  judge.py                        # symbolic, real-world and perceptual checks; Spark Open judge
    agents/  supervisor.py  redteam.py  tools.py
    sim/  scene.py  skills.py  render.py  layouts.py  twin_export.py  constants.py
    correct.py  card.py  export.py  library.py
    pipeline.py  jobs.py  api.py  cli.py
    prompts/*.md                               # versioned prompts (prompt_version in cache keys)
  backend/tests/ unit/ integration/ fixtures/{clips,responses,runs}
  frontend/ src/{pages,components,twin,replay,lib}
  synth/                                       # synthetic demo-clip generator (docs/09)
  eval/  run_eval.py  results.md (generated)
  scripts/ probe_models.py  calibrate_camera.py  bake_runs.py  record_demo.py
  assets/ print/ textures/                     # markers.pdf, checkerboard.pdf, Muse Image textures (committed)
  data/ clips/raw/ calibration/ runs/ cache/   # git-ignored: personal media, run outputs, model cache
  media/demo/                                  # demo video build outputs (git-ignored)
  reference/old_demobot/                       # first repo, read-only, git-ignored
```

## The run model: event-sourced and resumable

Every run lives in `data/runs/<run_id>/`:
- `input/`: the clip, optional `audio.wav`
- `artifacts/`: JSON and media per stage
- `events.jsonl`: append-only
- `state.json`: the stage cursor

Rules:
- **Stages are pure functions** of `(inputs, params, prompt_version)` plus cached model responses.
- **Restarts resume** from the last completed stage with zero new paid calls.
- **The UI renders only from events and artifacts.** Live mode streams `events.jsonl` over SSE. Replay mode re-streams a finished run with its original relative timing (speed 1×, 2× or 4×). Judge mode and the demo video are therefore identical to a real run and can never stall.
- `scripts/bake_runs.py` copies chosen runs into `backend/tests/fixtures/runs/` and the Docker image.

### Event schema (`events.py`)

```json
{"ts": "2026-11-01T10:00:00.123Z", "run_id": "a1b2c3", "seq": 42, "stage": "program",
 "type": "stage_start|stage_end|model_call|tool_call|artifact|decision|metric|log|error|question",
 "model": "muse-wonder-1.0", "provider": "meta|baseten|modal|local",
 "latency_ms": 8123, "tokens": {"in": 21000, "cached": 0, "out": 5200}, "cost_usd": 0.188,
 "cached": false, "payload": {}}
```

Every `model_call` carries model, provider, cost and whether it was a cache hit. The UI's model meter and the cost page sum these.

### Stages (details in `docs/04-pipeline.md`)

`ingest → calibrate → listen → watch (+ cross-watch) → perceive → ground → twin_build → program → verify → stress → harden → (supervise on any failure) → card → library`

Separate entry points:
- `correct`: voice or text correction applied to a finished run, which creates a new program version.
- `try_layout`: judge-supplied layout, simulation only, no paid calls.

## Core data contracts (`schemas.py`, Pydantic v2)

Units: table centimetres (cm) in the **table frame**; metres only inside PyBullet; seconds; US dollars.

The **table frame**:
- origin at the centre of marker 0;
- +x towards marker 1;
- +y towards marker 3, i.e. towards the robot and the camera side;
- z up.

Relations: `left_of` = −x, `right_of` = +x, `behind` = −y, `in_front_of` = +y.

- `Calibration`: image size, homography `H_img_to_table` (3×3), the four marker centres in cm, work-area rectangle, estimated focal length and camera pose (position in cm, look direction), method (`markers_bundle` or `markers_plus_intrinsics`), reprojection error in px.
- `Transcript`: text, language(s), segments `[{t0, t1, text}]`.
- `TaskSpec`: from Watch.
  - `summary`
  - `objects[]`: `name`, `kind`, `alt_names[]`, `role` (`moved|container|reference|distractor`), `color`, `est_height_cm`, `est_size_cm`
  - `steps[]`: `action` (`place_in|place_next_to|place_at`), `object`, `target`, `relation`, `t_start`, `t_end`, `evidence`
  - `goal`: a list of `GoalClause`
  - `generalization` (plain-language rule)
  - `uncertainties[]`
- `Track`: per object, frames `[{t, bbox_px, mask_rle?, centroid_px, score}]`, `track_id`, phrase used, quality.
- `GroundedDemo`: per-object initial and final positions and footprints in cm, motion segments, contact events (grasp and release times), step-to-segment matches with confidence, flags.
- `Layout`: objects with `x`, `y`, `yaw`, size, height, kind, texture reference, role. `source` is `demo|redteam:<persona>|random|user`.
- `Program`:
  - `version`, `parent_version`, `code` (Python source defining `run(scene, robot)`), `explanation`
  - `author` (`wonder|wonder-harden|wonder-correction`)
  - `diff_from_parent`, `synthesis_trace_id`
- `SimResult`:
  - `ok`, `error`
  - `skill_calls[]`
  - `final_state` (object poses)
  - `goal_results[]` (clause, holds, measured value)
  - `renders` (top-down and camera-pose PNG paths)
  - `twin_trajectory` path
  - `duration_s`
- `Verification`:
  - `symbolic`: goal on the simulated final state
  - `real_world`: goal on the human's real final state from SAM
  - `perceptual`: SAM run on the sim render, then the goal checked on that perceived state
  - `judge`: the Spark Open verdict
  - `agree` (bool), `failure_class`
- `AgentDecision`: `agent`, `step`, `observation`, `reasoning_summary` (one sentence, no chain of thought), `tool`, `args`, `result`, `cost`.
- `StressReport`: layouts with persona, before and after pass results, `robustness_before`, `robustness_after`, failure clusters.
- `SkillCard`: title, one-line description, image path (Muse Image), goal in words, program version, robustness, cost to learn.

## Goal DSL (`goal_dsl.py`)

The goal is declarative and quantified, so it generalises to new layouts and can be re-checked anywhere.

```json
[
  {"quant": "all",  "select": {"kind": "pen"},        "pred": "inside",   "target": {"name": "mug"}},
  {"quant": "the",  "select": {"name": "eraser"},     "pred": "left_of",  "target": {"name": "mug"}},
  {"quant": "all",  "select": {"role": "moved"},      "pred": "collinear", "order_by": "x"},
  {"quant": "pair", "select": {"names": ["stapler", "tape"]}, "pred": "swapped"}
]
```

- `quant`: `the` (exactly one), `all`, `pair`.
- `select`: by `name`, `kind`, `role`, or `names`.
- `pred`: `inside`, `left_of`, `right_of`, `in_front_of`, `behind`, `near` (needs `point_cm` or `target`), `collinear` (needs `order_by` or `order`), `swapped`.

Tolerances (ported from the first repo and proven there):
- `inside`: the centre lies within the container footprint shrunk by 1 cm per side. In sim, also require `z < container_height + 2`.
- `relation`: a gap between −1 and 8 cm, with lateral offset ≤ 3 cm + half the larger depth.
- `near`: ≤ 4 cm.
- `collinear`: PCA residual ≤ 2 cm and order equal to the list or its reverse.
- `swapped`: each object ≤ 4 cm from the other's initial position.

`evaluate(goal, state, initial_state) -> list[ClauseResult]` is shared by all verification paths. A clause whose selector matches nothing fails with `EMPTY_SELECTION`, unless the quantifier is `all` and the layout legitimately has none of that kind.

## The gateway (`gateway.py`, `providers.py`, `budget.py`)

Port this from the first repo. In summary:
- **Single choke point** for Meta, Baseten and Modal.
- **Cache:** every call is cached by the SHA-256 of its full request. The request includes provider, model, `prompt_version`, `schema_version`, input hashes and parameters. A repeated call costs $0 and logs a cache hit.
- **Ledger:** reserve, then settle. Each call reserves its estimated cost before it runs, and settles at the real cost afterwards. Calls that failed before billing are released. Timeouts settle at the estimate.
- **Caps:** per provider, per day, and per mode (`docs/03-models.md`).
- **Fallback chains** per purpose, e.g. supervisor: Baseten → Modal → Meta Spark 1.3. Every fallback is logged as an event.
- **Retries** with backoff on 429 and 5xx errors.
- **Validation** against Pydantic schemas, with one repair retry that sends the validation error back. Invalid output is billed but never cached.
- **`DEMOBOT_FIXTURES=1`** serves only recorded responses and raises `FIXTURE_MISSING` otherwise. Tests run in this mode.
- **Heartbeat:** while a call is in flight, a `log` event every 5 s keeps the UI alive.

## Modes

| Mode | Paid calls | Use |
| --- | --- | --- |
| `dev` | yes, dev caps | Building on the laptop |
| `replay` | none (no keys needed) | Plays baked runs; the interactive twin and `try_layout` still work (simulation is free) |
| `judge` | yes, judge daily cap | The HF Space: replay plus live runs on sample clips, uploads, and voice correction under the cap |

## HTTP API (`api.py`)

All responses are JSON unless noted. Errors are `{code, message, stage}`.

- `POST /api/runs`: multipart clip (+ optional `task_hint`) or `{"sample": "<id>"}`. Returns `run_id`.
- `GET /api/runs`: list runs. `GET /api/runs/{id}`: state plus artifact index.
- `GET /api/runs/{id}/events`: SSE; `?replay=1&speed=2` for replays.
- `GET /api/runs/{id}/artifacts/{path}`: files: video, overlay, renders, twin trajectory, program.
- `POST /api/runs/{id}/correct`: WAV upload or `{"text": ...}`. Starts a correction run.
- `POST /api/runs/{id}/try-layout`: `Layout` JSON. Simulation only; returns `SimResult` plus trajectory.
- `GET /api/skills`: the library. `GET /api/skills/{id}/export`: zip of the program, `TaskSpec`, goal, `card.png` and a README.
- `GET /api/costs`: per-model and per-provider spend, and the open-weight share.
- `GET /api/health`: mode, cap headroom, version.
