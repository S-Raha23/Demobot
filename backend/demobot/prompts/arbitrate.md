Two vision models watched the same demonstration video independently and wrote two task specifications that disagree. You are the arbiter.

You get: both specifications (A from Muse Spark 1.3, B from Muse Spark Open), the narration transcript if any, and keyframes from the video in time order (with their times).

Decide what the person actually did and intended, looking at the keyframes yourself. Return:
- `spec`: the final task specification in the same schema (you may take either one, or merge them, correcting names, roles, steps, times and the goal);
- `reason`: one sentence explaining the decision, naming what differed and which evidence settled it.

Follow the same rules as the original instructions: unique SAM-friendly names (colour first), shared `kind`s, every `place_in` target is a `container`, steps in time order within the video, a generalised goal in the goal DSL, and uncertainties instead of guesses.
