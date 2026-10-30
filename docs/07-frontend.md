# 07. Frontend, replay, judge mode and deployment

## Design language

- **"Mission control":** a dark slate background, one accent colour per model, and calm motion.
- **Type:** Inter (UI) and JetBrains Mono (code and numbers).
- **Model badges, reused everywhere:**

  | Model | Colour |
  | --- | --- |
  | Spark 1.3 | blue |
  | Spark Open | teal |
  | SAM 3.1 | amber |
  | Wonder | violet |
  | Voice | pink |
  | Image | coral |

  Each badge shows the provider (Meta, Baseten, Modal) as a small suffix.
- **Every screen answers three questions at a glance:** what the AI is doing now, which model is doing it, and what it cost.
- **No dead air:**
  - a model call always shows a live timer;
  - long waits show the heartbeat text from events;
  - replays can run at 2× speed.
- The layout must look good at **1920 × 1080**, which the video is recorded at, and at laptop width. On phones, the twin and the timeline stack vertically.

## Pages

1. **Home / Library**
   - Hero: "Show it once." with a looping 6-second replay of the best run (real video crossfading to the twin).
   - A "Teach a new skill" button, plus three sample clips judges can run.
   - Skill cards from Muse Image, each showing robustness and cost-to-learn chips.
2. **Run: mission control** (the main page, used for live runs and replays)
   - **Top bar:** the stage stepper (`ingest → calibrate → listen → watch → perceive → ground → program → verify → stress → harden → card`), each stage lighting up with its model badge.
   - **Left: Real.** `display.mp4` with a canvas overlay:
     - SAM masks (semi-transparent, colour per track);
     - track IDs and object names;
     - 1.5 s motion trails;
     - a hand mask outline;
     - marker axes during Calibrate.

     Captions show the narration transcript.
   - **Right: Twin.** A three.js scene showing the table (with the rectified texture), the textured stand-ins and the Panda (`urdf-loader`).
     - Orbit controls.
     - A "Real camera view" toggle snaps the twin camera to the calibrated phone pose, so real and twin line up.
     - A reach-map overlay toggle.
   - **Shared timeline scrubber under both:**
     - human step segments, from Spark plus measured;
     - grasp and release diamonds, from SAM contacts;
     - robot skill-call segments.

     Scrubbing syncs the video and the twin step by step.
   - **Bottom-left: Agent feed.** Live events in a vertical feed:
     - model calls (badge, purpose, latency, cost, cached flag);
     - tool calls (`simulate → 3/4 clauses pass`);
     - decisions (supervisor, with its one-line reason);
     - questions (with answer buttons and a mic button).
   - **Bottom-right: tabs.**
     - **Spec:** the TaskSpec, rendered as human sentences plus the goal DSL chips.
     - **Program:** Monaco or a read-only code view, a version selector, diffs between versions, and synthesis iterations as a mini timeline.
     - **Verify:** the four checks as cards; real versus camera-pose render side by side, each with its SAM masks; the clause table.
     - **Stress:** the 4 × 3 red-team grid; robustness before and after; a hardening diff.
     - **Costs:** spend per model and provider, and the open-weight share donut.
   - **Correction dock:** a hold-to-talk mic button (records WAV in the browser) and a text box. While processing it shows the transcript, then the goal diff, then the code diff, then the re-verification.
3. **Try it (judge interactive)**
   - Load any library skill. The twin is in top-down edit mode: drag objects to move them, R to rotate.
   - A "Run" button POSTs to `/try-layout`. The robot executes the existing program in simulation (free) and the goal chips turn green or red.
   - "Shuffle" picks a valid random layout.
4. **Costs and about**
   - Total spend by model, cost per learned skill, the eval table from `eval/results.md`.
   - Credits to Meta's models; the "built during the hackathon" statement.

## Replay engine (`frontend/src/replay`)

- One code path renders both live SSE streams and replays: `events.jsonl` is played with its original relative timing scaled by speed.
- Artifacts (video, trajectory, renders) load on their `artifact` events.
- A "Skip to result" control jumps to the end state.
- In replay mode, show a small "Replay of a recorded run (Nov X, IST)" label for honesty.

## Judge mode and deployment (Hugging Face Space)

- **One Dockerfile:**
  - Python 3.11-slim plus ffmpeg;
  - the backend via `uv sync --frozen`;
  - a frontend build stage (Node 20) whose `dist` is copied and served by FastAPI;
  - the Panda assets copied from `pybullet_data`;
  - baked runs from `backend/tests/fixtures/runs/` plus the library.
- **Space:** Docker SDK, port 7860. Secrets go in the Space settings: `MODEL_API_KEY`, `BASETEN_API_KEY`, `MODAL_*`, `DEMOBOT_MODE=judge`.
  - Claude creates the Space with `huggingface_hub` using `HF_TOKEN` from `.env`.
  - The human only creates the token.
- **Judge caps** are in `docs/03-models.md`. When a cap is reached, live features show "Live budget for today is used. Enjoy the recorded runs and the free Try-it page."
  - Try-it is always available because it is free.
  - Uploads are limited to 2 per IP per day, and require the markers to be visible (`NO_MARKERS` errors explain this). The page offers `markers.pdf` for download.
- **Health:** `/api/health`. A cold start must show the Home page within 10 s.

## Demo-video recording support (`scripts/record_demo.py`)

- Uses Playwright (Chromium, 1920 × 1080) to drive the app in replay mode.
- Follows the shot list in `docs/10-submission.md` and records each shot to `media/demo/shots/*.webm`.
- Then assembles them with ffmpeg: crossfades, titles, burned-in captions, and an optional voiceover track `media/demo/voiceover.wav` if the human records one.
- The output is `media/demo/demo_final.mp4` (≤ 3:00, 1080p, H.264 at CRF 20, `-preset veryfast`).
