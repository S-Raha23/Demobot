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

**Outputs:**
- `display.mp4`: H.264, original aspect ratio, short side 720 px, 30 fps, audio kept, `-preset veryfast`.
- `analysis.mp4`: 10 fps, short side 720 px, no audio. This feeds SAM and Spark.
- `audio.wav`: mono, 16-bit, 16 kHz. Only if the clip has an audio track with RMS above the silence threshold.
- `keyframes/`: 8 evenly spaced frames, plus the first and last clean frames (frames where no hand overlaps an object, if known later).

## 2. Calibrate (`calibrate.py`): metric table plane, no ruler needed

The human glued the 4 ArUco markers (`DICT_4X4_50`, IDs 0–3, black square **6.0 cm** edge to edge) roughly at the corners of a ~60 × 40 cm rectangle. **Their exact positions are unknown, and we never ask for measurements.**

1. **Detect markers** with OpenCV ArUco on up to 30 frames where all 4 are visible; use sub-pixel corner refinement. The camera is fixed: take the per-corner median. If a marker is missing in all frames, raise `NO_MARKERS` and say which ID.
2. **Metric plane by bundle fit.**
   - Unknowns: a homography `H` (image → table, 8 DOF) plus, for markers 1–3, an in-plane pose `(x, y, θ)`. Marker 0 defines the origin, and its +x edge defines the axis.
   - Each marker's four corners in the table frame are its pose applied to a 6 × 6 cm square.
   - Minimise reprojection error of all 16 corners with `scipy.optimize.least_squares`.
   - Initialise `H` from marker 0's own four corners alone (exactly metric), and each marker pose from mapping its corners through that `H`.

   The result is metric marker positions and `H`, typically < 1.5 px RMS. The table frame's +y may be flipped relative to the human's intent. Enforce the convention: marker 3 has y > 0 and marker 1 has x > 0.
3. **Camera.**
   - If `data/calibration/intrinsics.json` exists and its aspect ratio matches, scale its focal length and principal point to this clip's resolution. That file is produced by `scripts/calibrate_camera.py` from `data/calibration/checkerboard.mp4`: 9 × 6 inner corners, 25 mm squares, recorded portrait at 1080 × 1920 (HEVC, 30 fps, 60 s) on the human's phone. Corners were confirmed detectable on sampled frames. For landscape clips, swap the axes of the intrinsics.
   - Otherwise estimate focal length from `H`, assuming square pixels, a centred principal point and zero skew (Zhang's single-view constraints).
   - Then decompose to get the camera pose: position in table cm, height above the table `H_cam`, and the nadir point.
4. **Work area** = the bounding rectangle of the marker centres, shrunk by 4 cm. The robot base sits **28 cm in front of the work area's front edge** (the +y side), centred in x (`docs/06-simulation.md`).
5. **Outputs:**
   - `calibration.json`;
   - `rectified_first.png` and `rectified_last.png` at 10 px/cm, used by the judge and the UI;
   - a debug overlay with marker IDs and axes, drawn as a UI layer.

**Parallax correction** for a point at height `h` above the table is `p = c + (p_plane − c) · (H_cam − h) / H_cam`, where `c` is the nadir. Use the object's estimated half-height for its centroid.

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

Store masks as RLE (one-bit) for the overlay renderer, and the per-frame centroid of the mask's bottom contact region.

**Real final state:** run SAM image mode on the last clean frame for each phrase; this is more precise than the video's last frame.

**Object appearance:** for each object, crop its mask on a clean early frame and rectify it to a top-down patch using H. Save it to `artifacts/crops/<name>.png`. It becomes the texture of the object's stand-in in the twin.

## 6. Ground (`ground.py`): pixels to centimetres to events

Implement the algorithm specified in `reference/old_demobot/docs/spec/07-pipeline.md` section 7.5 (the first repo had the spec but no code for it). Defaults:
- `move_cm=1.5`, `move_frames=3`
- `settle_cm=0.3`, `settle_frames=5`
- `median=3`, `area_jump=0.4`, `occl_iou=0.3`
- `match_window_s=3.0`

1. **Convert to cm:** map centroids to the table plane through H, then apply the parallax correction.
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
- the camera pose (so the browser can show the real camera's viewpoint);
- the robot base pose.

## 8. Program (`program/synth.py`): Muse Wonder writes and debugs the robot program

See `docs/05-agents.md`. The output is `program_v1.py` plus `synthesis_trace.json`. Every tool call made during synthesis is also an event, so the UI can animate the debugging loop.

## 9. Verify (`verify.py`, `judge.py`): three ways, plus a judge

Run the final program on the demo layout, then check four things:
1. **Symbolic:** the goal on the simulated final state (exact poses).
2. **Real-world:** the goal on the human's real final state, already computed in Ground. It must also pass, otherwise the spec does not match what the human did.
3. **Perceptual:**
   - render the sim final state **from the real camera's pose**, at the same resolution and with stand-ins textured by the real crops;
   - run SAM 3.1 image mode on that render with the same phrases;
   - map the masks through the same H and parallax pipeline;
   - evaluate the goal on this perceived state.

   This proves the result looks right to the same eyes that watched the human.
4. **Judge:** Muse Spark Open receives the human's real final frame and the camera-pose sim render, plus the goal in words and the clause table. It returns `{same_goal_achieved: bool, confidence, differences[], suspected_error}`.

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
