# Decisions log

Append one line per decision that changes the plan: `YYYY-MM-DD — decision — why`.

- 2026-10-31 — Restart DemoBot in a new repo (The_Demobot), porting tested modules from the first repo (Oct 27–30, since deleted) — a cleaner, more ambitious architecture within the same event.
- 2026-10-31 — Everyday desk objects instead of coloured blocks; SAM 3.1 open-vocabulary phrases replace colour (HSV) tracking as the main path — no shopping for the human, and a stronger showcase of SAM.
- 2026-10-31 — Ruler-free calibration: a markers bundle fit gives the metric plane from the known 6 cm marker size; the checkerboard intrinsics are optional — the human only glues the markers.
- 2026-10-31 — The phone can be angled (0–50° from vertical), not only top-down — no camera mount needed.
- 2026-10-31 — The robot program is code written by Muse Wonder against a fixed skill API, with the simulator in the loop, replacing a fixed step list — generalises to new layouts; showcases Wonder's agentic coding.
- 2026-10-31 — Three-way verification including SAM on the simulator render from the real camera pose — "checks itself with the same eyes".
- 2026-10-31 — Red-team swarm on Muse Spark Open (Baseten) plus Wonder hardening — robustness numbers, high-volume work on open weights.
- 2026-10-31 — Event-sourced runs with replay — judge mode and the demo video can never stall.
- 2026-10-31 — 3D twin in the browser (three.js + urdf-loader) from trajectories exported by PyBullet — far more impressive than PyBullet MP4s, and interactive (Try-it).
- 2026-10-31 — Drop Neon Postgres; the SQLite ledger plus per-pool caps suffice; the Space runs in judge mode with daily caps — less setup.
- 2026-10-31 — No Streamlit (on the organisers' list of projects to avoid).
- 2026-10-31 — The docs' table frame (+x to marker 1, +y to marker 3/robot, z up) is left-handed, so it stays a 2D frame; 3D maths uses (x, y, z_down) and PyBullet uses X = x/100, Y = −y/100, Z up — keeps the documented relations (left_of = −x, in_front_of = +y) and a right-handed simulator.
- 2026-10-31 — Focal length: checkerboard intrinsics if present (human's phone: f ≈ 1544 px at 1920, long-side FOV 63.7°), else Zhang's single-view estimate when tilt ≥ 12°, else a 64° phone FOV default with a warning — a near top-down view cannot determine focal length from one homography.
- 2026-10-31 — Synthetic marker tables are rendered by warping a texture through an exact pinhole camera (fast, exact ground truth); M3 adds 3D objects and the hand — calibration tests run in milliseconds.
- 2026-10-31 — No lens undistortion of marker corners (the phone video is already mostly corrected; residual < 1 px) — simpler, revisit if real-clip reprojection > 1.5 px.
- 2026-10-31 — `place_in` stands an object upright inside a container when it does not fit lying flat (pens into a mug): the gripper lets go above the rim and the object slides in over 24 physics steps — that is how a person puts pens in a mug, and a flat 14 cm pen cannot fit a 9 cm mug.
- 2026-10-31 — Skill API additions: `free_spot(avoid=[(x, y, w, d)])` and +6 cm clearance around objects taller than 5 cm (the Panda hand is ~20 cm wide) — robust hand-written programs needed both; Wonder will too.
- 2026-10-31 — Collision = another object displaced > 1 cm by a skill (objects jostled but still inside the target container are fine); raised as `Collision` so the program's author sees it.
- 2026-10-31 — Sandbox memory limit 2 GB of address space instead of 1 GB (PyBullet + NumPy map more than 1 GB); CPU 20 s per task via RLIMIT_CPU on a reused spawn worker; wall timeout 90 s.
- 2026-10-31 — The camera-pose render hides the robot: it is compared with the human's real final frame, which has no robot.
- 2026-10-31 — **Handheld camera** (human's spec change): the phone is held in one hand while the other does the task, so calibration estimates a per-frame camera track (joint bundle fit with shared marker poses and per-frame homographies, per-frame H from ≥ 3 markers, Gaussian temporal smoothing, interpolation across frames with < 3 markers or blur, blur flagged by Laplacian variance). Perceive/Ground map each frame through its own H and pose; Verify and the twin's real-camera view use the last clean frame's pose; `display.mp4` is stabilised to the first frame's view; synthetic clips add mild handheld shake — no tripod or phone stand needed.
- 2026-10-31 — Supersedes the fixed-camera assumption of the earlier calibration entry and the "don't move the phone" filming instruction.
- 2026-10-31 — Per-frame homographies are smoothed lightly (σ = 0.5 frame) with a guard: a frame whose smoothed H fits its own markers > 0.75 px worse keeps its raw H — the synthetic tests showed σ = 1 lags 1–2 Hz hand motion by up to 2 cm, while raw per-frame fits are accurate to ~0.1 px.
- 2026-10-31 — Synthetic objects mirror the human's real ones (white square plastic box, mug, two teal pens, teal box cutter, small glue bottle, yellow tennis ball, steel spoon), filmed handheld in landscape — the pipeline is tuned for what the real clips will show. `sphere` added as a shape (tennis ball, with rolling friction).
- 2026-10-31 — Container insertion modes shared by sim and synth (`skills.container_slot`): flat (small items to a corner on one diagonal), diagonal across a square box for long items (cutter, spoon; turned above the contents, then lowered onto what is under that diagonal), upright for pens in a mug — what a person does with these objects.
- 2026-10-31 — Perceptual verification shows SAM the sim's objects composited onto a clean plate (the reference frame with every tracked object inpainted): SAM finds nothing in a bare CPU render, even a tennis ball it finds in the real frame. Objects hidden in both views (pens inside a cup) are checked at their simulated position, labelled — the render still comes from the sim state, through the real camera, on the real table.
- 2026-10-31 — The judge gets the object list with roles, so it can tell a distractor from a goal object.
- 2026-10-31 — GitHub repo is S-Raha23/Demobot (created by the human).
- 2026-10-31 — A stand-in SAM cannot see in the render makes the perceptual check *inconclusive* (UI: grey), not failed; only a seen contradiction is a perception_gap — SAM is unreliable on simulated primitives, and a false failure would send correct runs to the supervisor.
