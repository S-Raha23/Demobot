# Documentation index

Start here. The guides below are the public design story; the internal notes at the end are working records kept for reproducibility.

## Visitor guides (read in this order)

1. [01 · Vision](01-vision.md) — what DemoBot is and why one phone video should be enough.
2. [02 · Architecture](02-architecture.md) — stack, repository layout, and the event-sourced run model.
3. [03 · Models, APIs, probes and budget](03-models.md) — which Meta model does which job, the provider chains, and the spend caps.
4. [04 · Pipeline: stage by stage](04-pipeline.md) — ingest → calibrate → listen → watch → perceive → ground → program → verify → stress → harden → card.
5. [05 · Agents: the coder, the supervisor and the red team](05-agents.md) — how the Wonder coder loop, the failure-routing supervisor, and the seven red-team personas work.
6. [06 · Simulation, skill API and the digital twin](06-simulation.md) — PyBullet Panda, the centimetre goal DSL, and the browser twin.
7. [07 · Frontend, replay, judge mode and deployment](07-frontend.md) — the React app, mission-control replay, and the Docker/Hugging Face deploy.
8. [09 · Quality: tests, fixtures, synthetic clips, evaluation and security](09-quality.md) — how correctness is checked offline and live.
9. [Run directory and event payloads](run-artifacts.md) — the UI ↔ backend contract: every file a run produces and the event schema.
10. [DemoBot skill API](skill_api.md) — the `run(scene, robot)` API an exported skill targets on any robot.

## Internal notes (working records, not the tour)

- [Decisions log](internal/decisions.md) — one line per decision that changed the plan, with the reason.
- [Probe results (M0)](internal/probe-results.md) — measured answers to the `docs/03` PROBE checklist, from `scripts/probe_models.py`.

## Fixtures: how the offline judge site works

`backend/tests/fixtures/runs/` holds 11 baked runs (real desk clips and synthetic clips, plus `fx-*` fixture runs). They are recorded once from real pipeline runs and then replayed forever at zero model cost:

- The deployed judge site serves these runs read-only — Library, Replay, Try-it and Costs all render from the baked `events.jsonl` and artifacts, so judging never stalls on a live model call and never spends.
- `scripts/bake_runs.py` copies a finished run into `backend/tests/fixtures/runs/`; the Docker image ships them via `COPY backend/ backend/`.
- Offline checks use the same fixtures (`DEMOBOT_FIXTURES=1` in `make test`), so CI verifies the exact bytes a judge sees.

Do not delete or move `backend/tests/fixtures/` — the judge deployment and the offline test suite both depend on those paths.
