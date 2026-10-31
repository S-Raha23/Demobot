# What the frontend needs from the backend

The UI works today against the existing API and fixture/real runs; each item below has a
graceful fallback in the UI until it exists.

1. **`GET /api/samples`** → `[{id, title, duration_s?, thumb?}]` for Home's "Run a sample clip".
   Fallback: the three newest recorded runs are shown as "Watch the recorded run".
2. **`POST /api/runs`** — multipart `clip` (+ optional `task_hint`), or JSON `{"sample": id}`;
   returns `{run_id}`. The UI navigates to `/run/<run_id>`. It shows friendly messages for
   404/405 (live runs off), 429 (daily judge budget used) and `NO_MARKERS`.
3. **`POST /api/runs/{id}/correct`** — multipart field `audio` (16 kHz mono 16-bit WAV, recorded
   with hold-to-talk) or JSON `{"text": ...}`; returns `{run_id}` of the correction run.
4. **`GET /api/eval`** → `{"markdown": "<contents of eval/results.md>"}` for the Costs & About
   page (tables, headings and lists are rendered). Fallback: a "not generated yet" note.
5. **Serve `assets/print/markers.pdf`** (e.g. at `/assets/print/markers.pdf`) so the upload
   dialog can link it.
6. **Run status for live runs:** the UI streams SSE live only when `run.json.status` is one of
   `running | queued | pending | live | started`; anything else (`done`, `failed`, `partial`, …)
   is replayed client-side from `events.json`. Please keep `status: "running"` while a run is live.
7. **Verify masks (nice to have):** `verify.json` has the real frame and camera-pose render but no
   SAM outlines for them, so the Verify tab shows the images without masks. Suggested:
   `"masks": {"real": [{"name", "poly_px"}], "camera": [...]}` in each image's pixels.
8. **Real camera view:** `twin_scene.json.camera` is the reference (last clean) frame's pose, which
   is ~25 px off the stabilised `display.mp4` (stabilised to the first frame). The UI therefore
   uses `camera_track.json.frames[0]` (rvec/tvec, with the track's focal/principal), which lines
   up within ~3 px. Optionally add `camera_first` to `twin_scene.json` and the UI can switch to it.
9. **Demo recording (`scripts/record_demo.py`):** Playwright's bundled Chromium cannot decode
   H.264, so `display.mp4` renders black there. Use a real Chrome binary
   (`executablePath`, e.g. Chrome for Testing) or `channel: "chrome"`, or also write a VP9
   `display.webm`. Useful URL flags for recording: `/run/<id>?speed=1|2|4`, `?skip=1`
   (jump to the result), `?tab=spec|program|verify|stress|costs` (pin a tab).
