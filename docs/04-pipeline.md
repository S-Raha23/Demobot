# 04. Pipeline: stage by stage

Each stage:
- reads earlier artifacts and writes `artifacts/<stage>*.json`;
- emits `stage_start` and `stage_end` plus `model_call` events;
- is idempotent: a rerun hits the cache.

Every tunable number lives in `config.py`.

## 1. Ingest (`media.py`)

**Accept** MP4, MOV or WebM:
- at most 120 MB;
- raw duration at most 60 s;
- the active span after trimming at most 40 s;
- height or width at least 480 px.

Reject anything else with a clear error code: `CLIP_TOO_LONG`, `CLIP_TOO_SMALL`, `NOT_A_VIDEO`, `NO_MARKERS`.

**Trim** idle head and tail by frame-difference motion energy, keeping 1 s of padding each side.

**The camera is handheld** (one hand holds the phone, the other does the task), so it moves slightly during every clip. Every stage that maps pixels to the table uses the per-frame camera track from Calibrate.

**Outputs:**
- `display_raw.mp4`: H.264, original aspect ratio, short side 720 px, 30 fps, audio kept, `-preset veryfast`. Calibrate turns it into the stabilised `display.mp4`.
- `analysis.mp4`: 10 fps, short side 720 px, no audio. This feeds SAM and Spark.
- `audio.wav`: mono, 16-bit, 16 kHz. Only if the clip has an audio track with RMS above the silence threshold.
- `keyframes/`: 8 evenly spaced frames, plus the first and last clean frames (frames where no hand overlaps an object, if known later).

## 2. Calibrate (`calibrate.py`): metric table plane and a per-frame camera track, no ruler needed

The human glued the 4 ArUco markers (`DICT_4X4_50`, IDs 0–3, black square **6.0 cm** edge to edge) roughly at the corners of a ~60 × 40 cm rectangle. **Their exact positions are unknown, and we never ask for measurements.** The phone is **handheld**, so the camera moves slightly during the clip: the markers are fixed to the table, the camera is not.

1. **Detect markers** with OpenCV ArUco on **every frame** of `analysis.mp4` (10 fps), with sub-pixel corner refinement. If a marker is missing in all frames, raise `NO_MARKERS` and say which ID.
2. **Blur flag.** For each frame, the variance of the Laplacian inside the marker regions (or the whole frame if none are seen). Frames below 0.45 × the clip median are flagged `blurred`; their detections are not used for fitting, and they are never chosen as "clean" frames.
3. **Marker layout by joint bundle fit** (the table is rigid, the camera is not).
   - Use up to 30 sharp frames where all 4 markers are visible, spread over the clip.
   - Unknowns: one homography per frame (image → table, 8 DOF each) plus, shared by all frames, an in-plane pose `(x, y, θ)` for markers 1–3. Marker 0 defines the origin, and its +x edge defines the axis.
   - Each marker's four corners in the table frame are its pose applied to a 6 × 6 cm square. Minimise the reprojection error of all corners in all frames with `scipy.optimize.least_squares` (sparse Jacobian).
   - Initialise from the first frame's single-frame fit (marker 0's corners give an exactly metric `H`).
   - Enforce the convention: marker 1 has x > 0 and marker 3 has y > 0.
4. **Per-frame homography.** With the marker layout known, every frame with **≥ 3 markers** gets its own `H_t` from all visible corners (RMS reprojection recorded).
5. **Camera.**
   - Focal length: `data/calibration/intrinsics.json` if it exists and its aspect ratio matches (scaled to this clip; axes swapped for landscape). It comes from `scripts/calibrate_camera.py` on `data/calibration/checkerboard.mp4` (9 × 6 inner corners, 25 mm squares, the human's phone). Otherwise the median of the per-frame Zhang single-view estimates over frames tilted ≥ 12° (the handheld motion makes this better conditioned than one view); otherwise a 64° phone field of view, with a warning.
   - **Temporal smoothing:** a Gaussian over time (σ = 0.5 frame at 10 fps) on the normalised entries of `H_t`, skipping outlier frames (reprojection > 3 px). A frame whose smoothed `H_t` fits its own markers more than 0.75 px worse than its raw fit keeps the raw one, so smoothing removes jitter without lagging real hand motion. Frames with fewer than 3 markers, and blurred frames, get `H_t` **interpolated** from the nearest good neighbours (linear in the entries, which is exact enough for small handheld motion; held constant at the ends). Smoothing the homography rather than the pose keeps the metric mapping exactly consistent even when the focal length is only a default.
   - Per-frame pose `(R_t, t_t)` from the smoothed `H_t` and `K` (for parallax correction and rendering).
   - The **reference camera** is the pose of the **last clean frame** (sharp, ≥ 3 markers, no hand over the work area if known; otherwise the last sharp frame). Verify and the twin's "real camera view" use it.
6. **Work area** = the bounding rectangle of the marker centres, shrunk by 4 cm. The robot base sits **28 cm in front of the work area's front edge** (the +y side), centred in x (`docs/06-simulation.md`).
7. **Stabilised display video.** Every 30 fps frame of `display_raw.mp4` is warped into the **first frame's view** with `M_t = G_0 · H_t` (image t → table → image 0), using the camera track interpolated to 30 fps, and written as `display.mp4` (audio kept). Everything drawn over the video in the UI (masks, trails, axes) is stored in these stabilised coordinates, so overlays and the side-by-side with the twin look steady.
8. **Outputs:**
   - `calibration.json`: marker layout, work area, robot base, the reference camera, focal source, reprojection, frame counts and warnings;
   - `camera_track.json`: per analysis frame `{t, H_img_to_table, rvec, tvec, markers_seen, reproj_px, sharpness, blurred, interpolated}`;
   - `display.mp4` (stabilised) and `stabilise.json` (the per-frame `M_t` at 30 fps);
   - `rectified_first.png` and `rectified_last.png` at 10 px/cm, each through its own frame's `H_t`, used by the judge and the UI;
   - a debug overlay with marker IDs and axes, drawn as a UI layer.

**Parallax correction** for a point at height `h` above the table, in frame t, is `p = c_t + (p_plane − c_t) · (H_cam,t − h) / H_cam,t`, where `c_t` is that frame's nadir and `H_cam,t` its camera height. Use the object's estimated half-height for its centroid.

## 3. Listen (`listen.py`): Voice Transcribe

If `audio.wav` exists, transcribe it with `languageBias` = English, Hindi, Bengali and `keywords` = common desk-object words. Output `transcript.json` with segments.

If a transcript is present, Watch gets it as **narration context** ("the person said: …"). Narration often states intent, e.g. "all the pens go in the mug". This is the main way to recover intent that motion alone cannot show.

## 4. Watch (`watch.py`): Muse Spark 1.3, plus the cross-watch second opinion

**Inputs:**
- the `analysis.mp4` file (`file_id`);
- the transcript;
- a short calibration note ("the camera looks at the table from the robot's side; image up is behind, image left is left");
- the allowed actions and relations;
- the TaskSpec JSON schema.

**Prompt rules** (`prompts/watch.md`):
- Name each object with a short concrete noun phrase that SAM can find ("blue pen", "white mug"), and give 2 `alt_names`.
- Mark the role of each object.
- List the steps in time order, one per moved object, with `t_start` and `t_end` in seconds.
- Write the **goal** in the goal DSL, generalised appropriately: use `kind` selectors when several objects of a kind behave the same way.
- Write `generalization` in one sentence.
- List `uncertainties` instead of guessing.
- Never invent steps that are not visible.

**Semantic checks after validation:**
- names are unique;
- every step's object and target exist;
- every `place_in` target has role `container`;
- times are within the clip duration and increasing;
- goal selectors resolve.

If a check fails, do one repair turn with the error list. If it still fails, raise `INVALID_TASKSPEC`.

**Cross-watch:** Muse Spark Open on Modal watches the same clip with the same prompt and schema, in parallel with Watch. Compare the two specs: objects (fuzzy name match), steps (action, object, target) and the goal.
- **Agreement score** = matched steps over the union of steps.
- If the score is < 1, **Wonder arbitrates**. It sees both specs, the transcript and keyframes, and returns the final TaskSpec plus a one-line reason. This is emitted as a `decision` event.

This number is reported in eval as the cross-model agreement.

## 5. Perceive (`perceive.py`): SAM 3.1

For each TaskSpec object, and then `"hand"`:
- Run a video request on `analysis.mp4`, **one phrase per request, sequentially**.
- Parse the output with `meta-sam-parser`.
- Keep the track whose ID best matches the object: highest mean score, plus spatial consistency with Spark's initial-region hint.
- If several instances match one phrase (e.g. two "pen"s), assign them to TaskSpec objects in left-to-right order of their initial positions, and record `ambiguous_ordinal`.

**Quality** = the fraction of frames with a box × the mean score.
- If quality < 0.5, retry with the next `alt_name`.
- If still low, fall back to image mode on keyframes plus linear interpolation, and flag it.
- Never fail silently.

Store masks as RLE (one-bit) for the overlay renderer, and the per-frame centroid of the mask's bottom contact region. SAM runs on the unstabilised `analysis.mp4` (the real pixels); for the overlay, masks are warped into stabilised display coordinates with that frame's `M_t`.

**Real final state:** run SAM image mode on the last clean frame for each phrase; this is more precise than the video's last frame.

**Object appearance:** for each object, crop its mask on a clean early frame and rectify it to a top-down patch using that frame's `H_t`. Save it to `artifacts/crops/<name>.png`. It becomes the texture of the object's stand-in in the twin.

## 6. Ground (`ground.py`): pixels to centimetres to events

Implement the algorithm specified in `reference/old_demobot/docs/spec/07-pipeline.md` section 7.5 (the first repo had the spec but no code for it). Defaults:
- `move_cm=1.5`, `move_frames=3`
- `settle_cm=0.3`, `settle_frames=5`
- `median=3`, `area_jump=0.4`, `occl_iou=0.3`
- `match_window_s=3.0`

1. **Convert to cm:** map each frame's centroids to the table plane through **that frame's own** `H_t`, then apply the parallax correction with that frame's camera pose (nadir `c_t`, height `H_cam,t`). Points in frames whose pose was interpolated are kept but down-weighted in the medians; points in blurred frames are dropped.
2. **Clean:**
   - drop points whose mask area jumps by more than 40%;
   - drop points occluded by the hand (box IoU > 0.3);
   - apply a 3-frame median.
3. **Motion segments:** anchor/settle logic. Occlusion gaps between two clean positions more than `move_cm` apart count as carries. Discard segments with less than 3 cm net displacement.
4. **Contact events:**
   - `grasp` = the first frame where the dilated hand mask overlaps the object mask within the 1 s before a segment starts;
   - `release` = the last overlap within 1 s after it ends.

   These sharpen the timeline and are shown as diamonds in the UI.
5. **Match steps to segments** by the largest time overlap within ±window.
   - Confidence = IoU of the time intervals × track quality.
   - Record `timing_delta_s` (Spark's timestamps versus measured).
   - If no segment matches, flag `no_motion_for_step`; the supervisor handles it.
6. **Build states:**
   - the initial and real final states use the medians of the first and last 5 clean frames;
   - footprint = the median mask extent mapped to cm, with a minimum of 2 cm;
   - height = Spark's `est_height_cm`, clamped to 1–20 cm.
7. **Real-world check:** evaluate the TaskSpec goal on the real final state. If a clause fails, either Spark misunderstood or SAM mis-tracked. This is the first job for the supervisor.

## 7. Twin build (`sim/layouts.py`, `sim/twin_export.py`)

Build the demo `Layout` from the grounded initial state:
- boxes for flat or long items;
- cylinders for round items (Spark's `kind` and the mask aspect ratio decide);
- open containers built from walls, with the footprint and height of the real container;
- each stand-in's top face textured with its crop.

Write `twin_scene.json` for the frontend:
- objects with sizes, textures and colours;
- the table rectangle;
- marker positions;
- the reference camera pose, i.e. the last clean frame's (so the browser can show the real camera's viewpoint);
- the robot base pose.

## 8. Program (`program/synth.py`): Muse Wonder writes and debugs the robot program

See `docs/05-agents.md`. The output is `program_v1.py` plus `synthesis_trace.json`. Every tool call made during synthesis is also an event, so the UI can animate the debugging loop.

## 9. Verify (`verify.py`, `judge.py`): three ways, plus a judge

Run the final program on the demo layout, then check four things:
1. **Symbolic:** the goal on the simulated final state (exact poses).
2. **Real-world:** the goal on the human's real final state, already computed in Ground. It must also pass, otherwise the spec does not match what the human did.
3. **Perceptual:**
   - render the sim final state **from the reference camera pose (the last clean frame)**, at the same resolution and with stand-ins textured by the real crops;
   - run SAM 3.1 image mode on that render with the same phrases;
   - map the masks through that frame's `H_t` and parallax pipeline;
   - evaluate the goal on this perceived state.

   This proves the result looks right to the same eyes that watched the human.
4. **Judge:** Muse Spark Open receives the human's real last clean frame and the camera-pose sim render (same pose), plus the goal in words and the clause table. It returns `{same_goal_achieved: bool, confidence, differences[], suspected_error}`.

**The run passes** when 1–3 all hold and the judge agrees. Any disagreement is classified into a `failure_class`:
- `spec_mismatch`: real-world fails;
- `program_bug`: symbolic fails;
- `perception_gap`: symbolic passes but perceptual fails;
- `judge_dissent`.

The failure goes to the supervisor.

## 10. Stress and harden (`agents/redteam.py`)

See `docs/05-agents.md`. Twelve adversarial layouts are generated in parallel, then validated, then simulated in parallel (Modal Sandboxes, falling back to a local pool).
- `robustness_before` is the fraction that passes.
- If it is below 1.0, Wonder hardens the program using the failures, and all 12 plus the demo layout are rerun to give `robustness_after`.
- At most 2 hardening rounds.
- Both program versions are kept with a diff.

## 11. Supervise (`agents/supervisor.py`)

Called on any failure from stages 4–10. See `docs/05-agents.md`. At most 4 decisions per run, each a visible `decision` event.

## 12. Correct (`correct.py`): voice or text

The browser records push-to-talk audio (WebAudio, then WAV at 16 kHz mono) and sends it to `/api/runs/{id}/correct`.
1. Voice Transcribe produces the correction text.
2. Wonder runs in correction mode: current program, TaskSpec, correction text and the tool loop. It returns a new program version plus an updated goal clause (corrections can change the goal; the goal change is shown explicitly).
3. Verify runs on the demo layout, then the stress layouts.
4. The UI shows the transcript (original script plus English gloss), the goal diff and the code diff.

## 13. Card (`card.py`): Muse Image

Anchored edit of `rectified_last.png`, or of the clean final frame. Prompt:
- "Turn this photo into a clean, friendly instruction card titled '<title>'";
- with the numbered steps (at most 3, each at most 8 words);
- an icon-style robot arm in the corner;
- a white background and flat colours;
- no other text.

Store `card.png`. If generation is refused or fails, use a template card made from the final frame.

## 14. Library and export (`library.py`, `export.py`)

Save a skill containing:
- `TaskSpec`, goal, latest program, `card.png`, robustness, cost to learn, and the source run ID.

Export a zip containing:
- `program.py`;
- `skill_api.md`, the API contract, so any robot stack can implement the six primitives;
- `goal.json`, `taskspec.json`, `card.png`;
- a `README.md`.
