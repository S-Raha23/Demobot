PROJECT_STATUS: IN_PROGRESS

# PROGRESS

Single source of truth for status. Update it in the same commit that finishes a milestone. All times are IST.

**Now:** M1 Calibration (M0 done Sat Oct 31, 05:05 IST)
**Freeze:** Wed Nov 4, 14:00 IST · **Submit target:** Wed Nov 4, 22:00 IST · **Hard deadline:** Thu Nov 5, 07:30 IST

## Milestones

| # | Milestone | Status | Done at | Acceptance result / notes |
| --- | --- | --- | --- | --- |
| M0 | Bootstrap and probes | done | Sat 05:05 | `make check` green (41 tests). Every PROBE item answered (`docs/probe-results.md`). Full probe re-run cost $0.00. |
| M1 | Calibration | todo | | |
| M2 | Simulation core and skill API | todo | | |
| M3 | Synthetic demo generator | todo | | |
| M4 | Listen + Watch + cross-watch | todo | | |
| M5 | Perceive + Ground | todo | | |
| M6 | Coder (Wonder) + MVP gate | todo | | |
| M7 | Verify (three ways + judge) | todo | | |
| M8 | Supervisor agent | todo | | |
| M9 | Red team + hardening | todo | | |
| M10 | Voice correction | todo | | |
| M11 | Frontend | todo | | |
| M12 | Skill cards, library and export | todo | | |
| M13 | Deploy judge mode | todo | | |
| M14 | Eval, README, demo video | todo | | |
| S1–S3 | Stretch goals | — | | |

Status values: `todo` → `doing` → `done`, or `blocked: <reason>`.

## Budget log (update after any live batch; reconcile with dashboards daily)

| Date (IST) | Pool | What | $ this batch | Pool total | Dashboard check |
| --- | --- | --- | --- | --- | --- |
| Sat Oct 31 05:00 | Meta ($130 cap) | M0 probes (Spark, Wonder, SAM, Voice, Image) | 0.057 | 0.057 | not yet |
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

1. M1 Calibration: read `docs/04-pipeline.md` (calibrate section) and `docs/06-simulation.md`/`docs/09-quality.md` as needed. Build `backend/demobot/calibrate.py` + `media.py` (port `reference/old_demobot/backend/demobot/media.py`).
2. M1's acceptance is on synthetic clips, so M3's generator (or a minimal renderer of the marker table) may come first.
3. No real clips yet (`data/clips/raw/` empty): use synthetic clips.
