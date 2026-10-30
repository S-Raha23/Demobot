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
