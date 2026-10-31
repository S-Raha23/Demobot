# HUMAN_TASKS: the only things the human has to do

Everything else is Claude Code's job. Claude adds items under **Waiting on you** only when it truly cannot continue without you, and keeps working on other things meanwhile.

## Once, today (about 45 minutes in total)

### 1. Glue the markers (10 min)

- Use the 4 ArUco markers you already printed (`assets/print/markers.pdf`, IDs 0–3, 6 cm).
- Glue them flat on your table at the corners of a rectangle of **roughly** 60 cm wide × 40 cm deep. **No measuring needed**: DemoBot measures their positions itself from the marker size.
- Seen from where the phone will stand (the "robot side"): ID 0 far-left, ID 1 far-right, ID 2 near-right, ID 3 near-left.
- Keep the area between them clear, on a plain matte surface if possible.

### 2. Film 5 short clips with things already on your desk (20 min)

**Phone setup:**
- Hold the phone in one hand from the near (robot) side of the table, looking forward and down at the markers, and do the task with the other hand. Any angle from straight down to about 45° is fine.
- **All 4 markers must be in view** for the whole clip, and not hidden behind tall items (keep the glue bottle, mug and box a hand's width away from the markers).
- **Same camera mode as your checkerboard video:** 1080p, 30 fps, normal 1× lens, no zoom, good light. Portrait like the checkerboard video is best; landscape also works.
- **Keep the phone as steady as you comfortably can** (small handheld motion is fine; DemoBot tracks it). Tap record, wait 2 s, do the task with natural movements, wait 2 s, then stop.

**Objects:** anything you have. One mug or bowl as the container, plus 2–4 small items such as pens, an eraser, a glue stick, a sticky-note pad, or a phone charger head. Nothing shiny or transparent if you can avoid it. No buying or hunting needed.

| Clip file name | Do this (10–25 s) | Speak while doing it (optional, but it powers a demo moment) |
| --- | --- | --- |
| `01_pens_in_mug.mp4` | Put 2 pens into the mug, one at a time | In **Hindi or Bengali**: "All the pens go in the mug." |
| `02_next_to.mp4` | Move the eraser so it sits just to the **right** of the mug | In English: "The eraser goes to the right of the mug." |
| `03_line_up.mp4` | Arrange 3 items into a straight row | Nothing |
| `04_sort.mp4` | Pens into the mug, and the other items into a second container (bowl, box or lid) | English or Hindi, anything natural |
| `05_swap.mp4` | Swap the places of two items, using a free spot in between | Nothing |

**Also record 2 voice notes** with your phone's recorder (5 s each): the correction "Put the eraser to the left of the mug instead," once in English and once in Bengali (or Hindi). Name them `correction_en.m4a` and `correction_bn.m4a`.

**Copy everything to `data/clips/raw/`** in the project. The project lives in Linux, so in Windows File Explorer go to `\\wsl.localhost\Ubuntu\home\soubh_raha24--\The_Demobot\data\clips\raw` (or run `explorer.exe data/clips/raw` in the VS Code terminal). Use USB, Google Drive or Nearby Share at original quality. **Not WhatsApp**: it shrinks the video.

### 3. Keys and logins (15 min)

1. Copy `.env.example` to `.env` and paste your keys: `MODEL_API_KEY`, `BASETEN_API_KEY`, `MODAL_API_KEY` + `MODAL_BASE_URL` (from your old setup or the Modal dashboard), and `HF_TOKEN` (Hugging Face → Settings → Access Tokens → new token with **write** access).
2. In WSL, in this folder, run these once:
   - `gh auth login` (GitHub, browser login)
   - `modal token new` (Modal, browser login)

   Claude creates the GitHub repo and the Space itself.
3. Make sure the credit forms are claimed. The Meta $150 form closes **Wed Nov 4, 9 PM ET**. Check Baseten and Modal credits on their billing pages.

### 4. Start Claude Code

Follow `PROMPT.md`.

## During the build (a few minutes a day)

- If Claude Code stops (its context is full, or your computer slept), restart it with the **resume prompt** in `PROMPT.md`.
- Glance at **Waiting on you** below about twice a day.

## At the end (Wed Nov 4, about 30 minutes)

1. Watch `media/demo/demo_final.mp4`. Optional: record a voiceover by reading the captions, save it as `media/demo/voiceover.wav`, and tell Claude to re-render.
2. Upload the video (YouTube, unlisted) and paste the link where Claude asks.
3. Submit on the Cerebral Valley platform using the text in `docs/submission-form.md`.
4. Post on X using the draft in `docs/10-submission.md` and the 30-second cut, then add the post link to the form.

## Status

- [x] 0. Checkerboard calibration video (1080×1920, 60 s) is in `data/calibration/checkerboard.mp4`

- [ ] 1. Markers glued
- [ ] 2. Clips and voice notes in `data/clips/raw/`
- [x] 3. `.env` filled (all 14 variables present); `gh` logged in (S-Raha23); Modal token present and the Modal credit covers LLM calls (checked Sat Oct 31 05:00 IST). Meta and Baseten credit pages not checkable by Claude.
- [x] 4. Claude Code started (Sat Oct 31, 04:30 IST)

## Waiting on you

(Claude adds items here, newest first, with the date and why it is blocking.)

- **Finish-remaining pass — your detailed checklist (do in this order, ~40 min total):**
  1. **Confirm the table (1 min, free):** are the 4 markers still glued flat? Tick Status 1 above. Clips 01–05 are already in the repo (Status 2 can be ticked) — only 06/07 below are missing.
  2. **Film 06/07 (10 min, free):** same setup as before (landscape, handheld, all 4 markers visible, 2 s still at start/end). `06_push_box.mp4`: slide the white box ~15 cm right with fingertips, do not lift. `07_rotate_cutter.mp4`: turn the teal cutter 90° in place. Copy both into `data/clips/raw/` (USB, original quality), then say "06 and 07 are in data/clips/raw/".
  3. **Re-run the push forge on your machine (paid, ~$1–3, 10 min):** the sandbox CPU is too slow (tests hit the 20 s limit, 10% is not a real result). In the VS Code terminal: `uv run python -m eval.forge_synth push`. Tell Claude the printed pass rate. Only if it says `promoted: True` will Claude flip `JUDGE_ACCEPTED`.
  4. **Browser checks on your machine (free, 10 min):** `make api` in one terminal; in another: `cd frontend && npm run e2e` (look at `frontend/test-results/*.png`; the stepper must not scroll sideways at 1366 px) and `npm run lighthouse` (desktop scores should be ≥ 70). Paste any failure text to Claude.
  5. **SAM licence (1 min, only if asked):** if Claude names a Hugging Face model page, open it logged in and click **Agree / Request access** (needed for F2 live weights).
  6. **Phone test (5 min, when Claude asks):** open `/live`, scan the QR with your phone, allow camera, move one object, check the twin follows within ~1 s, tap "do it". Report what happened.
  7. **Ship it (20 min):** watch `media/demo/demo_final.mp4` + `demo_30s.mp4`; upload the 3:00 cut to YouTube (unlisted); run `uv run python scripts/deploy_modal.py`; fill `docs/submission-form.md`, submit on Cerebral Valley, post on X with the 30 s cut.
  8. **Voice note (2 min, free):** record `correction_bn.m4a` ("put the eraser to the left instead", Bengali/Hindi) into `data/clips/raw/` — the last M10 gap.

- **Sat Oct 31 23:10 IST: frontier phase, 3 small tasks (not blocking; Claude builds with synthetic clips meanwhile).**
  1. **Film 2 more clips (about 10 min, same setup as before):** landscape, handheld from the near edge, all 4 markers visible, only your arm in frame, wait 2 s before and after.
     - `06_push_box.mp4`: **slide** the white box about 15 cm to the right with your fingertips. Don't lift it.
     - `07_rotate_cutter.mp4`: **turn** the teal cutter 90° where it lies (pick it up, rotate, put it back in the same spot).
     - Copy them by USB into `Downloads\demobot-print`, then in the VS Code terminal (change the source names):
       `cp "/mnt/c/Users/soubh/Downloads/demobot-print/VID_XXXX.mp4" ~/The_Demobot/data/clips/raw/06_push_box.mp4`
       `cp "/mnt/c/Users/soubh/Downloads/demobot-print/VID_YYYY.mp4" ~/The_Demobot/data/clips/raw/07_rotate_cutter.mp4`
     - Then tell Claude: "06 and 07 are in data/clips/raw/."
  2. **Accept the SAM 3.1 licence on Hugging Face (1 min, only if Claude asks):** open the model page Claude gives you while logged in and click **Agree / Request access**.
  3. **Live phone test (5 min, when Claude asks):** open `/live` on the laptop, scan the QR code with your phone, allow the camera, point it at the table, move one object and watch the twin follow, then say or click "do it". Tell Claude what happened.

- **Sat Oct 31 21:30 IST: the last steps (about 20 minutes).** Everything else is built and checked.
  1. Watch `media/demo/demo_final.mp4` (3:00) and `media/demo/demo_30s.mp4` (for X). Upload the 3:00 one to YouTube (unlisted).
  2. Redeploy once (`uv run python scripts/deploy_modal.py`) to pick up the last fix.
  3. (done Sat Oct 31) New repo https://github.com/S-Raha23/Demobot pushed; only you are listed as a contributor; it is already public.
  4. Fill the links in `docs/submission-form.md`, submit the form, post on X with the 30 s clip.


- (done Sat Oct 31, by you) Judge site deployed: https://soubhagyaraha24--demobot.modal.run (health, real replays, Try-it and the markers PDF checked by Claude). Redeploy once more with the same command to pick up the corrected-skill descriptions: `uv run python scripts/deploy_modal.py`.
- (old) **Sat Oct 31 14:10 IST: deploy the judge site (2 minutes, one command).** Hugging Face now charges (PRO, $9/month) for any Docker Space, so DemoBot deploys to **Modal** instead, on the Modal credits you already have. Claude Code's safety check does not let Claude run a production deploy itself. In the VS Code terminal run:
  `cd ~/The_Demobot && uv run python scripts/deploy_modal.py`
  It builds the frontend, stores your keys as a Modal secret (never printed), deploys, and prints the URL (`https://<workspace>--demobot.modal.run`). Then tell Claude the URL. (Prefer Hugging Face? Subscribe to PRO and run `uv run python scripts/deploy_space.py` instead.) To let Claude redeploy updates later by itself, add `"Bash(uv run python scripts/deploy_modal.py)"` to the allow list in `.claude/settings.local.json`.
- (done Sat Oct 31) Git re-initialised and pushed to the new repo, commits authored by you only (no Claude trailer).
- (done Sat Oct 31 18:00 IST) Clips and voice notes received: clip_01–05, table_photo.jpg, voice_1.m4a (Hindi: "green ball cup के अंदर रखो"), voice_2.m4a (English: "put the green ball in the tub."). The marker layout is fitted once from the photo + clip_01 and all five clips calibrate (0.45–1.06 px).