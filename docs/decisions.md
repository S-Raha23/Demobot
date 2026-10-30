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
