# DemoBot: show it once

**A robot learns a tabletop pick-and-place task from one phone video, using Meta's models.**

Film yourself doing a task once ("put the pens in the cup"). A team of agents built on Meta's models watches the video, measures every object in centimetres, writes a robot program, tests it on a simulated Franka Panda, checks the result with the same eyes that watched you, attacks its own program with hard layouts, hardens it, takes spoken corrections, and hands you a verified, robot-agnostic skill.

- **Live demo:** https://soubhagyaraha24--demobot.modal.run : replays of recorded runs, the free **Try it** page, and live runs on sample clips within a small daily budget.
- **3-minute video:** *(link added after upload)*
- Built for the **Meta Global AI Developer Hackathon** (Indie track, theme *Push the Frontier*), Oct 26 – Nov 4, 2026.

> **Build history.** This repository restarts DemoBot on Oct 31, 2026, porting tested modules (the model gateway, budget ledger, goal predicates, media checks, and the PyBullet scene and skills) from the author's first repository of the same event (Oct 27–30, 2026), which was later deleted. All code was written during the event. Built with Claude Code as the coding tool; all AI inside the product runs on Meta's models.

## What it does: six moments

1. **It watched me once.** SAM 3.1 masks with track IDs and motion trails on your video; a timeline of every step, grasp and release; narration as captions (English and Hindi verified live; Bengali is supported by the transcription model, live clip still to record).
2. **It wrote its own robot program.** Muse Wonder writes Python against a small skill API and debugs it with tool calls to the simulator: clauses go red, then green; every version has a diff.
3. **It checks itself with the same eyes.** The twin is rendered from your phone's pose; SAM 3.1 segments it the way it segmented your video. Symbolic, real-world and perceptual checks, plus an open-weight judge. (The perceptual check is advisory today: inconclusive on 4/5 real clips — see Limitations.)
4. **It attacks itself.** Six Muse Spark Open personas propose twelve hard layouts in parallel; Wonder hardens the program until it survives them.
5. **Talk to it.** "No, the pen goes to the left of the box": the correction becomes a goal diff and a code diff, and the robot complies.
6. **Your turn.** Drag objects in the 3D twin; the robot re-plans and does it, live and free.

## How Meta's models are used

| Capability | Meta model | Its job in DemoBot |
| --- | --- | --- |
| Watch | **Muse Spark 1.3** (video) | Turns the demo video and narration into a `TaskSpec`: objects, timed steps, a declarative goal, a generalisation rule. Answers the supervisor's targeted "rewatch" questions. |
| Listen | **Muse Voice Transcribe** | Narration and spoken corrections in English, Hindi and Bengali. |
| See | **SAM 3.1** (video and image) | Pixel-precise, identity-preserving tracks of every object and the hand; also segments the simulator's render to close the loop. |
| Program | **Muse Wonder** (agentic coding) | Writes and debugs the robot program with tools (simulate, inspect the demo, check reach, submit); hardens it; applies corrections as goal and code edits; arbitrates when two watchers disagree. |
| Supervise | **Muse Spark Open** (open weights, Baseten; Modal fallback) | Decides how to recover from a failed check, with tools (rewatch, retrack, revise the spec, reprogram, accept with a caveat). |
| Red team | **Muse Spark Open** swarm (Baseten, parallel) | Six adversarial personas propose hard but solvable layouts. |
| Judge | **Muse Spark Open** (images) | Compares your real final frame with the twin rendered from your camera's pose. |
| Second opinion | **Muse Spark Open on Modal** (video) | Watches the same clip independently; disagreement triggers Wonder's arbitration. |
| Illustrate | **Muse Image** | Skill cards (anchored edits of your final frame) and the synthetic test set's object textures. |

Every model call goes through one gateway that caches it, prices it, enforces per-provider caps and logs a `model_call` event (model, provider, latency, tokens, cost, cache hit). The UI shows these live, including the open-weight share.

## Architecture

```mermaid
flowchart LR
  V[Phone video] --> I[Ingest] --> C[Calibrate<br/>markers, handheld camera track]
  V --> L[Listen<br/>Muse Voice]
  C --> W[Watch<br/>Muse Spark 1.3 + Spark Open @ Modal<br/>Wonder arbitrates]
  L --> W
  W --> P[Perceive<br/>SAM 3.1] --> G[Ground<br/>cm, contacts, real final state]
  G --> T[Twin build] --> Pr[Program<br/>Muse Wonder + simulator<br/>Spark Open drafts]
  Pr --> Ve[Verify<br/>symbolic · real-world · perceptual SAM 3.1 · judge Spark Open]
  Ve -->|failure| Su[Supervisor<br/>Spark Open tools]
  Su --> Pr
  Ve --> S[Stress<br/>6 Spark Open personas] --> H[Harden<br/>Muse Wonder]
  H --> K[Card<br/>Muse Image] --> X[Skill: program.py + skill_api.md]
  K -.-> Co[Correct<br/>Voice + Wonder]
```

Runs are event-sourced (`data/runs/<id>/events.jsonl` plus artifacts), so every run replays exactly, restarts resume at $0, and the UI renders only from events.

## Results

<!-- results:start -->
Generated by `eval/run_eval.py` on Sat Oct 31 2026, 19:23 UTC at git `1538bb6`. Every number in the README and the video is copied from this file.

### Real clips (the human's desk, handheld phone)

5 clips; 5 finished end to end (ingest → card).

| Metric | Value | Definition |
| --- | --- | --- |
| Goal accuracy (Watch) | **5/5** | synthetic: the goal holds on the true final state and not the initial one; real: it matches the human's label (eval/labels/real.json) |
| Cross-model agreement | **100%** mean; 5/5 identical | Spark 1.3 vs Spark Open step agreement, before arbitration |
| Tracking quality | **0.97** mean; 100% of objects tracked | fraction of frames with a SAM box, per object |
| Real-world check | **4/5**; 1 inconclusive (start hidden by the hand) | the goal holds on the measured real final state |
| Program success | **5/5** pass the demo; 3.0 Wonder turns on average | after the coder loop (incl. the supervisor's reprogram) |
| Verification | **5/5** all checks agree; 5/5 accepted (incl. supervisor caveats); judge agrees on 5/5; perceptual inconclusive on 4/5 | symbolic, real-world, perceptual, judge |
| Robustness | **74% → 82%** (mean over 5 skills; improved on 1) | red-team pass rate before and after hardening |
| Correction success | **2/2** | corrections applied and verified on the demo |
| Cost per skill | **$0.67** mean (min $0.23, max $1.37) | spend of the run's own model calls (cache hits count $0) |
| Open-weight share of calls | **31%** of model calls | Muse Spark Open on Baseten and Modal (the costs page shows the share of spend) |
| Time per skill | **5.1 min** mean | sum of stage times from upload to the skill card |
| Best-of-N | Wonder 3, Spark Open draft 2 | whose program was submitted |

Spend by provider over these runs: baseten $0.95, meta $2.36, modal $0.02.

### Synthetic clips (exact ground truth)

10 clips; 10 finished end to end (ingest → card).

| Metric | Value | Definition |
| --- | --- | --- |
| Goal accuracy (Watch) | **9/10** | synthetic: the goal holds on the true final state and not the initial one; real: it matches the human's label (eval/labels/real.json) |
| Cross-model agreement | **85%** mean; 5/10 identical | Spark 1.3 vs Spark Open step agreement, before arbitration |
| Tracking quality | **0.80** mean; 90% of objects tracked | fraction of frames with a SAM box, per object |
| Grounding error | start **0.47 cm** (p90 1.47), end **0.46 cm** (p90 4.60) | moved objects vs exact synthetic truth |
| Real-world check | **9/10** | the goal holds on the measured real final state |
| Program success | **10/10** pass the demo; 4.2 Wonder turns on average | after the coder loop (incl. the supervisor's reprogram) |
| Verification | **5/10** all checks agree; 10/10 accepted (incl. supervisor caveats); judge agrees on 6/10; perceptual inconclusive on 5/10 | symbolic, real-world, perceptual, judge |
| Robustness | **89% → 95%** (mean over 10 skills; improved on 5) | red-team pass rate before and after hardening |
| Correction success | **2/2** | corrections applied and verified on the demo |
| Cost per skill | **$1.48** mean (min $0.79, max $2.47) | spend of the run's own model calls (cache hits count $0) |
| Open-weight share of calls | **39%** of model calls | Muse Spark Open on Baseten and Modal (the costs page shows the share of spend) |
| Time per skill | **9.4 min** mean | sum of stage times from upload to the skill card |
| Best-of-N | Wonder 8, Spark Open draft 2 | whose program was submitted |
| Calibration (handheld) | **10/10** pass; marker error ≤ 0.41 cm, reprojection ≤ 0.51 px | marker error < 0.8 cm and reprojection < 1.5 px |
| Fault injection (verify) | **5/5** caught; 4/5 with the exact class | 5 injected faults; the failure class verification assigns |
| Supervisor recovery | **4/5** | injected failures the supervisor recovered from |

Spend by provider over these runs: baseten $5.26, meta $8.85, modal $0.67.

Synthetic clips are rendered by `synth/` with the human's real objects and handheld shake; their model calls are real.
Costs include re-runs made while developing, except where cached (cache hits are $0).
<!-- results:end -->

## Run it yourself

```bash
uv sync && (cd frontend && npm ci --legacy-peer-deps && npx vite build)
DEMOBOT_MODE=replay uv run uvicorn demobot.api:app --app-dir backend --port 8000   # no keys needed
# open http://localhost:8000: replay the baked runs; Try it works (simulation is free)
```

With keys in `.env` (see `.env.example`): `make dev`, then upload a clip, or `uv run demobot run my_clip.mp4`. Print `assets/print/markers.pdf` and glue the four markers around your work area; film from the robot's side (handheld is fine).

## Frontier features (in progress, honestly labelled)

- **Skill Forge:** Wonder invents new robot skills from low-level primitives. `rotate_in_place` is promoted (10/10 fresh layouts, regression gate green over 100 library runs). `push` is not promoted yet (best 50% on the author's machine; sandbox re-runs are CPU-limited), so the Forge is on in dev mode only, not on the judge site.
- **Live Twin core:** detection-to-object tracking with 3-frame confirmation and smoothing (`backend/demobot/live.py`, unit-tested). The Modal GPU SAM app, `/live` pages and the phone test are not built yet.
- **"Did you mean…?" core:** a deterministic goal solver (`backend/demobot/goal_solver.py`, unit-tested) predicts each candidate goal's outcome and picks the layout that separates competing interpretations. The Wonder/Image question flow and UI are not built yet.

## Exported skills

Each learned skill exports as a zip: `program.py` (`run(scene, robot)`), `skill_api.md` (the contract: a `scene` that reports objects in table centimetres and a `robot` with six primitives), `goal.json`, `taskspec.json` and the card. Implement `skill_api.md` on any robot stack and the program runs there; check the result with `goal.json`.

## Limitations, stated honestly

- **Simulation only.** The robot is a simulated Franka Panda in PyBullet; no physical robot was used. The exported program is robot-agnostic, but it has not run on hardware.
- Rigid objects on a table; no stacking, deformables or force-controlled tools.
- The four printed markers must be visible; tall objects must not hide them.
- Heights come from the vision model's estimates, so parallax correction is approximate; objects inside containers are placed at the container.
- SAM can miss simple synthetic stand-ins in renders; the perceptual check then reports *inconclusive* instead of passing or failing.
- If your hand already covers an object when the clip starts, its starting position is never seen; a check that needs it (a swap) is reported *inconclusive* rather than passed.
- Cost per skill is real money (see Results); every call is cached, so replays and restarts are free.

## Related work and credits

- **SeeDo** (Wang et al., arXiv 2410.08792): learning robot plans from demonstration videos with vision-language models.
- **Code as Policies** (Liang et al., 2022): language models writing robot policy code.
- **SAM 3** (Meta), the **Meta Model API** documentation, **PyBullet**, and the **Franka Panda** URDF from `pybullet_data`.

## Licence

MIT
