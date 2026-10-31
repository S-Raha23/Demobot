# Probe results (M0)

Run: Sat Oct 31, 2026, 04:35–04:50 IST, by `scripts/probe_models.py`. Raw responses: `data/probe/results.json` (git-ignored). Test media: a PyBullet render (tray, duck, two cubes) as a 640×480 still and a 3 s, 10 fps, 30-frame clip in which the red cube slides into the tray; 5 s of phone audio for Voice.

**Cost of the whole probe batch:** Meta $0.057, Baseten $0.007, Modal $0.010 (LLM) plus about $0.01 of Sandbox time. **A full second run cost $0.00** on every provider: every call was a cache hit.

## Checklist (docs/03 PROBE items)

| Item | Answer |
| --- | --- |
| Meta hello on `muse-spark-1.3` | OK, 2.8 s. |
| Reasoning-effort field | `reasoning={"effort": "low"}` on the Responses API is accepted. |
| Reasoning tokens count in `max_output_tokens` | **Yes.** With `max_output_tokens=200` and effort `high`, the response is `status: incomplete`, `incomplete_details.reason: max_output_tokens`, 198 reasoning tokens, empty text. Keep ≥ 4,000 (16,000 for Watch). |
| Rate-limit headers | `x-ratelimit-limit-requests: 3000`, `x-ratelimit-limit-tokens: 4000000` (per minute), plus `x-ratelimit-remaining-*` and `x-request-id`. |
| Spark 1.3 video via `file_id` | Works: `files.create(purpose="user_data")`, then `{"type": "input_file", "file_id": ...}`. 3 s clip = 814 input tokens, 7 s wall. It described the motion correctly ("red cube moves … into the inside of the black tray"). |
| JSON schema with `$defs`/`$ref` | **Accepted** on Spark 1.3 (`text.format` json_schema with nested `$defs`). Output valid. `strict_schema()` is not needed for Meta. |
| Wonder function-calling loop | Works. First turn output: `reasoning`, `message`, `function_call` (`call_id`, `name`, `arguments` JSON string). Continue with `previous_response_id` + `function_call_output`. Cached tokens show up in turn 2 (500 of 1,026). |
| Images in a follow-up turn | Works: a user message with `input_image` (data URL) in the same `input` list as the `function_call_output`. |
| Wonder video input | **Works** via `input_file` + `file_id` ("The red cube moves left into the metal tray."). |
| Transient errors | One `503 persistence service error` on a Wonder follow-up; the gateway retry succeeded. Retries are needed. |
| SAM 3.1 image | Responses API, `input_text` (phrase) + `input_image` (data URL). 2.2 s. Usage reports `images_processed: 1`, tokens 0. |
| SAM 3.1 video via `file_id` | **Works** with `{"type": "input_video", "file_id": ...}`. 2.4 s for 30 frames, non-streamed. |
| SAM output format | Lines `<Nf>` (frame index) then records `ID<\|box;x1=..;y1=..;x2=..;y2=..;w=640;h=480\|><\|mask;x=0;y=0;data=H,W,~...\|>`. **Boxes are in pixels**; **`w`/`h` are the frame size**; the mask is `H,W` of the box crop with a lossless encoding. `meta_sam_parser` parses it (`image_segmentation_format()` / `video_segmentation_format()`, then `create_parser().push(text)` and `finish(...)`): boxes as `SegmentationBoxRecord(left, top, right, bottom, frame.frame_index)`, masks decodable with `decode_mask_to_raster`. Track ids are stable across frames (`object_id` "0"). |
| SAM billing per frame | Usage reports `video_frames_processed: 50` for a 30-frame clip (all 30 frames tracked). Bill from the reported `video_frames_processed`, not our frame count. To re-check on a longer clip in M5. |
| `mask_encoding` | Not needed: the default is already a compact lossless encoding the parser decodes. |
| Voice Transcribe round trip | Works: multipart `POST /v1/asr/transcribe` with parts `request` (JSON) and `audio` (WAV, mono 16 kHz s16). `languageBias` and `keywords` are accepted (no 400). Response: `{"sessionId", "transcript", "audioDurationMs", "turns": []}`. 4.2 s for 5 s audio. |
| Voice segment timestamps | **`turns` stays empty even with speech** in PUSH_TO_TALK mode (checked Sat 12:30 with synthesised English speech, transcribed perfectly). The code uses one segment spanning the audio. |
| Muse Image generate / edit | `images.generate(model="muse-image-1.0", prompt=...)` and `images.edit(model=..., image=file, prompt=...)` both work. Both return `data[0].b64_json` (**base64 WebP**, `output_format: "webp"`), no URL. Generate 24 s, edit 10 s. |
| Muse Image fast / no-search field | **None on the images endpoint**: `fast`, `web_search`, `enable_web_search`, `search` and `reasoning` are all rejected with `400 unknown parameter`. Accept the latency; generate cards in the background and cache them. |
| Baseten Spark Open | Hello OK (1.7 s). `response_format` json_schema with `strict: true` works. `image_url` data URLs work. `tools` work (OpenAI `tool_calls`). Reasoning comes back in a separate `reasoning_content` field, so `content` is clean. Prompt caching is reported (`cached_tokens`). |
| Modal Spark Open | Hello OK (1.9 s). json_schema works. Images work. `tools` work. **Video works** as `{"type": "video_url", "video_url": {"url": "data:video/mp4;base64,..."}}` (3 s clip = 756 video tokens) and described the motion correctly. |
| Modal billing hits the hackathon credit | **Yes.** `modal billing summary`: LLM Tokens $0.02, Credits −$0.02, Billed $0.00. `MODAL_LLM=1` stays. |
| Modal Sandbox | `modal.Sandbox.create("python", "-c", "import pybullet", image=debian_slim(3.11).pip_install("pybullet==3.2.6"))`: 12.4 s the first time (image build), **1.7 s** warm. Usable for the red-team pool. |

## Consequences for the code

- `providers.responses_call` raises `IncompleteResponse` on `status: incomplete`; the gateway retries it (billed).
- Watch and the Wonder loop send the strict Pydantic schema straight to Meta (`$defs` OK). Baseten and Modal get `strict_schema()` with `strict: true`.
- SAM: `perceive.parse_sam()` wraps `meta_sam_parser`; cost from `video_frames_processed` / `images_processed`.
- Cross-watch on Modal sends the 10 fps analysis clip as a `video_url` data URL (no keyframe fallback needed unless the clip is large).
- Muse Image: decode base64 WebP, convert to PNG; cards and textures are generated off the critical path.
