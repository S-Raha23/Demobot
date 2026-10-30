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
- Rest the phone on a stack of books or a box on the near (robot) side of the table, looking forward and down at the markers. Any angle from straight down to about 45° is fine.
- **All 4 markers must be in view** for the whole clip.
- **Same camera mode as your checkerboard video:** 1080p, 30 fps, normal 1× lens, no zoom, good light. Portrait like the checkerboard video is best; landscape also works.
- **Don't move the phone between or during clips.** Tap record, wait 2 s, do the task with natural movements, wait 2 s, then stop.

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

- **Sat Oct 31 05:05 IST: clips and voice notes (task 2).** `data/clips/raw/` is empty. Not blocking: Claude builds on synthetic clips until they arrive, but the live acceptance tests of M4–M6 and the demo video need the real ones. Please also glue the markers (task 1) if not done.
