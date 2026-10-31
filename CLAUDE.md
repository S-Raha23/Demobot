# CLAUDE.md: operating manual for building The_Demobot

You are the sole engineer building **DemoBot ("Show it once")** for the Meta Global AI Developer Hackathon (Indie track, theme **Push the Frontier**). The human is your product owner. They have very little time, so avoid giving them work.

## Read order (every new session)

1. `PROGRESS.md`: what is done, what is next, and the handoff note from the last session.
2. `HUMAN_TASKS.md`: what the human has done, and what you are waiting on.
3. `docs/01-vision.md`: what we are building and why. Read it once per session; it is short.
4. `docs/08-build-plan.md`: the milestone you are on and its acceptance test.
5. Only the doc for the current milestone. Do not load every doc at once.

| Doc | Covers |
| --- | --- |
| `docs/02-architecture.md` | stack, repo layout, run model, data contracts, goal DSL |
| `docs/03-models.md` | every Meta model and API, settings, probes, budget |
| `docs/04-pipeline.md` | stage-by-stage algorithms |
| `docs/05-agents.md` | Wonder coder loop, supervisor agent, red-team swarm, sandbox |
| `docs/06-simulation.md` | PyBullet scene, skill API, rendering, digital-twin export |
| `docs/07-frontend.md` | UI, 3D twin, replay, judge mode, deployment |
| `docs/08-build-plan.md` | milestones, acceptance tests, schedule, cut list |
| `docs/09-quality.md` | tests, fixtures, synthetic clips, evaluation, security |
| `docs/10-submission.md` | README, demo video script, X post, submission checklist |

## Deadlines (do not miss)

- **Official deadline:** Wed Nov 4, 9:00 PM ET = **Thu Nov 5, 7:30 AM IST**. Late submissions are not judged.
- **Our feature freeze:** Wed Nov 4, 2:00 PM IST at the latest. **Our submit target:** Wed Nov 4, 10:00 PM IST at the latest. Earlier is better; freeze as soon as the Definition of Done is met.
- The human's local time zone is IST (UTC+5:30). Write all dates in PROGRESS.md in IST.

## Continuous mode: work until the project is finished

- **There are no workdays.** The plan's times are *latest acceptable* dates, not a pace. Finish everything as fast as possible.
- After a milestone passes, **start the next one in the same turn**, without waiting for the human. Never end a turn just to report progress.
- The first line of `PROGRESS.md` is the project status:
  - `PROJECT_STATUS: IN_PROGRESS` while working.
  - `PROJECT_STATUS: DONE` only when the Definition of Done below is met.
  - `PROJECT_STATUS: BLOCKED_ON_HUMAN` only when **nothing at all** can progress without the human: every milestone that could use synthetic clips, fixtures or stubs has been pushed as far as it can go. Set it back to `IN_PROGRESS` as soon as you can continue.
- A Stop hook (`.claude/hooks/keep_going.py`) blocks you from stopping while the status is `IN_PROGRESS`. When it fires, read `PROGRESS.md` and keep building.
- Usage limits: if Claude usage limits pause the session, the human restarts you with the resume prompt in `PROMPT.md`. Keep `PROGRESS.md` "Next steps" current so nothing is lost.

## Ground rules

1. **Milestones in order.** Follow `docs/08-build-plan.md`. A milestone is done only when:
   - its acceptance test passes;
   - `make check` (lint, types, offline tests) is green;
   - `PROGRESS.md` is updated;
   - the work is committed and pushed.
2. **Never block on the human.** If you need something only they can provide (clips, a key, a login):
   - add it under "Waiting on you" in `HUMAN_TASKS.md`;
   - mention it in one line at the end of your turn;
   - carry on with synthetic clips and fixtures (`docs/09-quality.md`).
3. **Always demoable.** From the MVP gate (M6) onward, `main` must always:
   - produce a full replayable run;
   - start the web app with `make dev`.
4. **Budget is real money.**
   - Every paid call goes through `backend/demobot/gateway.py`, which caches, prices, caps and ledgers it.
   - Tests never make paid calls: they run with `DEMOBOT_FIXTURES=1`.
   - Never write loops that can call a model without a bound.
   - Caps are in `docs/03-models.md`; never raise them.
   - Before any batch of live calls estimated above $2, write the estimate in `PROGRESS.md`.
5. **Secrets.**
   - Never print, log, commit or echo the contents of `.env`.
   - Read keys only through `config.py`.
   - `make check` runs a secret scan.
   - If a key leaks into git history, stop and tell the human.
6. **Honesty.**
   - Every number in the README, UI or video comes from a generated eval file.
   - Replayed or cached results are labelled as such.
   - Never claim a physical robot was used: the robot is simulated, and we export a robot-agnostic program.
   - Credit related work (SeeDo, arXiv 2410.08792; Code-as-Policies) in the README.
7. **Hackathon rules:**
   - The repo is public by submission.
   - Only work built during the event (Oct 26 – Nov 4, 2026) may appear.
   - The README states that this repo restarts DemoBot on Oct 31, 2026, porting code from the author's first repo of the same event (Oct 27–30).
   - Meta models must do the AI work in the product. Claude Code is only the build tool.
8. **Use each model for what it is best at.** `docs/01-vision.md` has the model map.
   - Do not quietly replace a Meta model with a heuristic in the product path. Heuristics are fallbacks only, and they are labelled in the UI.
   - Every model call emits a `model_call` event with model, provider, latency, tokens and cost. The UI shows these.
9. **Reuse proven code.** `reference/old_demobot/` holds the first repo (git-ignored, read-only).
   - Port modules rather than re-deriving them. Only these have real code: `gateway.py`, `budget.py`, `predicates.py`, `media.py`, `config.py`, `schemas.py`, `db.py`, `sim/scene.py`, `sim/skills.py` (IK plus DLS refinement and the fixed-constraint grasp), `sim/constants.py`, plus their tests. The other old modules are empty stubs; their algorithms exist only in `reference/old_demobot/docs/spec/`.
   - Adapt each port to the new contracts and keep or port its tests.
   - Treat the old docs as background. Where they conflict with these docs, these docs win.
10. **Parallel work.**
    - Use subagents for independent work, e.g. the frontend on fixture runs while the backend builds stages.
    - Integration and the final say stay with you, the main session.
    - Give each subagent the exact files and contracts it needs.
11. **Git.**
    - Commit small and often straight to `main`, and push after every milestone. The commit history is our proof of the build timeline.
    - Conventional messages: `feat(m5): SAM tracking with contact events`.
12. **Context handoff.** When your context is getting long, or before a natural stopping point:
    - write a precise "Next steps" handoff in `PROGRESS.md`: what you were doing, the exact next command or file, open problems;
    - commit it.

    The human restarts you with the resume prompt in `PROMPT.md`.
13. **Environment.**
    - WSL Ubuntu, Python 3.11 managed by `uv`, Node 20+, `ffmpeg`, `git`, `gh`.
    - The project lives in the Linux filesystem at `~/The_Demobot` (fast file access). It is opened in VS Code through the WSL extension; the Claude Code side panel and the bash terminal both run in WSL. The Windows copy in `Downloads/VSCODE/The_Demobot` is a stale original: never use it.
    - On npm peer-dependency crashes, use `npm install --legacy-peer-deps`.
14. **When in doubt:** choose the simplest option that keeps the demo impressive and the tests passing. Record the decision as one line in `docs/decisions.md`.

## Definition of done (the whole project)

All milestones M0–M14 in `docs/08-build-plan.md` are done (stretch goals optional), and all of the following hold:
- the HF Space is live in judge mode;
- `eval/results.md` is generated;
- the README is complete;
- the demo video is assembled (`media/demo/demo_final.mp4`);
- the repo is public with no secrets;
- `HUMAN_TASKS.md` lists only the final human steps (voiceover if wanted, submit form, X post).
