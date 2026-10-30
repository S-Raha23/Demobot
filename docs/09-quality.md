# 09. Quality: tests, fixtures, synthetic clips, evaluation and security

## Tests

- **Unit:** `backend/tests/unit/`
  - goal DSL and predicates: port the old edge cases (exactly on the shrunk border counts as inside; a −1 cm gap passes a relation; reverse order passes collinear; 2-object collinear always passes; swapped with identical starts is rejected);
  - homography bundle fit;
  - parallax correction;
  - grounding segments;
  - SAM parser on recorded outputs;
  - sandbox guard (15 malicious snippets rejected, 20 valid programs accepted);
  - gateway cache, caps and fallbacks;
  - event schema.
- **Integration:** `backend/tests/integration/`
  - simulation skill programs on random layouts;
  - the full pipeline on fixture runs (`DEMOBOT_FIXTURES=1`, recorded model responses), giving identical artifacts.
- **Frontend:** Vitest for the replay engine and the timeline sync maths. Playwright smoke test: Home, then a replay to the end, then Try-it run, with screenshots saved to `frontend/test-results/`. Claude looks at these screenshots and fixes any visual problems.
- **`make check`** = ruff, mypy (backend), tsc, offline pytest, Vitest, plus a secret scan (`gitleaks` if installed, otherwise a regex scan for `sk-`, `wk-`, `Bearer`, and the key variable names with values).
- **Recording fixtures:** `demobot fixtures <run_id>` copies a run's cached model responses into `backend/tests/fixtures/responses/`. Record one fixture run per task family as soon as M6 works.

## Synthetic demo generator (`synth/`), to be built early (M3)

Purpose: build and test the whole pipeline before, or without, the human's clips, with **exact ground truth**.

- A PyBullet scene with:
  - a table textured with the 4 printed ArUco markers at random rectangle positions (55–65 × 35–45 cm, slightly rotated), the same dictionary, IDs and 6 cm size;
  - a wood or desk-like background colour.
- Objects: 2–6 per clip, sampled from the desk-item set (mug, bowl, pen, marker, eraser, glue stick, sticky-note pad, coin, matchbox).
  - Textures come from **Muse Image** top-down product shots: generated once and saved in `assets/textures/` (committed; they were created during the event).
  - Offline fallback: flat colours.
- The hand: a skin-toned capsule plus a box "palm" that moves along a scripted pick-and-place arc (approach, descend, attach the object, lift, carry, place, release, retreat), with realistic timing of 2–4 s per move.
- The camera: random phone-like pose, 0–45° from vertical, from the robot side, 1280 × 720 at 30 fps, with mild noise and JPEG artefacts.
- Task families: `place_in`, `place_next_to`, `line_up`, `sort_by_kind`, `swap`.
- Output: `clip.mp4` plus `truth.json` (object poses per frame, step times, the goal).
- `synth/make_set.py --n 10 --seed 7` builds the eval set.

## Evaluation (`eval/run_eval.py` → `eval/results.md`)

Run all of this on the real clips (labels written by Claude from keyframes, stored in `eval/labels/`) and on the synthetic set (exact truth).

| Metric | Definition |
| --- | --- |
| Goal accuracy (Watch) | Fraction of clips whose final TaskSpec goal is equivalent to the label |
| Cross-model agreement | Spark 1.3 vs Spark Open step agreement before arbitration |
| Tracking quality | Mean track quality; fraction of frames with a box |
| Grounding error | Synthetic: median and p90 error of start and end positions (cm). Real: real-world check pass rate |
| Program success | Demo-layout pass rate after the coder loop; mean tool turns; mean cost |
| Verification agreement | Symbolic vs perceptual vs judge agreement rate |
| Robustness | Red-team pass rate before and after hardening (mean over skills) |
| Correction success | Corrections applied and verified |
| Cost per skill | Mean $ from the ledger per learned skill, split by model and provider; open-weight share of calls |
| Time per skill | Wall-clock from upload to verified skill |
| Best-of-N | Which drafts won (Wonder vs Spark Open) |

Every number in the README and the video must be copied from `results.md`. The file records the date and the git SHA.

## Security and safety

- Generated code runs only through the AST guard plus the sandbox (`docs/05-agents.md`).
- Uploads: type, size and duration checks; files stored under a random run ID; nothing executable is ever served from uploads.
- Judge mode: per-IP rate limits, daily caps, no way to change caps from the UI, and keys only in Space secrets.
- Privacy: track hands only; never identify people. Clips stay on the server running the app and are deleted when a judge-mode upload run completes, except for derived artifacts.
- Logs never include request headers or keys.
