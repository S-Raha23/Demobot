# Run directory and event payloads (the UI ↔ backend contract)

Every run lives in `data/runs/<run_id>/` (baked runs: `backend/tests/fixtures/runs/<run_id>/`). The UI renders **only** from `events.jsonl` and the files below, served at `GET /api/runs/{id}/artifacts/{path}` (path relative to the run directory). Schemas are the Pydantic models in `backend/demobot/schemas.py`; the TypeScript types mirror them.

## Files

| Path | Schema / format | Written by |
| --- | --- | --- |
| `run.json` | `{run_id, title, created_at (ISO, UTC), source, mode, status, fixture, replay_of?}` | jobs |
| `state.json` | `{cursor, stages: {stage: "todo"\|"running"\|"done"\|"failed"\|"skipped"}}` | jobs |
| `events.jsonl` | one `Event` per line (`docs/02`) | every stage |
| `input/clip.<ext>` | the upload | api |
| `artifacts/ingest.json` | `IngestInfo` | ingest |
| `artifacts/display.mp4` | H.264, 30 fps, **stabilised** to the first frame's view, audio kept | calibrate |
| `artifacts/analysis.mp4` | 10 fps, unstabilised, no audio (what SAM and Spark see) | ingest |
| `artifacts/keyframes/kf_XX.jpg` | 8 frames | ingest |
| `artifacts/calibration.json` | `Calibration` (reference = last clean frame) | calibrate |
| `artifacts/camera_track.json` | `CameraTrack` (per analysis frame) | calibrate |
| `artifacts/stabilise.json` | `{"M": [3×3 per display frame]}` raw → stabilised pixels | calibrate |
| `artifacts/calibration_overlay.json` | `{markers: [{id, corners_px}], axes_px: {origin, x10cm, y10cm}, work_area_px}` in stabilised pixels | calibrate |
| `artifacts/rectified_first.png`, `rectified_last.png`, `reference_frame.jpg` | 10 px/cm top-down; the reference (last clean) frame | calibrate |
| `artifacts/transcript.json` | `Transcript` | listen |
| `artifacts/taskspec.json` | `TaskSpec` | watch |
| `artifacts/crosswatch.json` | `{spec: TaskSpec, agree: bool, differences: [str], arbitration?: str}` | watch |
| `artifacts/tracks.json` | `{fps, size: [w, h], tracks: [Track]}`; `poly_px` in **stabilised display** pixels | perceive |
| `artifacts/crops/<name>.png` | top-down object crops | perceive |
| `artifacts/grounded.json` | `GroundedDemo` | ground |
| `artifacts/twin_scene.json` | `{layout: Layout, markers: [MarkerPose], camera: CameraPose, image_size, table_texture: "rectified_first.png", reach: {x0, y0, step_cm, cells}}` | twin_build |
| `artifacts/programs/v<N>.py` | program source | program, harden, correct |
| `artifacts/programs.json` | `[Program]` (code inline too) | program, harden, correct |
| `artifacts/sim/<layout_id>_v<N>/result.json` | `SimResult` (paths inside are relative to the run dir) | program, verify, stress |
| `artifacts/sim/<layout_id>_v<N>/twin_<layout_id>.json` | `TwinTrajectory` (`sim/twin_export.py`) | same |
| `artifacts/sim/<layout_id>_v<N>/top_<layout_id>.png`, `camera_<layout_id>.png` | renders | same |
| `artifacts/verify.json` | `Verification` | verify |
| `artifacts/stress.json` | `StressReport` | stress, harden |
| `artifacts/card.png`, `artifacts/card.json` | `SkillCard` | card |
| `artifacts/costs.json` | `{by_model, by_provider, total_usd, open_weight_share}` | end of run |

## Stages, in order

`ingest → calibrate → listen → watch → perceive → ground → twin_build → program → verify → stress → harden → card` (+ `supervise` on any failure, + `correct` for a correction run).

## Event payloads by type

- `stage_start` / `stage_end`: `stage` is the stage name; `stage_end.payload = {ok, summary, duration_s}`.
- `model_call`: `model`, `provider`, `latency_ms`, `tokens {in, cached, out}`, `cost_usd`, `cached`, and `payload = {purpose, open_weight, frames?, images?, audio_s?, note?}`. `note: "incomplete"` marks a billed retry; `fixture: true` marks a simulated call in a fixture run.
- `log`: `payload.message`; or a heartbeat `{heartbeat: true, purpose, model, elapsed_s}`; or a retry `{retry, purpose, error}`; or a **fallback** `{fallback: true, purpose, from, to, code, message}` (the UI shows fallbacks visibly).
- `artifact`: `payload = {name, path, kind: "video"|"image"|"json"|"code"|"trajectory", label}`. The UI loads files only after their `artifact` event.
- `tool_call`: `payload = {agent, iteration, tool, args (short), result: {ok, error?, clauses_passed?, clauses_total?, layout?}}`.
- `decision`: `payload` = `AgentDecision`.
- `metric`: `payload = {name, value, unit?}`, e.g. `clauses_passed`, `robustness_before`, `robustness_after`, `crosswatch_agree`.
- `question`: `payload = {id, text, options: [str]}`.
- `error`: `payload = {code, message}`.

## Fixture runs

`scripts/make_fixture_run.py` builds runs from synthetic clips for UI development. Their model calls are **simulated** (`fixture: true` in `run.json` and on every `model_call`), the simulation is real. They are never presented as real results; real baked runs replace them in the Space and the video.
