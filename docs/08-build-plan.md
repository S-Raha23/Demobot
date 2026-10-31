# 08. Build plan: milestones, acceptance tests and schedule

**Time available:** from Sat Oct 31 morning (IST) to the Wed Nov 4, 2:00 PM IST freeze, about 100 hours of wall-clock time.

**Go as fast as possible.** The target column is the *latest acceptable* time, not a schedule. Never pause between milestones or at day boundaries: when one milestone passes, start the next immediately. Finishing everything a day or two early is the goal; use the spare time for polish and stretch goals.

**Work the milestones in order.** The frontend (M11) starts as a parallel subagent once M2 produces a fixture run.

Each acceptance test runs offline unless marked **(live)**. Live tests use the human's real clips, or synthetic clips if real ones have not arrived yet.

| # | Milestone | Key deliverables | Acceptance test | Est. | Latest (IST) |
| --- | --- | --- | --- | --- | --- |
| M0 | Bootstrap and probes | `pyproject` (uv), Makefile (`dev`, `check`, `test`, `costs`, `probe`), ruff + mypy + pytest, `.claude/settings.json`, `config.py`, `errors.py`, `events.py`, gateway/budget/providers **ported**, `scripts/probe_models.py`, `docs/probe-results.md`, public GitHub repo created and pushed | `make check` green. **(live)** The probe report answers every item in the docs/03 PROBE checklist (or marks it "failed: reason"). A repeated live call costs $0.00. | 3h | Sat 14:00 |
| M1 | Calibration | markers bundle fit, intrinsics from the checkerboard video (optional path), camera pose, rectification, `calibrate` CLI | On synthetic clips (M3 can come first if easier), marker positions err < 0.8 cm and plane reprojection < 1.5 px. **(live)** On a real clip, all 4 markers are found. | 3h | Sat 18:00 |
| M2 | Simulation core and skill API | port of scene and skills; the `api.py` contract; layouts plus validator; reach map; renders (top-down and camera-pose); twin export; sandbox guard plus executor | 20 hand-written programs (5 per task family) pass on 3 random layouts each. The guard rejects 15 malicious snippets. A twin trajectory validates against its schema. | 5h | Sat 23:00 |
| M3 | Synthetic demo generator | `synth/`: PyBullet scene with marker textures on the table, objects (Muse Image textures, or flat colours offline), a skin-coloured capsule "hand" doing scripted pick-and-place, an oblique phone camera, an MP4 plus ground-truth JSON | 10 synthetic clips across 5 task families, with ground truth. They feed M1, M5 and eval. | 3h | Sun 02:00 |
| M4 | Listen + Watch + cross-watch | `listen.py`, `watch.py`, prompts, semantic checks, the Modal cross-watch, Wonder arbitration | Fixture tests pass. **(live)** On 5 clips the goal is correct on ≥ 4. Claude labels the real clips by viewing keyframes and writes them to `eval/labels/*.json`. | 4h | Sun 09:00 |
| M5 | Perceive + Ground | SAM tracking (sequential), parser wrapper, alt-name retries, contacts, segments, real final state, crops, real-world check | Synthetic: median start and end error < 2 cm. **(live)** Real: the goal holds on the real final state for ≥ 4 of 5 clips. | 5h | Sun 15:00 |
| M6 | **Coder (Wonder) + MVP gate** | coder prompt, tools, loop, best-of-N with Spark Open drafts, `pipeline.py`, `jobs.py`, `cli.py run`, event log, resume | **(live)** `demobot run <clip>` on ≥ 4 of 5 clips produces a program passing the demo layout. Killing and restarting a run resumes with $0 new spend. **MVP gate:** a full replayable run exists. | 6h | Sun 23:00 |
| M7 | Verify (three ways + judge) | symbolic, real-world, perceptual (SAM on the camera-pose render), Spark Open judge, failure classes | Injecting 5 faults (wrong target, wrong relation, missing step, wrong object, sim-only offset) gives the correct failure class on ≥ 4. Correct runs pass. | 3h | Mon 05:00 |
| M8 | Supervisor agent | tools, bounded loop, the fixed-policy fallback, decision events | Recovers ≥ 3 of 5 injected failures. Every decision has an observation, tool, result and reason. | 3h | Mon 09:00 |
| M9 | Red team + hardening | 6 personas in parallel, validator, parallel sim (Modal Sandboxes or a local pool), clustering, the Wonder harden loop | **(live)** On ≥ 3 skills, robustness before and after is reported; on at least one, after > before. All layouts are valid. | 5h | Mon 16:00 |
| M10 | Voice correction | browser WAV capture; `correct.py`; goal patch; diffs | **(live)** A spoken English correction and one in Hindi or Bengali (the human records one 5 s phrase, or Claude uses the narration clip) change the program, and the robot complies. | 3h | Mon 20:00 |
| M11 | Frontend (parallel from M2) | all pages in docs/07, replay engine, the 3D twin with URDF, overlays, timeline sync, Try-it editor, costs, a polished visual style | A first-time user goes from Home to a finished replay to Try-it without help. Lighthouse performance ≥ 70 on desktop. Claude reviews screenshots from Playwright at 1920 × 1080. | 12h | Tue 12:00 |
| M12 | Skill cards, library and export | `card.py` (Muse Image), `library.py`, `export.py`, `skill_api.md` | Cards exist for all library skills. Export zips validate. | 2h | Tue 15:00 |
| M13 | Deploy judge mode | Dockerfile, HF Space creation via `huggingface_hub`, secrets set by script from `.env`, baked runs | The Space is healthy from a phone. Replay works with no key. A live sample run works within the caps. Try-it works. | 3h | Tue 21:00 |
| M14 | Eval, README, demo video | `eval/run_eval.py` → `results.md` (metrics in docs/09); README per docs/10; `record_demo.py` producing `demo_final.mp4`; X post draft | All numbers in the README and video come from `results.md`. The video is ≤ 3:00 and plays. Repo is public. A secret scan of the full history is clean. | 6h | Wed 12:00 |
| — | **Freeze** | bug fixes only | | | **Wed 14:00** |
| — | Submit buffer | the human submits; Claude prepares the form text | | | by Wed 22:00 |

## Stretch goals (start them as soon as M0–M14 are done, if there are at least 12 hours left before the freeze)

- **S1 Imagined result:** Muse Image edits the start render into the predicted end state before the robot runs. It is shown beside the sim result, labelled "imagined".
- **S2 Glimmer offline judge:** Muse Glimmer 30B served with vLLM on a Modal GPU as a fully open-weight judge, compared with Spark Open in eval.
- **S3 Skill composition:** chain two library skills ("tidy desk" = pens into the mug, then line up the rest).

## Cut list (if behind schedule, cut from the top first)

1. S1–S3
2. M10 Hindi/Bengali (keep English)
3. Best-of-N drafts in M6 (keep Wonder alone)
4. Cross-watch plus arbitration in M4 (keep Spark 1.3 alone; still report agreement on 3 clips offline)
5. Modal Sandboxes (keep the local pool)
6. The second hardening round in M9

**Never cut:**
- the end-to-end run;
- the three-way verification;
- the red-team grid with at least one before/after improvement;
- the 3D twin with timeline sync;
- replay and judge mode;
- Try-it;
- the demo video.

## Rhythm

- **Start of each session:** read PROGRESS.md, then check the ledger with `make costs`.
- **Every milestone:** commit, push, update PROGRESS.md.
- **Every ~6 hours of work:** bake one replayable run of the current best state (`scripts/bake_runs.py`) so a demo always exists.
- **Before ending a session:** write the handoff in PROGRESS.md.
