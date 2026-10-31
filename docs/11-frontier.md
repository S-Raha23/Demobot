# 11. Frontier upgrades: Skill Forge, Live Twin, "Did you mean…?"

Added Sat Oct 31, 2026, 23:00 IST. These three upgrades are built **on top of** the working DemoBot. They must never break it.

## Ground rules for this phase

1. **Gate 0, before any new feature.**
   - The baseline Definition of Done holds: deployed site, README, `eval/results.md`, demo video v1, repo public, no secrets.
   - Finish anything missing first.
   - Then tag the commit `v1-submittable` and push the tag. A complete submission must always exist.
2. **Feature flags.** Each upgrade sits behind a flag in `config.py`: `FRONTIER_FORGE`, `FRONTIER_LIVE`, `FRONTIER_ASK`. They default to on in dev and on in judge mode only once the acceptance test passes. When a flag is off, the UI hides that feature completely.
3. **Order:** Fix 0 → F1 Skill Forge → F2 Live Twin → F3 "Did you mean…?" → re-cut the video and update the README.
4. **Latest acceptable times (IST):**

   | Step | Latest |
   | --- | --- |
   | F1 | Sun Nov 1, 20:00 |
   | F2 | Mon Nov 2, 16:00 |
   | F3 | Mon Nov 2, 23:00 |
   | Video and README v2 | Tue Nov 3, 18:00 |
   | Freeze (unchanged) | Wed Nov 4, 14:00 |

   These are latest times, not a pace: go as fast as possible. If F1 or F2 are not done by their time, apply the cut rules at the end of this file.
5. **Budget.** Caps are unchanged (`docs/03-models.md`). About $20 of Meta credit was spent by Oct 31, 22:40 IST. New estimates:
   - F1: about $6 of Wonder;
   - F2: Modal GPU about $15–25 (a hard sub-cap of **$30 on GPU spend**, enforced by an idle shutdown plus a GPU-minutes ledger);
   - F3: about $3.
6. Add each upgrade as milestones in `docs/08-build-plan.md` and `PROGRESS.md` (F0–F3), with the acceptance tests below. Record design choices in `docs/decisions.md`.

## Fix 0: bugs found on the live site (audited Oct 31, 22:55 IST)

Fix these first, in this order. Each one is visible to judges.

**Correctness and honesty (highest priority)**

1. **The box cutter is tracked as a third pen.** Real runs list "left / middle / right light blue pen" plus "light blue pen cap", but the scene has 2 pens and 1 cutter. The SAM phrase "light blue pen" matches the cutter too, so "every pen" skills move the cutter.
   - Fix: after tracking, verify each SAM instance with a cheap Spark 1.3 or Spark Open crop check ("is this a pen or a box cutter?"), split instances that belong to different kinds, and re-track with a more specific phrase.
   - Add a regression test on `clip_01`–`clip_05`: exactly 2 pens and 1 cutter.
   - This is also the natural demo case for F3.
2. **Try-it shows the wrong skill.** The dropdown says "Put every pen in the white plastic tub", but the panel says "Put the green ball in the tub" with goal `all kind: tennis ball inside white plastic tub`. A voice correction on a run seems to have overwritten the library skill.
   - Fix: a correction creates a **new skill version or a new skill** and never overwrites the demo skill.
   - The dropdown, the panel title, the goal and the program version must always come from the same record.
   - Add an integration test.
3. **Run header mismatch.** `/run/real-spoon-in-tub` shows "Put the green (yellow tennis) ball inside the tub (corrected by voice; demo: Put the silver spoon…)".
   - Fix: show the demo skill as the title, and any correction as a separate, clearly labelled version chip ("v2: corrected by voice: ball into the tub").
4. **Names vary between runs** for the same physical object: "white box" / "white plastic tub", "green ball" / "yellow tennis ball", "steel spoon" / "silver spoon", "small glue bottle" / "white glue bottle".
   - Fix: a per-table **object registry** (canonical name, kind, colour, size, crop) built from the real clips. Watch output is mapped onto it (fuzzy match on kind, colour and size).
   - Display canonical names everywhere: library, runs, Try-it, cards.
5. **Synthetic runs not labelled as synthetic.** "Swap the white cylinder and the gray block", "Put every pen in the white cup" and "Put the teal pen left of the white box" come from synthetic clips but carry no "synthetic" badge, while other synthetic skills do.
   - Fix: every skill and run carries a `source: real | synthetic` from its clip, and the badge is always shown.
   - Order the library real-first.
   - Make the homepage "Run a sample clip" offer at least one **real** clip (with cached model responses, so it stays cheap).
6. **The "Your turn" step on the homepage is badged "Image"**, but Try-it uses no Muse Image. Badge the steps truthfully: Try-it is simulation only, and Muse Image belongs to the skill-card moment.

**3D twin and visuals**

7. **The robot is hidden in the homepage hero twin**, and **the robot blocks the table in Try-it top-down view** (a huge translucent arm covers the near half of the work area).
   - Fix: frame the hero twin so the Panda is visible next to the table.
   - In top-down edit mode, hide the robot or draw it as a thin outline at its base position, outside the work area.
   - Double-check the robot base pose against `docs/06` (28 cm in front of the work area's near edge, facing the table).
8. **Stand-in shapes and textures.**
   - The white tub is drawn as a large **cylinder (disc)** overlapping the spoon, but it is a square tub. Use the mask shape (rectangularity / aspect ratio) to choose box versus cylinder, and use the measured footprint.
   - Apply each object's **real top-down crop as the texture** on the stand-in's top face (docs/06). Right now stand-ins are plain.
   - This is also why the **perceptual check is "inconclusive" on 3/5 real and 5/10 synthetic runs**: SAM can't recognise plain shapes. Re-measure after textures are added, and report it in eval.
9. **Overlapping initial layouts.** Try-it object lists show "overlaps steel spoon / overlaps white plastic tub / overlaps light blue pen cap", and the program stage logs repeated "layout repair: nudged … 0.4 → 3.5 cm".
   - Fix: build the twin from de-duplicated tracks (after fix 1), with correct footprints (after fix 8).
   - The validator must produce a non-overlapping demo layout in one repair pass.
10. **Label clutter.** Twin object labels pile on top of each other, and SAM overlay labels in the real video are truncated ("#1 white plastic tu…").
    - Fix: label collision avoidance (offset or leader lines); show labels on hover or selection, plus for the moved objects only by default.
    - Shorten the overlay labels to the canonical short name.

**Cost and efficiency**

11. **Red-team calls hit the output limit.** Each Spark Open persona call produces 11–12k output tokens and ends `incomplete`, then retries (billed twice) and falls back to Modal. That's about $0.10 per persona instead of about $0.01.
    - Fix: lower the reasoning effort (low), ask for **compact layout JSON only** (numbers rounded to 0.5 cm), set a sensible `max_tokens` with headroom for reasoning, and validate.
    - Measure the before/after cost per red-team round and put it in PROGRESS.
12. **The judge call takes about 42 s.** Use low reasoning effort and smaller images. Target < 15 s.

**Costs page**

13. "BUILD LEDGER (EVERY PAID CALL WHILE BUILDING) Total $0.00" is wrong on the deployed site, because the dev ledger isn't shipped. Either ship a read-only snapshot of the dev ledger totals (per provider, with date) or remove that box.
14. The eval header says `at git ```: the SHA is empty. Fill it in.
15. Clarify the two open-weight numbers: 46% is a share of **spend** (costs page), 40% a share of **calls** (eval). Label both explicitly.
16. "Mean over 11 runs (3 synthetic, simulated prices)": explain or remove "simulated prices".

**Accessibility**

17. The skill-card image links have no text: add `aria-label` or `alt` text, e.g. "Replay: Put every pen right of the white box".

**Acceptance (Fix 0):** a Playwright run over Home, one run page, Try-it for every skill and Costs, with screenshots reviewed by you and all 17 items checked off in PROGRESS. Then rebake the affected runs and redeploy.

---

## F1: Skill Forge, the robot invents its own skills

**The story:** "The box is too wide for the gripper. DemoBot noticed it had no way to move it, so it invented a `push` skill, tested it, and added it to its toolkit for good."

### Forge-tier API (only inside the forge sandbox)

These are low-level primitives, added to `program/api.py` under a `forge` namespace and **not** exposed to normal programs:

```python
robot.ee_pose() -> tuple[x, y, z, yaw]                 # cm / degrees
robot.move_ee(x, y, z, yaw=None, speed=1.0) -> None    # straight-line Cartesian move with IK; raises NotReachable / Collision (except allowed contact)
robot.grip(state: "open" | "close", width_cm: float | None = None) -> None
robot.wait(seconds: float) -> None                     # let physics settle
scene.pose(obj) -> tuple[x, y, z, yaw]
scene.in_contact(a, b) -> bool
scene.gripper_width_max() -> float                     # Panda about 8 cm
```

In forge mode, contact between the closed gripper and the target object is allowed. Collisions with any other object still raise.

### Triggers

1. **From Watch.**
   - Extend the TaskSpec actions with `other_motion`: Spark uses it when it sees a demonstrated motion that is not pick-and-place (sliding or pushing, rotating in place, stacking, tipping), plus a description and the start and end time.
   - Ground already measures the start and end pose of the moved object. Add **yaw** from the mask's principal axis, so rotations are measurable.
2. **From the coder.**
   - Add a tool `request_new_skill(name, signature, purpose, evidence)` to the Wonder coder loop.
   - Wonder calls it when no combination of the current primitives can achieve the goal. Typical reasons: the object is wider than `gripper_width_max()`, the goal needs a yaw change, the goal needs a z offset (stacking).
   - The call must cite evidence: the failed `simulate` results, or a measured property.

### The forge loop (Muse Wonder, tools, at most 10 turns)

| Tool | Does |
| --- | --- |
| `write_skill(code)` | Defines `def <name>(robot, scene, <args>)` using forge-tier plus existing primitives. The AST guard plus sandbox apply (forge namespace allowed). |
| `write_tests(code)` | Defines ≥ 3 test functions. Each builds a layout through the `layouts` helpers (random seeds), calls the skill and asserts outcome predicates (pose tolerance, no other object displaced > 1 cm, object upright). |
| `run_tests(n_layouts=10)` | Runs every test on n randomised layouts in parallel (Modal Sandboxes, falling back to a local pool). Returns the pass rate, failures with top-down renders, and the twin trajectories of the first 3 runs. |
| `inspect_physics(obj)` | Mass, friction, size and the resting contacts of an object. |
| `promote(explanation)` | Accepted only if the pass rate ≥ 9/10 on fresh seeds **and** the regression gate passes. |

**Regression gate:** every existing library skill reruns on its demo layout plus 3 random layouts with the new skill available, and none may get worse.

**On promotion:**
- write `backend/demobot/skills/forged/<name>.py` with its tests;
- auto-generate the docstring into `skill_api.md`;
- bump `skill_api_version`;
- emit a `skill_forged` event;
- the coder prompt includes all forged skills from then on;
- the exported skill zip includes any forged skills its program uses.

### Physics notes

- **Push:** close the gripper; approach behind the object at z = 0.5 × the object's height; move in a straight line at low speed; finish with a small retreat. Use realistic friction and mass for the box stand-in. Tests must allow a ±2 cm, ±10° tolerance.
- **Rotate in place:** grasp at the centre, lift 1 cm, rotate yaw, place.
- **Stack:** `place_at` with z = the top of the base object, followed by a stability check after a 1 s settle.

### Evidence clips

- Use synthetic clips first: add `push` and `rotate` families to `synth/`.
- Then the human's real clips `06_push_box.mp4` (slide the white box with fingertips) and `07_rotate_cutter.mp4` (turn the cutter 90° in place). These are listed in `HUMAN_TASKS.md`.

### UI

- **A "Forge" tab in mission control:**
  1. the capability-gap card (why: "box 13.2 cm > gripper 8 cm");
  2. a skill spec;
  3. a code view with versions;
  4. a test grid (10 mini twins with pass/fail);
  5. the regression check;
  6. the promotion banner.
- **A Library page "Toolkit" section:** primitives with badges, "built in" versus "invented by DemoBot, <date>", plus the skill API version.

### Acceptance (F1)

- **Synthetic:** DemoBot forges `push` and `rotate`, each with ≥ 9/10 on fresh seeds and the regression gate green.
- **Real (live):** on `06_push_box`, the final program uses a forged skill, all verification checks pass, and the Toolkit shows the new skill.
- If the real clip has not arrived yet, use synthetic only and add the clips to "Waiting on you".

---

## F2: Live Twin, real time on open-weight SAM 3.1 (Modal GPU)

**The story:** "Point your phone at the table. The twin mirrors it live. Move anything, say 'do it', and the robot does the learned skill on what's actually there."

### Serving the open-weight SAM 3.1 on Modal

- Weights: `facebook/sam3.1` (SAM License), with code from the SAM 3 GitHub repository.
  - If Hugging Face requires accepting the licence, add a "Waiting on you" item: open the model page while logged in and click Agree.
  - `HF_TOKEN` in `.env` is used to download the weights.
- A Modal app class (`modal_apps/sam_live.py`):
  - GPU L4 or A10G (fall back to A100 if too slow);
  - weights cached in a Modal Volume;
  - `scaledown_window` 300 s;
  - `min_containers` 0, except during a live session, when `keep_warm` is pinged.
- Endpoint: `segment(jpeg_bytes, phrases[]) -> [{phrase, instances: [{box, mask_rle, score}]}]`, computing the image embedding **once per frame for all phrases**.
- Target: ≥ 4 frames/s server-side at 720p with ≤ 8 phrases.
- **GPU ledger:** record container seconds × price. Enforce the $30 sub-cap, and a judge-mode daily limit of 20 GPU-minutes.
- **Fallback:** if the open-weight deployment fails or is unavailable, use Meta API SAM 3.1 image mode at 0.5 Hz within the budget caps. The UI labels this "API mode".

### The live loop

1. **Browser** (the phone or laptop on `/live`, which needs HTTPS): `getUserMedia` with the rear camera. Send 640–720p JPEG frames over a WebSocket at up to 6 fps, with backpressure: drop frames while one is in flight.
2. **Backend:**
   - ArUco detection gives a per-frame homography, using the fixed marker layout from `table_photo.jpg`;
   - Modal SAM segments the frame;
   - masks are mapped to table cm with parallax correction;
   - instances are associated to objects (Hungarian matching on position and class, with a 3-frame confirmation and exponential smoothing);
   - the result is streamed as `twin_state` events at ≥ 2 Hz.
3. **Phrases:** the objects of the selected skill, plus up to 3 distractor phrases. "Add object" lets the user type one.
4. **"Run it now"** (button or voice "do it"):
   - freeze the current mirrored layout into a `Layout`;
   - run the selected skill's program in simulation;
   - animate the robot in the twin;
   - show the goal chips.

   This costs nothing beyond the GPU time.
5. **Pairing:** `/live` on the laptop shows a QR code with a session code. The phone opens `/live/cam?s=CODE` and becomes the camera, while the laptop shows the twin full-screen. Single-device mode (camera and twin on the phone) also works.
6. **Live replay mode:** feed a recorded clip through the exact same live path in real time. Used for the demo video and for testing without the human.

### Measured finding (add to eval)

On keyframes from the 5 real clips, compare open-weight SAM 3.1 on Modal against API SAM 3.1:
- mask IoU;
- centroid difference in cm;
- latency;
- cost per frame.

Report this in `eval/results.md` and the README.

### Acceptance (F2)

- **Live replay of `clip_01`:** twin updates ≥ 2 Hz; median position error < 2.5 cm against the offline pipeline; "Run it now" completes.
- **(live, human, 5 min):** a phone-camera session on the real table mirrors moved objects within about 1 s, and "Run it now" works. Claude adds this as a "Waiting on you" item with exact instructions when it is ready.

---

## F3: "Did you mean…?", resolving intent from a single demo

**The story:** "You put the two teal pens in the box, but the teal cutter was on the table too. Did you mean 'pens', or 'teal things'? DemoBot imagines both outcomes and asks you the one question that settles it."

### Steps

1. **Hypotheses.** After Watch and Ground, an intent analyst (Muse Wonder, effort high, one call) proposes 2–5 alternative goals in the goal DSL that are **also consistent with the demo**. It varies:
   - the selector type: name, kind, colour, role, region (e.g. "items left of the box"), count;
   - the relation, where ambiguous.

   Keep only the hypotheses that hold on the human's real final state (`goal_dsl.evaluate`) and that differ from each other on at least one layout.
2. **Goal solver** (`goal_solver.py`, no LLM): a deterministic planner that achieves any goal DSL on any layout using the skill API (`inside`, `relation`, `collinear`, `swapped`, `near`). It predicts each hypothesis's outcome cheaply and doubles as a baseline in eval.
3. **Contrastive probe.**
   - Generate 50–100 candidate layouts: random ones, red-team ones, and ones that add distractors which split the hypotheses (e.g. add a teal non-pen item, or a non-teal pen).
   - For each candidate, simulate every hypothesis with the goal solver.
   - Choose the layout that maximises the number of hypothesis pairs whose final states differ (an information-gain proxy), with ties broken by simplicity.
4. **Imagine.**
   - Render each hypothesis's outcome on the probe layout as a top-down twin image (exact).
   - **Muse Image** turns each render into a clean illustrated card captioned "If you meant <hypothesis in words>…", using an anchored edit of the exact render so object positions stay faithful.
   - Show the exact render beside each card ("imagined by Muse Image from the simulation").
5. **Ask.**
   - Spark 1.3 writes one short question with the options.
   - The UI shows the cards side by side. The user answers by click or voice (Voice Transcribe, then Spark maps the answer to an option).
   - With no answer within 60 s, pick the most specific consistent hypothesis and mark it as an assumption.
6. **Apply.**
   - If the chosen hypothesis changes the goal, use the Wonder correction mode (goal patch plus program edit), then rerun Verify and the red team.
   - Emit `intent_resolved` with the hypotheses before and after.

### UI

An "Intent" step in mission control:
- the hypotheses list, each with a consistency tick;
- the probe layout twin;
- the 2–4 image cards;
- the question with answer buttons and a mic;
- after answering, the goal diff and code diff.

### Acceptance (F3)

- On `clip_02` (one pen into the box, with a teal cutter and another pen present) or the synthetic pens clip: ≥ 2 consistent hypotheses, and a probe layout that separates them. The cards render.
- Answering "teal things" versus "pens" produces different goals and programs, both verified.
- A recorded replay of the whole interaction is baked for judge mode.

---

## Video and README v2 (after F1–F3)

- Re-cut the 3-minute video, still ≤ 3:00, replacing the weakest existing segments. New moments, about 20 s each:
  - **Forge:** capability gap → test grid → "Toolkit 6 → 8".
  - **Live:** the phone camera, the twin mirroring live, "do it".
  - **Did you mean:** two imagined outcome cards, then one question.
- Also render the 30-second cut again.
- **README:** a "Frontier features" section with the three stories, the measured numbers (forge pass rates, live Hz and error, open versus API SAM comparison, intent probe success), and their limitations.

## Cut rules if behind schedule

| If… | Then… |
| --- | --- |
| F1 is late | Ship `push` only; drop `rotate` and `stack` |
| F2 is late | Ship live replay mode only, on Modal open SAM. If the open SAM deployment fails, use API mode at 0.5 Hz. Drop phone pairing last. |
| F3 is late | Keep hypotheses, probe and question with exact renders; drop the Muse Image cards |

**Never** let any of these break the baseline demo, judge mode or the `v1-submittable` tag.
