# 03. Models, APIs, probes and budget

Facts here came from Meta's docs, participant notes and our own Oct 28 hello tests. Anything marked **PROBE** must be confirmed by `scripts/probe_models.py` in M0. The script writes its findings to `docs/probe-results.md`, and code that depends on a probed fact is isolated in one function.

## Endpoints and keys (`.env`)

| Provider | Base URL | Key env var | API style |
| --- | --- | --- | --- |
| Meta Model API | `https://api.meta.ai/v1` | `MODEL_API_KEY` | OpenAI Responses and Chat Completions; Anthropic Messages at `https://api.meta.ai` |
| Baseten | `https://inference.baseten.co/v1` | `BASETEN_API_KEY` | OpenAI Chat Completions; model name **exactly** `meta-models/muse-spark-open-1026` |
| Modal Shared Endpoint | `MODAL_BASE_URL` (from the Modal dashboard) | `MODAL_API_KEY` (workspace proxy token, format `wk-<id>.ws-<secret>`, used as the bearer) | OpenAI Chat Completions; model `meta-models/Muse-Spark-Open-816B-A42B` (endpoint was named `muse-spark-open-816b-a42b` in the Oct 28 hello test) |
| Modal Sandboxes | Modal SDK | `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` (`modal token new` stores them in `~/.modal.toml`) | Python SDK |

## Model facts and how DemoBot uses each

### Muse Spark 1.3: `muse-spark-1.3` ($1.25 in / $0.15 cached / $4.25 out per M tokens)

- **Inputs:** text, image, video and PDF; 1M-token context; tool calling; structured output; always reasons.
- **Video:** upload the MP4 with `files.create(file=..., purpose="user_data")` and pass it as `{"type": "input_file", "file_id": ...}` in a Responses `input` message.
- **Audio:** Spark also hears the soundtrack, but **audio in 1.3 is degraded**. We transcribe narration with Voice Transcribe and pass the text.
- **Output budget:** reasoning tokens consume `max_output_tokens`. Keep it ≥ 4,000, and use 16,000 for Watch, or answers come back empty with `status: incomplete`.
- **Reasoning effort:** values are `minimal`, `low`, `medium`, `high`, `xhigh`. On the Responses API it is probably `reasoning={"effort": ...}` (**PROBE** the field name).
- **Structured output:** `text={"format": {"type": "json_schema", "name": ..., "schema": ...}}`. **PROBE** whether `$defs`/`$ref` are accepted; otherwise send `strict_schema()` (inline refs, no defaults, `additionalProperties: false`).
- **Uses:**
  - Watch, at effort `high`.
  - Rewatch tool: a targeted question about a time window, effort `medium`.
  - The run narrative for the report, effort `low`.
  - The final fallback for the judge and supervisor.
- `muse-spark-1.3-contributor` ($0.10/$0.20) trains on your data. Do not use it by default; offer it as an opt-in switch for bulk eval only.

### Muse Wonder: `muse-wonder-1.0` ($4 in / $0.20 cached / $20 out per M)

- Frontier agentic and coding model; text, image, video and audio input; 1M context.
- Always reasons: `reasoning effort: none` returns HTTP 400.
- **Uses:** program synthesis with tool calls (`docs/05-agents.md`), hardening, voice-correction edits, and arbitration when Spark 1.3 and Spark Open disagree on Watch.
- **Tool loop:** Responses API with `tools=[{"type": "function", ...}]`; continue with `previous_response_id` plus `function_call_output` items. **PROBE** that this works on Meta, and whether images can follow in a user message in the same turn.
- **Video input** to Wonder: **PROBE**. Default: send 6–8 keyframes as images.
- Use prompt caching: keep the long system prompt and skill API docs as a stable prefix.

### SAM 3.1: `sam-3.1` ($0.20 per 1k video frames; $2.50 per 1k images)

- Called through the Responses API. **One short noun phrase per request** ("pen", "coffee mug", "hand"). Plural or vague phrases fail.
- Returns boxes, masks (ask for `mask_encoding: one_bit`) and persistent track IDs across video frames. At most 16 objects per request.
- Output is a special-token grammar. Decode it with `meta-sam-parser` and wrap that in `perceive.parse_sam()`.
- **Never run SAM video jobs in parallel.** A participant measured one concept on a 42-frame clip at 19.6 s, but two concepts at once on the same clip took 104 s. Run phrases **sequentially**.
- Measured speeds: an image at 960 px took about 2 s; video about 0.5 s per frame.
- **PROBE:**
  - whether an uploaded `file_id` is accepted for video (`{"type": "input_video", "file_id": ...}`);
  - whether every frame is billed or only processed frames;
  - box units: pixels or normalised;
  - whether `w=`/`h=` in the output are frame size.
- **Uses:**
  - track every TaskSpec object plus "hand" on the 10 fps analysis clip;
  - image mode on the human's final frame;
  - **image mode on the simulator's render** (perceptual verification);
  - re-tracking with `alt_names` when quality is low.

### Muse Voice Transcribe: `muse-voice-transcribe-1.0` ($0.18 per audio hour)

- Batch: multipart `POST {base}/asr/transcribe` via `httpx`, with parts:
  - `request` = JSON `{"model": "muse-voice-transcribe-1.0", "mode": "PUSH_TO_TALK", "audioEncoding": "WAV", "languageBias": ["English", "Hindi", "Bengali"], "keywords": [object names]}`
  - `audio` = the WAV file.

  The response field is `transcript` (**PROBE** the timestamp and segment fields and the `languageBias` name).
- Realtime: `wss://api.meta.ai/v1/asr/realtime` (optional; push-to-talk is enough).
- Audio must be mono 16-bit PCM WAV at 16 or 24 kHz, at most 10 minutes. Convert with ffmpeg.
- **Uses:** narration in demo clips, and spoken corrections from the browser microphone.

### Muse Image: `muse-image-1.0` ($0.01 per image)

- Agentic image generation and editing that reasons before rendering. Strong at text and fine detail. Anchored composition and multi-turn refinement.
- Surfaces:
  - OpenAI-style images endpoints, generate and edit (**PROBE** the exact paths and `stream`);
  - or the Responses API with the `image_generation` tool, which is the only tool it accepts.
- It runs web search by default. Turn that off for speed (the participant notes call this `fast=True`; **PROBE** the real field name).
- It refuses some words, e.g. prompts containing "burnt".
- **Uses:**
  - skill cards: an anchored edit of the real final frame into a clean illustrated card with the title and 3 short numbered steps;
  - realistic top-down **object textures** for the synthetic clip generator, generated once and saved in `assets/textures/` (committed);
  - (stretch) the "imagined result" preview for a new layout.

### Muse Spark Open: open weights, 816B MoE with 42B active

- **Baseten** (`meta-models/muse-spark-open-1026`):
  - Chat Completions; 2M TPM; $100 credit.
  - Images go as `image_url` data URLs (512 px JPEG, quality 85).
  - `response_format` with `json_schema`: **PROBE**; the fallback is `json_object` plus the schema in the prompt.
  - Tool calling with `tools`: **PROBE**; the fallback is a JSON "action" schema.
  - Returns reasoning text: strip it before parsing JSON.
- **Modal** (`meta-models/Muse-Spark-Open-816B-A42B`):
  - also accepts **video** as `{"type": "video_url", "video_url": {"url": "data:video/mp4;base64,..."}}` (**PROBE** the format; fallback is 8 keyframes);
  - send a `Modal-Routing-Affinity-Key` header per run;
  - **PROBE** that the hackathon credit covers Shared Endpoint usage. Modal docs say plan credits may not. If not, disable Modal LLM use (`MODAL_LLM=0`) and keep Modal for Sandboxes only.
- **Uses:** the supervisor agent, the red-team swarm (parallel), the visual judge, and the cross-watch second opinion (Modal, video).

### Muse Glimmer 30B (open weights, Apache 2.0): stretch only

An optional offline judge served with vLLM on a Modal GPU (`docs/08-build-plan.md`, S2).

## Purpose → model → provider chain

| Purpose | Primary | Fallback chain | Effort / limits | Estimate per call |
| --- | --- | --- | --- | --- |
| `watch` | Spark 1.3 (video) | Wonder with keyframes | high, max_out 16k | ~$0.17 |
| `crosswatch` | Spark Open @ Modal (video) | Spark Open @ Baseten with keyframes, then skip | max 8k | ~$0.10 |
| `arbitrate` | Wonder (keyframes + both specs) | Spark 1.3 high | max 16k | ~$0.40 |
| `listen` | Voice Transcribe | none (no narration) | n/a | <$0.01 |
| `track:<phrase>` | SAM 3.1 video | the same phrase on keyframes in image mode | sequential | frames × $0.0002 |
| `segment_image` | SAM 3.1 image | none | n/a | $0.0025 |
| `synth` / `harden` / `correct` | Wonder tool loop | Spark 1.3 high tool loop | ≤ 8 tool turns | ~$0.25 per turn |
| `supervise` | Spark Open @ Baseten | Modal, then Spark 1.3 | ≤ 4 decisions | ~$0.02 per decision |
| `redteam:<persona>` | Spark Open @ Baseten (parallel) | Modal | 6 personas × 2 layouts | ~$0.02 each |
| `judge` | Spark Open @ Baseten (2 images) | Modal, then Spark 1.3 low | n/a | ~$0.03 |
| `rewatch` | Spark 1.3 (video window) | none | medium | ~$0.08 |
| `card` / `texture` | Muse Image | skip card (UI shows the final frame) | fast mode | $0.01 |
| `narrative` | Spark 1.3 | template text | low | ~$0.01 |

## Budget caps (enforced by `budget.py`; never raise them)

| Pool | Credit | Hard cap | Dev daily cap | Judge daily cap |
| --- | --- | --- | --- | --- |
| Meta Model API | $150 | **$130** total | $40 | $6 |
| Baseten | $100 | **$90** | $35 | $5 |
| Modal (LLM endpoint + Sandboxes) | ~$130 | **$110** | $40 | $5 |

Meta has **no hard spend limit**, only email alerts, and spend past the credit is charged to the card. Participants report that a spend-limit notification does not stop billing. The ledger is the only safety. `make costs` prints the ledger; reconcile it against the dashboards once a day and record the result in PROGRESS.md.

Expected cost per learned skill: Watch, then SAM on 5 phrases × ~200 frames, then Wonder at ~6 turns, then stress plus harden, then the card. **About $2–4.** Budget for about 25 full live runs during development. Everything after that is cache hits and replays.

## PROBE checklist (M0 writes the answers to `docs/probe-results.md`)

- [ ] Meta hello on `muse-spark-1.3`; reasoning-effort field; reasoning tokens counted in `max_output_tokens`; rate-limit headers
- [ ] Spark 1.3 video via `file_id`; JSON-schema acceptance (`$defs`)
- [ ] Wonder: function-calling loop with `previous_response_id`; images in follow-up turns; video input yes or no
- [ ] SAM 3.1: image call on a test frame; video call via `file_id`; output format (units, `w`/`h`, mask encoding); billing per frame
- [ ] Voice Transcribe: 5 s WAV round trip; `languageBias` field; segment timestamps
- [ ] Muse Image: generate and edit endpoints; fast / no-search field; returned format (URL or base64)
- [ ] Baseten Spark Open: hello; `json_schema`; images; `tools`
- [ ] Modal Spark Open: hello; video part; `json_schema`; billing hits the hackathon credit
- [ ] Modal Sandbox: create, run `python -c "import pybullet"` with a custom image, and measure cold-start time
