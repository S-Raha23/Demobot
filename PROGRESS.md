PROJECT_STATUS: BLOCKED_ON_HUMAN

# PROGRESS

Single source of truth for status. Update it in the same commit that finishes a milestone. All times are IST.

**Now:** frontier phase (docs/11): Gate 0, then Fix 0 → F1 → F2 → F3 → video/README v2
**Freeze:** Wed Nov 4, 14:00 IST · **Submit target:** Wed Nov 4, 22:00 IST · **Hard deadline:** Thu Nov 5, 07:30 IST

## Milestones

| # | Milestone | Status | Done at | Acceptance result / notes |
| --- | --- | --- | --- | --- |
| M0 | Bootstrap and probes | done (push pending: the human creates the GitHub repo) | Sat 05:05 | `make check` green (41 tests). Every PROBE item answered (`docs/probe-results.md`). Full probe re-run cost $0.00. |
| M1 | Calibration | done (live: 5/5 real clips, 0.45–1.06 px, fixed marker layout) | Sat 06:50 | **Handheld** (spec change): joint bundle fit + per-frame homographies, smoothing with a no-lag guard, interpolation (+ similarity correction from 1–2 visible markers), blur flags, last-clean-frame reference, stabilised display. 10/10 synthetic handheld clips: marker error 0.23–0.42 cm (< 0.8), reprojection ≤ 0.51 px (< 1.5), per-frame p95 ≤ 0.72 cm (`eval/calibration_synth.py`). **Live:** `demobot calibrate data/clips/raw/01_pens_in_mug.mp4` when clips arrive. |
| M2 | Simulation core and skill API | done | Sat 07:20 | 20 hand-written programs (4 × 5 families) pass on 3 random layouts each (60/60, 34 s). The guard rejects 20 malicious snippets. Twin trajectory validates against `TwinTrajectory`. Renders: top-down and camera-pose. 117 tests. |
| M3 | Synthetic demo generator | done | Sat 07:30 | `synth/`: the human's real objects (white box, mug, teal pens, teal box cutter, glue bottle, tennis ball, steel spoon), Muse Image textures, a skin-toned hand with fingers, handheld shake, landscape 1280×720. 10 clips × 5 families with exact truth in `data/synth/set7` (`python -m synth.make_set --n 10 --seed 7`). 3 fixture runs baked for the UI. |
| M4 | Listen + Watch + cross-watch | done (live: goal 5/5 on real clips; Hindi narration transcribed) | Sat 08:40 | Spark 1.3 watch + Spark Open @ Modal cross-watch (video) + Wonder arbitration (decision events). Synthetic set: **goal correct on 9/10** (misses: a line-up with 3–7 cm nudges); cross-watch agreement mostly 1.0 once objects are aligned through step timing. `eval/understanding_synth.py`. Live: run on the 5 real clips, label them in `eval/labels/`. Listen: parser + language detection tested; `turns[]` timestamps still unconfirmed (no speech yet). |
| M5 | Perceive + Ground | done (live: tracking 0.98 on real clips) | Sat 10:40 | Synthetic set: **median start error 0.60 cm, end error 0.47 cm** (< 2 cm). Weakness: SAM misses some featureless synthetic teal bars (real goal holds on 5/10); kind and "<colour> object" fallback phrases added. `eval/grounding_synth.py`. |
| M6 | Coder (Wonder) + MVP gate | done (live: 5/5 real clips end to end) | Sat 13:20 | Stateless Wonder tool loop + 2 Spark Open drafts works live (syn7-00: submitted v2 in 3 turns, ~$0.10). Restart of the program stage = $0 new spend (verified). Live ≥ 4/5 needs real clips; run on more synthetic clips next. |
| M7 | Verify (three ways + judge) | done | Sat 12:20 | Fault injection on syn7-01: **5/5 faults caught, 4/5 with the exact class** (the sim-only offset was caught by the judge, not by perceptual, because SAM did not see that stand-in). SAM on simulated stand-ins is unreliable, so an unseen stand-in is *inconclusive* (shown grey), never a silent pass or a false failure. `eval/fault_injection.py`. |
| M8 | Supervisor agent | done | Sat 13:10 | Spark Open (Baseten → Modal → fixed policy) with rewatch, retrack, revise_spec, reprogram, ask_user, accept, stop; ≤ 4 decisions, each a decision event. **Recovered 4/5 injected failures** (judge dissent → rewatch + accept with caveat; program bug → reprogram; wrong relation and wrong object → rewatch + revise_spec; a lost track was not recovered). `eval/supervisor_injection.py`. `adjust_skill` is not offered (skill parameters are not plumbed in this build). |
| M9 | Red team + hardening | done | Sat 12:05 | 6 Spark Open personas in parallel (Baseten, Modal fallback), validator with one repair round, 12 layouts simulated in parallel on the local pool, Wonder hardening (≤ 2 rounds, kept only if the demo passes and robustness does not drop). 3 synthetic skills: next-to **92% → 100%** (v1 → v4), swap **92% → 100%** (v1 → v2), pens-in-mug 100% (no hardening needed). Gateway now stops after 2 cut-short answers. |
| M10 | Voice correction | done (live: Hindi and English voice notes, 3/3 corrections) | Sat 12:40 | `correct.py` + Wonder correction mode with an `update_goal` tool (goal diff + English gloss) → new program → re-checked on demo + red-team. Live: a typed and a **spoken English** correction flipped `left_of`↔`right_of` on syn7-01 (v4 → v6 → v7, red-team 12/12 each). espeak-ng Hindi/Bengali speech is too robotic for STT, so that check needs `correction_bn.m4a` from the human. Voice Transcribe returns `turns: []` even with speech (one segment is used). |
| M11 | Frontend | doing | | Core done: all pages, replay engine, twin with URDF, overlays, synced timeline, Try-it; 19 Vitest tests pass. Backend endpoints (samples, POST /runs, /correct, /eval, markers.pdf) are live in `backend/demobot/api.py`. Done this session: 1366 px stepper (`min-w-[84px]` below 1400 px, `chromium-1366` Playwright project, `frontend/e2e/acceptance.spec.ts` for Home/run/Costs + Try-it per skill) and a `lighthouse` npm script. Still open (environment-blocked here, run locally): Playwright browser launch times out in the sandbox and Lighthouse/Chrome cannot start there — commands in HUMAN_TASKS. |
| M12 | Skill cards, library and export | done | Sat 13:00 | Muse Image anchored-edit cards (template fallback), imperative titles/steps from the goal, `costs.json` per run from its own events (syn7-01: $1.68 to learn, 51% of spend on open weights), export zip (`/api/skills/{id}/export`), `docs/skill_api.md`. |
| M13 | Deploy judge mode | done (https://soubhagyaraha24--demobot.modal.run; checked health, replays, Try-it) | | Hugging Face needs PRO ($9/mo) for Docker Spaces, so the target is a Modal ASGI endpoint (`deploy/modal_app.py`, ledger on a Modal Volume so caps survive restarts; `scripts/deploy_modal.py`). Dockerfile kept for portability. Judge mode: 429 when a provider's judge-daily headroom < $1; 2 uploads per visitor per day; 3 synthetic sample clips + 3 baked real runs. The auto-mode classifier refuses production deploys by Claude. |
| M14 | Eval, README, demo video | done (video re-recorded on real-03) | | Synthetic eval in `eval/results.md`; README with numbers copied by `scripts/update_readme.py`; `scripts/record_demo.py` makes a 3:00 and a 30 s cut from the replay UI; `docs/submission-form.md`; history secret scan clean. |
| S1–S3 | Stretch goals | — | | |

### Frontier phase (docs/11-frontier.md, added Sat Oct 31 23:00 IST)

| # | Milestone | Status | Latest (IST) | Done at | Acceptance test |
| --- | --- | --- | --- | --- | --- |
| G0 | Gate 0: baseline Definition of Done holds, tag `v1-submittable` | done | before any feature | Sat 23:45 | Deployed site, README, `eval/results.md`, demo video v1, repo public, no secrets; tag pushed. |
| F0 | Fix 0: the 17 live-site bugs | doing | before F1 | | Playwright over Home, one run page, Try-it for every skill, Costs; screenshots reviewed; all 17 items checked off below; affected runs rebaked; redeployed. |
| F1 | Skill Forge (`FRONTIER_FORGE`) | todo | Sun Nov 1, 20:00 | | Synthetic: forges `push` and `rotate`, each ≥ 9/10 on fresh seeds, regression gate green. Real (when 06_push_box arrives): final program uses a forged skill, all checks pass, Toolkit shows it. |
| F2 | Live Twin on open-weight SAM 3.1, Modal GPU (`FRONTIER_LIVE`) | todo | Mon Nov 2, 16:00 | | Live replay of clip_01: twin ≥ 2 Hz, median position error < 2.5 cm vs offline, "Run it now" completes. Human 5-min phone test. GPU spend ≤ $30. |
| F3 | "Did you mean…?" (`FRONTIER_ASK`) | todo | Mon Nov 2, 23:00 | | On clip_02 or synthetic pens: ≥ 2 consistent hypotheses, a separating probe layout, cards render; "teal things" vs "pens" give different verified goals and programs; replay baked for judge mode. |
| V2 | Video + README v2 | todo | Tue Nov 3, 18:00 | | Video ≤ 3:00 with Forge, Live, Did-you-mean moments; 30 s cut; README "Frontier features" with measured numbers and limitations. |

**Fix 0 checklist** (docs/11, in order): 1 cutter tracked as pen · 2 Try-it wrong skill · 3 run header · 4 object registry names · 5 synthetic labels + real sample · 6 "Your turn" badge · 7 robot framing hero/top-down · 8 stand-in shapes + textures · 9 overlapping layouts · 10 label clutter · 11 red-team token cost · 12 judge latency · 13 build ledger box · 14 eval SHA · 15 open-weight labels · 16 "simulated prices" · 17 card aria-labels.

**Frontier Definition of Done:** G0 tag pushed; F0 all 17 checked; F1–F3 acceptance tests pass (or their cut rules applied and recorded); each feature behind its flag and on in judge mode only after its acceptance test; GPU spend ≤ $30; video v2 and README v2 done; `make check` green; deployed; `v1-submittable` still intact.

Status values: `todo` → `doing` → `done`, or `blocked: <reason>`.

## Budget log (update after any live batch; reconcile with dashboards daily)

| Sat Oct 31 16:30 IST | all | 10 synthetic runs end to end (incl. re-runs) | — | Meta $9.89, Baseten $4.31, Modal $0.61 spent; caps left: Meta $120, Baseten $86, Modal $109 | not yet |

**Estimate before batch (Sun Nov 1 02:00 IST), F1 forge:** forge `push` and `rotate_in_place` on synthetic layouts, ≤ 10 Wonder turns each at ~$0.3 ≈ **≤ $6** (Meta). Simulation is local and free.

**Estimate before batch (Sun Nov 1 00:30 IST), Fix 0 rebake:** 5 real clips from scratch with the registry check and the cheaper red team/judge (Watch and SAM mostly cached): ~$1.0 per clip + 2 voice corrections ~$0.5 each ≈ **$6 total** (Meta ~$3.5, Baseten ~$2, Modal ~$0.5). Red team before the fix: ~$0.95 per round (≈21 calls, ≈210k output tokens); judge 41.8 s.

**Estimate before batch (Sat Oct 31 18:30 IST):** 5 real clips end to end (ingest → card): ~$1.5 per clip (synthetic mean $1.48) ≈ **$7.50 total** (Meta ~$4.50, Baseten ~$2.70, Modal ~$0.30). Pools after: Meta ~$14 of $130, Baseten ~$7 of $90, Modal ~$1 of $110.

**Estimate before batch (Sat Oct 31 14:20 IST):** finish 7 synthetic runs (program → verify → stress → harden → card) for the eval: ~$0.40 Wonder + ~$0.30 Spark Open + ~$0.05 SAM/judge + ~$0.01 card ≈ **$0.80 per run, ~$5.60 total** (Meta ~$3.50, Baseten ~$1.80, Modal ~$0.30). Pools after: Meta ~$9 of $130, Baseten ~$3 of $90, Modal ~$0.6 of $110.


| Date (IST) | Pool | What | $ this batch | Pool total | Dashboard check |
| --- | --- | --- | --- | --- | --- |
| Sat Oct 31 05:00 | Meta ($130 cap) | M0 probes (Spark, Wonder, SAM, Voice, Image) | 0.057 | 0.057 | not yet |
| Sat Oct 31 06:35 | Meta ($130 cap) | 8 Muse Image textures | 0.08 | 0.137 | not yet |
| Sat Oct 31 08:40 | Meta ($130 cap) | M4 watch + arbitration on 10 synthetic clips (+2 reruns) | 0.61 | 0.75 | not yet |
| Sat Oct 31 08:40 | Modal ($110 cap) | M4 cross-watch on 12 clips | 0.16 | 0.18 | not yet |
| Sat Oct 31 13:10 | Meta ($130 cap) | M5–M8 on synthetic (SAM, Wonder, verify, supervisor) | ~3.3 | ~4.1 | not yet |
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

**Stopped by the human on Sun Nov 1 (about 02:30 IST) mid-F1.** The baseline (`v1-submittable`, commit `1cb448e`) is untouched and complete. Everything below is on `main` after it, `make check` green (166 backend + 19 frontend tests).

### Done since v1-submittable (docs/11)
- **Gate 0:** done. Tag `v1-submittable` pushed. `eval/results.md` now carries the git SHA.
- **Fix 0 (17 items), code done, rebake only partly done:**
  1 object registry + crop check (`registry.py`, `table_registry.json`; teal cutter no longer a third pen) · 2/3 skill versions (`versions.py`, `skills.json`, `/api/skills`, `/api/runs/{id}/skill`, Try-it and run header use one record; migration script) · 4 canonical names · 5 real/synthetic badges, real-first library, sample source/cached fields · 6 truthful "Your turn" badge · 7 robot framed in the hero, hidden/ringed in top-down edit · 8 registry shapes + real top-down crops as textures · 9 layout repaired once at twin_build · 10 label focus + collision avoidance (twin and overlay) · 11 compact red-team JSON, low effort, 4000 tokens · 12 judge low effort, 1800 tokens (the 15 s target is not measured yet) · 13 ledger snapshot `eval/ledger_snapshot.json` · 14 eval SHA · 15/16 costs-page labels · 17 aria-labels.
  - **Not done for Fix 0:** the Playwright acceptance run over Home, a run page, Try-it for every skill and Costs; the red-team cost before/after number; the judge latency measurement; re-measuring "perceptual inconclusive" with textures; baking the rebuilt runs. `data/runs/real-01..05` are rebuilt with the new code (old ones in the scratchpad `old_runs/pre_f0`); **`backend/tests/fixtures/runs/real-*` (what the site shows) are still the pre-Fix-0 bakes.** Next: `uv run python scripts/bake_runs.py real-01:real-ball-in-tub real-02:real-pens-in-tub real-03:real-spoon-in-tub real-04:real-pens-right-of-tub real-05:real-swap-cutter-glue`, re-label their `note`, then rerun `scripts/migrate_skill_versions.py` if needed, `uv run python -m eval.run_eval`, `update_readme.py`.
  - Known: tub objects were not marked hollow in old runs; fixed in code (`ground.py`) and patched in `data/runs/real-04/05` (twin_scene, stress layouts). real-04 correction re-run gives a combined goal (pens right of tub and ball in tub), red-team 7/7. real-02/03 corrections were not re-run after the rebuild.
- **F1 Skill Forge (flag `FRONTIER_FORGE`, on in dev, off in judge until accepted via `JUDGE_ACCEPTED` in `config.py`):**
  - Forge tier in the sandbox (`ee_pose`, `move_ee`, `grip`, `wait`, `scene.pose/in_contact/gripper_width_max`), `TooWide` for objects wider than the 8 cm gripper, `turned` goal predicate, `other_motion` step, goal completion with measured end position/yaw, `request_new_skill` coder tool, `program/forge.py` (Wonder loop with write_skill/write_tests/run_tests/inspect_physics/promote, 9/10 fresh seeds, regression gate), Forge tab, Toolkit section, `/api/toolkit`, synthetic `push` and `rotate` clip families (`data/synth/frontier/`), `eval/forge_synth.py`.
  - **Result:** `rotate_in_place` **promoted, 10/10 on fresh layouts, regression gate green over 100 library runs, 7 turns** (`backend/demobot/skills/forged/`). **`push` not promoted:** best 50% (about $0.4 per 10-turn attempt, five attempts, ~$2 in total). Physics works (a hand-written open-gripper push at yaw 0 passes 6 of the 8 layouts where it ran; fingers across the push direction, yaw 90 for pushes along y); failures were collisions with neighbours and tests that skip almost everywhere. My last test (a clear-path check) skipped on all 10 layouts because its clearance margins were too strict: loosen them, then give Wonder the lesson in `PHYSICS_NOTES`, and retry.
  - Not done: forge from a Watch `other_motion` demo (trigger 1), real clips 06/07 (not filmed), the Forge acceptance on a real clip, wiring `request_new_skill` end to end on a synthetic push clip, `JUDGE_ACCEPTED` flag flip.
- **F2 Live Twin, F3 "Did you mean…?", Video + README v2:** not started.

### Next steps, in order
1. Finish `push` (see above), run `uv run python -m eval.forge_synth`, then an end-to-end run of `data/synth/frontier/push_11001/clip.mp4`; add `"forge"` to `JUDGE_ACCEPTED` only after the acceptance passes.
2. Finish Fix 0 (bake, Playwright acceptance, measurements), commit, redeploy (`uv run python scripts/deploy_modal.py`).
3. F2 (Modal GPU, $30 sub-cap), F3, video and README v2, per docs/11 and its cut rules.
4. Latest times in docs/11: F1 Sun Nov 1 20:00, F2 Mon Nov 2 16:00, F3 Mon Nov 2 23:00, video/README Tue Nov 3 18:00, freeze Wed Nov 4 14:00 IST.

### Budget
About $41 spent by Oct 31 evening; since then roughly $10 more (rebake, corrections, forge attempts). Caps untouched; Modal GPU not used yet.

## Session update (finish-remaining pass)

**Verified:** `make check` green (ruff + mypy + **181 backend** + **19 frontend** tests, secret scan clean; baseline was 166 backend).

- **F1 code (done, free):** `request_new_skill` now takes `target` and threads it into `ForgeRequest` (so `sparse()` sparsifies coder-triggered forges); push test layouts are corridor-filtered (`push_corridor_clear`/`layout_has_push_corridor` in `forge.py`) and `PHYSICS_NOTES` teaches the swept-corridor rule. Regression tests: `backend/tests/unit/test_forge.py`.
- **Bug fixed:** `goal_dsl` wrongly rejected `turned` clauses without a target (`INVALID_CLAUSE`), which `ground.fill_goal` emits; now evaluated against `yaw_deg`/`point_cm` (`test_turned_needs_no_target`).
- **F1 run (paid, ~$0.25):** `eval.forge_synth push` → **not promoted, 10%** (was 50%). Free local probe shows the forged tests hit the sandbox 20 s CPU limit ("used too much CPU or memory"), so this reads as environment-limited, not a physics result. `JUDGE_ACCEPTED` stays empty (correct). Do not re-run paid forges in this sandbox; re-run on the human's machine.
- **Fix 0 (done):** fixtures rebaked (`scripts/bake_runs.py real-01..05`), `eval.run_eval` + `update_readme.py` regenerated. Measured from recorded `model_call` events: judge median **12.7 s** (p90 14.5 s, target < 15 s ✓); red-team 209 calls / $5.50 total (≈ $0.55/round vs ~$0.95 before ✓). Perceptual re-measure needs fresh paid runs — still open.
- **F3 (core done):** deterministic `backend/demobot/goal_solver.py` (`solve`, `consistent`, `choose_probe`, `separating_pairs`) + `test_goal_solver.py`. Selector has no colour field, so hypotheses vary name/kind/role only. Wonder/Image/UI/paid acceptance still open.
- **F2 (core done):** `backend/demobot/live.py` `LiveTracker` (3-frame confirmation, smoothing, gate, ≥2 Hz check) + `test_live.py`. Modal GPU app, `/live` routes, phone test still open (human/GPU).
- **Remaining human-only:** film 06/07, SAM HF licence click if asked, 5-min phone test, local Playwright/Lighthouse runs, production redeploy, YouTube/submission/X. See HUMAN_TASKS "Waiting on you".

## Judge panel (Meta Hackathon 2026 simulation)

**Round 1 scores:** UI/UX **6/10** · Functionality **7/10** · Details **6/10** · Meta-story **7/10** (avg 6.5). Full issue lists were returned by four judge agents; the fixable ones are being fixed by developer agents below, then re-judged. Human-only blockers (video/X links, hardware run, dashboard reconciliation) stay in HUMAN_TASKS and cap the Details score until done.

Round-1 top issues → fix status (developer agents, verified by `make check`: **185 backend + 19 frontend**):
- [x] verify inconclusive is now a distinct non-pass state routed to the supervisor (`verify.classify`, `FIXED_POLICY["inconclusive"]="retrack"`) · 2-object `collinear` needs spacing ≤ 10 cm · unattended `ask_user` no longer burns a decision · red-team emits delivered/requested metric. (`fill_goal` self-scoring and stale-`final_masks` retrack noted, not changed — they need a design call on scoring semantics.)
- [x] Try-it ghost Panda hidden while editing · global `:focus-visible` ring + AA contrast tokens · markers.pdf download link (dialog + `NO_MARKERS` error) · "Export skill (.zip)" on skill cards · real 404 view. Pointer-only timeline/dragging remains (keyboard equivalents still open).
- [x] README: tagline scoped to pick-and-place, Frontier section added, Bengali claim scoped, eval regenerated at HEAD.

**Round 2 scores:** UI/UX **8/10** · Functionality **8.5/10** · Details **7/10** · Meta-story **8/10** (avg 7.9). Details fixes applied: submission-form tagline/Bengali scoped, README Listen row qualified, eval regenerated at the frozen code commit (`35715cd`; this docs commit follows it, so the SHA names the code the numbers measure, not the docs commit).

**Round 3 (Details): 8.5/10 — GOOD.** Final panel: UI/UX 8 · Functionality 8.5 · Details 8.5 · Meta-story 8 (**avg 8.25**). Judge cycle closed at a good score. Checkpoints you can return to: `1538bb6` (frontier work), `35715cd` (round-1 fixes), `dc1ef99` (submission scoping) — e.g. `git show`/`git switch --detach <hash>`; `v1-submittable` is untouched.

**Round 4 (perfection standard, requested by the human):** UI/UX 8 · Functionality 7.5 · Details 8.5 · Meta-story 7.5 (avg 7.9). Fixes applied and verified (`make check`: **195 backend + 19 frontend**): LiveTracker creates confirmed tracks from unseeded detections; `Selector.colour` makes "teal things" expressible; exported zips bundle used forged skills; retrack invalidates stale final masks; goal solver honours `order_by="y"`; filled goal clauses are marked `filled_from_measurement`; UI gained Bengali qualifiers, video pause/reduced-motion, Home error+Retry, dialog semantics, slider keyboard seek, tab semantics, social meta/skip-link, replay read-only answers, AA comment token. Deployed to Modal after this round (judge mode, health ok).

**Round 5:** UI/UX 8.5 · Functionality 8.0 · Details 8.5 · Story 7.0. Round-6 fixes verified (`make check`: **202 backend + 19 frontend**): LiveTracker expiry + teleport suppression, transitive forged export bundling, colour-selector consistency + prompt docs, persisted `filled_from_measurement` flag, plus UI keyboard/dialog/error/aria polish. Note: the Toolkit (with the promoted `rotate_in_place`) is already on the judge site's home page; what stays off in judge mode is invoking new forges/live/ask flows before their acceptance. Remaining deductions are human-blocked (Bengali clip, video re-record/upload, clips 06/07, hardware, paid rebakes).

**Final confirmation:** UI/UX **9.0** · Functionality **8.5** · Details **9.0** · Story **7.5** — **avg 8.5/10**, the highest reachable without the human tasks. Story is capped by frontier judge-visibility (new forge/live/ask flows stay off until their acceptances), the pre-frontier demo video, and no hardware run. The judge→developer cycle therefore stops here: every remaining deduction is human-blocked (see HUMAN_TASKS). Checkpoints: `0821514` (round 4), `bfd0f61` (round 6). Site redeployed at each checkpoint; both contributors credited (author + Muse Code co-author).
