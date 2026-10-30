# 01. Vision: DemoBot, "Show it once"

## The problem

Most of the world's small workshops, labs, warehouses and kitchens will never automate a task, because programming a robot arm takes a specialist. To be useful to everyone else, a robot has to learn the way a person does: by watching someone do the task once.

## What DemoBot does

You film yourself doing a tabletop task once with a phone, for example "put the pens in the mug". Optionally you narrate it in English, Hindi or Bengali. Then a team of AI agents built on Meta's models takes over:

1. **Watches** the video and understands the intent, not just the motions.
2. **Tracks** every object and your hand, pixel-precise, and measures where things went in real centimetres.
3. **Writes a robot program** that generalises the task ("every pen goes in the mug, wherever it is").
4. **Tests that program** on a simulated Franka Panda arm, debugs it, and rewrites it until it works.
5. **Checks itself with the same eyes:** the simulated result is judged by the same perception models that watched the human.
6. **Attacks its own program.** A swarm of open-weight agents invents tricky new table layouts to break it, and the program is hardened until it survives them.
7. **Takes spoken corrections:** "No, the eraser goes to the left of the mug."
8. **Delivers a skill:** a verified, robot-agnostic program, an illustrated skill card, and a 3D digital twin you can play with. Drag the objects anywhere and the robot adapts live.

## The model map: every Meta model where it is strongest

| Capability | Meta model | Its job in DemoBot | Why this model |
| --- | --- | --- | --- |
| Watch | **Muse Spark 1.3** (video input) | Turns the demo video plus narration transcript into a `TaskSpec`: objects, timestamped steps, a declarative goal and a generalisation rule. Also answers targeted "rewatch" questions from the supervisor. | Native video understanding, structured output, reasoning |
| Listen | **Muse Voice Transcribe** | Transcribes narration inside the clip and live spoken corrections (English, Hindi, Bengali) | Multilingual STT built for push-to-talk and realtime |
| See | **SAM 3.1** (video and image) | Text-prompted masks and persistent track IDs for every object and the hand. Also segments the **simulator's render** to close the perception loop. | The only model here that gives pixel-precise, identity-preserving tracks |
| Program | **Muse Wonder** (agentic coding with tools) | Writes the robot program and debugs it through tool calls: simulate, inspect, check reach. Also hardens the program against red-team failures and applies voice corrections as code edits. | Meta's frontier model for long-horizon agentic coding |
| Supervise | **Muse Spark Open** (open weights, Baseten; Modal fallback) | The supervisor agent: decides how to recover when checks disagree, using tool calls | Runs often and cheaply, open weights |
| Red team | **Muse Spark Open** swarm (Baseten, parallel) | Six adversarial "personas" each propose hard layouts to break the program | High-throughput parallel generation (Baseten 2M TPM) on open weights |
| Judge | **Muse Spark Open** (images) | Compares the real final frame with the simulated final render | Cheap visual judgement, open weights |
| Second opinion | **Muse Spark Open on Modal** (video) | Watches the same clip independently. Disagreement with Spark 1.3 triggers Wonder arbitration. | Open-weight video path; a measured cross-model agreement number |
| Illustrate | **Muse Image** | Illustrated skill cards anchored on the real final frame; realistic object textures for the synthetic test generator; (stretch) an "imagined result" preview | Accurate text rendering, anchored editing, $0.01 per image |
| Build | Claude Code (build tool only) | Writes this repository | Not part of the product |

**Open-weight share:** the supervisor, red team and judge (the highest-volume calls) all run on Muse Spark Open. The UI shows a live meter of open-weight versus API calls and spend. This supports the "Best Build on Open Weight Models" bonus.

## The six moments judges must see (the demo is built around them)

1. **"It watched me once."** The real video shows glowing SAM masks with track IDs and motion trails. A timeline shows each step and every grasp and release. A Hindi narration appears as captions.
2. **"It wrote its own robot program."** Wonder's code streams in. Tool calls to the simulator appear, the tests go red then green, and an iteration counter climbs. A program diff is shown for every fix.
3. **"It checks itself with the same eyes."** The real final frame sits beside the digital twin rendered from the same camera angle. SAM masks appear on both. Three checks all turn green: symbolic, real-world, and perceptual.
4. **"It attacks itself."** Twelve mini twins show adversarial layouts. Robustness reads 7/12. Wonder hardens the program and it rises to 12/12.
5. **"Talk to it."** A spoken correction in Bengali produces a code diff, and the robot complies.
6. **"Your turn."** A judge drags the mug to a new spot in the 3D twin and the robot re-plans and does it, live and free (no paid calls).

## Judging map

| Criterion (weight) | How we win it |
| --- | --- |
| Impact (30%) | Programming by demonstration for anyone with a phone. The exported program is robot-agnostic. Measured robustness and cost per skill. Global framing: small businesses, labs and assistive robotics. |
| Meta AI tooling (25%) | Six Meta models, each used for its distinctive strength. Agentic tool use on Wonder and Spark Open. Video, audio, image and segmentation all in one loop. Open weights in high-volume roles. |
| Demo (25%) | The six moments above, a live interactive twin in judge mode, a clean 3-minute video, and no dead air (event replay). |
| Technical depth (20%) | Ruler-free metric calibration, persistent tracking with contact events, code synthesis with simulator-in-the-loop, three-way verification, adversarial hardening, sandboxed execution, full cost ledger and eval numbers. |

Bonus prizes targeted: Best Agentic Use-Case, Best Build on Open Weight Models, Best Creative Build (Muse Image / Wonder), Most Viral, Community Vote.

## Scope

**In scope:** rigid tabletop pick-and-place rearrangement with 2–6 everyday objects, using one fixed phone camera (top-down or angled up to about 50° from vertical). The four ArUco markers must be visible. Task families:
- put into a container
- place next to an object (left, right, in front, behind)
- line up
- sort by kind into containers
- swap
- any composition of these

**Out of scope:**
- stacking
- deformables, liquids, tools that need force
- a moving camera
- real robot hardware (we export a robot-agnostic program instead)
- any people or face identification (we track hands only)

**Objects:** whatever is on the human's desk: a mug or bowl as a container, plus pens, an eraser, a glue stick, a sticky-note pad and so on. No coloured blocks needed. SAM is open-vocabulary, so names matter, not colours.
