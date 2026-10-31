PROJECT_STATUS: IN_PROGRESS

# PROGRESS

Single source of truth for status. Update it in the same commit that finishes a milestone. All times are IST.

**Now:** M7 Verify (fault-injection acceptance), then M8 supervisor. Frontend M11 core done (Sat 11:30 IST); its backend requests are listed below.
**Freeze:** Wed Nov 4, 14:00 IST · **Submit target:** Wed Nov 4, 22:00 IST · **Hard deadline:** Thu Nov 5, 07:30 IST

## Milestones

| # | Milestone | Status | Done at | Acceptance result / notes |
| --- | --- | --- | --- | --- |
| M0 | Bootstrap and probes | done (push pending: the human creates the GitHub repo) | Sat 05:05 | `make check` green (41 tests). Every PROBE item answered (`docs/probe-results.md`). Full probe re-run cost $0.00. |
| M1 | Calibration | done (live check waits for real clips) | Sat 06:50 | **Handheld** (spec change): joint bundle fit + per-frame homographies, smoothing with a no-lag guard, interpolation (+ similarity correction from 1–2 visible markers), blur flags, last-clean-frame reference, stabilised display. 10/10 synthetic handheld clips: marker error 0.23–0.42 cm (< 0.8), reprojection ≤ 0.51 px (< 1.5), per-frame p95 ≤ 0.72 cm (`eval/calibration_synth.py`). **Live:** `demobot calibrate data/clips/raw/01_pens_in_mug.mp4` when clips arrive. |
| M2 | Simulation core and skill API | done | Sat 07:20 | 20 hand-written programs (4 × 5 families) pass on 3 random layouts each (60/60, 34 s). The guard rejects 20 malicious snippets. Twin trajectory validates against `TwinTrajectory`. Renders: top-down and camera-pose. 117 tests. |
| M3 | Synthetic demo generator | done | Sat 07:30 | `synth/`: the human's real objects (white box, mug, teal pens, teal box cutter, glue bottle, tennis ball, steel spoon), Muse Image textures, a skin-toned hand with fingers, handheld shake, landscape 1280×720. 10 clips × 5 families with exact truth in `data/synth/set7` (`python -m synth.make_set --n 10 --seed 7`). 3 fixture runs baked for the UI. |
| M4 | Listen + Watch + cross-watch | done on synthetic (live check waits for real clips) | Sat 08:40 | Spark 1.3 watch + Spark Open @ Modal cross-watch (video) + Wonder arbitration (decision events). Synthetic set: **goal correct on 9/10** (misses: a line-up with 3–7 cm nudges); cross-watch agreement mostly 1.0 once objects are aligned through step timing. `eval/understanding_synth.py`. Live: run on the 5 real clips, label them in `eval/labels/`. Listen: parser + language detection tested; `turns[]` timestamps still unconfirmed (no speech yet). |
| M5 | Perceive + Ground | done on synthetic (live check waits for real clips) | Sat 10:40 | Synthetic set: **median start error 0.60 cm, end error 0.47 cm** (< 2 cm). Weakness: SAM misses some featureless synthetic teal bars (real goal holds on 5/10); kind and "<colour> object" fallback phrases added. `eval/grounding_synth.py`. |
| M6 | Coder (Wonder) + MVP gate | doing | | Stateless Wonder tool loop + 2 Spark Open drafts works live (syn7-00: submitted v2 in 3 turns, ~$0.10). Restart of the program stage = $0 new spend (verified). Live ≥ 4/5 needs real clips; run on more synthetic clips next. |
| M7 | Verify (three ways + judge) | doing | | symbolic + real-world + perceptual (SAM on the sim render composited onto an inpainted clean plate of the real table) + Spark Open judge. syn7-00: three checks pass; the judge dissents over an untracked distractor (goes to the supervisor). |
| M8 | Supervisor agent | todo | | |
| M9 | Red team + hardening | todo | | |
| M10 | Voice correction | todo | | |
| M11 | Frontend | doing | | Core done by the subagent (Sat 11:30): all pages, replay engine, twin with URDF, overlays, synced timeline, Try-it; 19 Vitest tests + Playwright smoke pass. Open: backend endpoints in `frontend/NEEDS_FROM_BACKEND.md` (samples, POST /runs, /correct, /eval, markers.pdf), Lighthouse, 1366 px stepper. Playwright in WSL needs `LD_LIBRARY_PATH=~/.local/pwlibs/root/usr/lib/x86_64-linux-gnu`; H.264 video needs Chrome for Testing (`PW_CHROME=~/.local/cft/chrome-linux64/chrome`). |
| M12 | Skill cards, library and export | todo | | |
| M13 | Deploy judge mode | todo | | |
| M14 | Eval, README, demo video | todo | | |
| S1–S3 | Stretch goals | — | | |

Status values: `todo` → `doing` → `done`, or `blocked: <reason>`.

## Budget log (update after any live batch; reconcile with dashboards daily)

| Date (IST) | Pool | What | $ this batch | Pool total | Dashboard check |
| --- | --- | --- | --- | --- | --- |
| Sat Oct 31 05:00 | Meta ($130 cap) | M0 probes (Spark, Wonder, SAM, Voice, Image) | 0.057 | 0.057 | not yet |
| Sat Oct 31 06:35 | Meta ($130 cap) | 8 Muse Image textures | 0.08 | 0.137 | not yet |
| Sat Oct 31 08:40 | Meta ($130 cap) | M4 watch + arbitration on 10 synthetic clips (+2 reruns) | 0.61 | 0.75 | not yet |
| Sat Oct 31 08:40 | Modal ($110 cap) | M4 cross-watch on 12 clips | 0.16 | 0.18 | not yet |
| Sat Oct 31 05:00 | Baseten ($90 cap) | M0 probes | 0.007 | 0.007 | not yet |
| Sat Oct 31 05:00 | Modal ($110 cap) | M0 probes (LLM) + Sandbox test | 0.02 | 0.02 | `modal billing summary`: $0.02 covered by credits, $0 billed |

## Probe results summary

Full detail in `docs/probe-results.md`. Everything in the docs/03 checklist works:
- Spark 1.3: video via `file_id`; `$defs` schemas accepted; `reasoning={"effort"}`; reasoning tokens count against `max_output_tokens`.
- Wonder: tool loop with `previous_response_id` + `function_call_output`; images in follow-ups; **video input works**.
- SAM 3.1: image and video (`input_video` + `file_id`); pixel boxes, `w/h` = frame size; `meta_sam_parser` decodes it; bill from `video_frames_processed`.
- Voice: `/asr/transcribe` works, `languageBias` accepted; `turns[]` timestamps still to confirm with real speech.
- Muse Image: `images.generate` / `images.edit` → base64 WebP; **no fast/no-search field exists** (10–24 s per image).
- Baseten and Modal Spark Open: json_schema (strict), images, tools all work; Modal also takes video. Modal LLM usage is covered by the hackathon credit.
- Modal Sandbox with pybullet: 12 s cold (image build), 1.7 s warm.

## Next steps: handoff note for the next session

1. M7: fault-injection acceptance (wrong target, wrong relation, missing step, wrong object, sim-only offset → correct failure class on ≥ 4/5), then mark done.
2. M8 supervisor (Spark Open on Baseten, bounded tool loop; handles judge_dissent, perception_gap, spec_mismatch, program_bug).
3. Run the full pipeline (to verify) on more synthetic clips; bake a real run (not a fixture) for the UI.
4. Backend endpoints for the UI: `GET /api/samples`, `POST /api/runs`, `POST /api/runs/{id}/correct`, `GET /api/eval`, serve `markers.pdf`, keep `status: running` in run.json during live runs.
5. When real clips arrive (by Sun Nov 1 evening): calibrate (M1 live), watch (M4 live), perceive+ground (M5 live), program (M6 live); label in `eval/labels/`.
