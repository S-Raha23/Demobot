# PROMPT: how to start Claude Code and what to paste

## Start Claude Code (WSL)

```bash
# Windows Terminal → Ubuntu (WSL)
cd ~/The_Demobot
code .                     # VS Code opens with "WSL: Ubuntu" bottom-left; use the Claude Code side panel (Opus 5.5)
# or, in the terminal instead of the panel:  claude --model opus
```

`.claude/settings.json` already allows the usual build commands and auto-accepts file edits, so you will rarely be asked to approve anything. It also blocks Claude from reading `.env`, so your keys never enter the transcript.

**It keeps going on its own.** A Stop hook (`.claude/hooks/keep_going.py`) stops Claude from ending its turn until `PROGRESS.md` says `PROJECT_STATUS: DONE` or `BLOCKED_ON_HUMAN`. To pause it yourself, press **Esc**, or create an empty file `.claude/ALLOW_STOP` (delete that file before resuming). If your Claude plan's usage limit pauses it, wait for the reset and paste the resume prompt.

## 1. Kickoff prompt (paste once)

```text
You are building The_Demobot, our entry for the Meta Global AI Developer Hackathon, from scratch and end to end. Aim for a first-place-quality project: impressive, robust and honest.

1. Read CLAUDE.md and follow it exactly. Then read PROGRESS.md, HUMAN_TASKS.md, docs/01-vision.md and docs/08-build-plan.md. Read the other docs only when a milestone needs them.
2. Check what the human has already done: data/clips/raw/ (real clips and voice notes), .env present (check that the variable names exist without printing values), `gh auth status`, and whether a Modal token exists. Record the result in HUMAN_TASKS.md. Anything missing goes under "Waiting on you". Never wait on it: real clips can be replaced by synthetic clips (M3) until they arrive.
3. Build milestones M0 → M14 in order, per docs/08-build-plan.md, without asking me for confirmation between milestones. Each milestone ends with: its acceptance test passing, `make check` green, PROGRESS.md updated, then commit and push.
4. Port proven code from reference/old_demobot/ (gateway, budget, predicates, sim scene and skills with the IK refinement, media checks) instead of re-deriving it. Adapt it to the new contracts in docs/02.
5. Once M2 produces a fixture run, start the frontend (M11) with a subagent working only on fixture runs and the documented contracts. You stay the integrator.
6. Treat the budget as real money: every paid call goes through the gateway with caching and caps. Never make paid calls in tests. Write the estimate in PROGRESS.md before any live batch over $2.
7. Use every Meta model for its strongest capability as mapped in docs/01. Never silently replace one with a heuristic in the product path. Fallbacks must be visible in the events and the UI.
8. Visual quality matters as much as correctness. Take Playwright screenshots of the UI at 1920x1080, look at them, and polish until it looks like a top-tier product.
9. Bake a replayable run of the current best state every ~6 hours of work, so a demo always exists.
10. Work continuously: there are no workdays and no pauses between milestones. When one passes, start the next in the same turn. Keep the first line of PROGRESS.md as `PROJECT_STATUS: IN_PROGRESS` (a Stop hook keeps you going while it says that).
11. Stop only when the Definition of Done in CLAUDE.md is met (set PROJECT_STATUS: DONE), or when you are truly blocked by something only I can do and nothing else can move forward. In that case, set PROJECT_STATUS: BLOCKED_ON_HUMAN, write the handoff in PROGRESS.md, and tell me in 3 lines exactly what you need.

Start now with M0.
```

## 2. Resume prompt (paste whenever you restart Claude Code)

```text
Continue building The_Demobot. Read CLAUDE.md, then PROGRESS.md (especially "Next steps") and HUMAN_TASKS.md. Check data/clips/raw/ for anything new I added. Then continue from where the handoff says, following docs/08-build-plan.md. Don't redo finished milestones. Set the first line of PROGRESS.md to PROJECT_STATUS: IN_PROGRESS if I have added what you were waiting for. Work continuously, without pausing between milestones, until the Definition of Done or a true blocker.
```

## 3. Useful short prompts

- **Status check:** `Give me a 5-line status: milestone, what works, spend per pool, what's next, anything waiting on me.`
- **Behind schedule:** `We're behind. Apply the cut list in docs/08 from the top until the remaining milestones fit before the Wed 14:00 IST freeze. Update PROGRESS.md.`
- **Final day:** `Freeze features. Run eval, finish the README, render the demo video and the 30 s cut, write docs/submission-form.md, and run the full submission checklist in docs/10.`
