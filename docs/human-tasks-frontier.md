# Human tasks for the frontier upgrades

Claude merges these into `HUMAN_TASKS.md`. Do them when convenient; Claude keeps building with synthetic clips meanwhile.

## 1. Film 2 more clips (about 10 min, same setup as before)

Same rules as before:
- landscape, handheld from the near edge;
- all 4 markers visible;
- only your arm in the frame;
- wait 2 s before and after.

| File | Do this |
| --- | --- |
| `06_push_box.mp4` | **Slide** the white box along the table with your fingertips, about 15 cm to the right. Don't lift it. |
| `07_rotate_cutter.mp4` | **Turn** the teal cutter 90° where it lies: pick it up, rotate it, put it back in the same spot. |

Copy them by USB into `Downloads\demobot-print`, then run this in the VS Code terminal (change the source names to your new files):

```bash
cp "/mnt/c/Users/soubh/Downloads/demobot-print/VID_XXXX.mp4" ~/The_Demobot/data/clips/raw/06_push_box.mp4
cp "/mnt/c/Users/soubh/Downloads/demobot-print/VID_YYYY.mp4" ~/The_Demobot/data/clips/raw/07_rotate_cutter.mp4
```

Then tell Claude: "06 and 07 are in data/clips/raw/."

## 2. Accept the SAM 3.1 licence on Hugging Face (1 min, only if Claude asks)

Open the model page Claude gives you while logged in to Hugging Face, and click **Agree / Request access**.

## 3. Live test with your phone (5 min, when Claude asks)

1. Open the `/live` page on the laptop.
2. Scan the QR code with your phone, allow camera access, and point the phone at the table.
3. Move one object and watch the twin follow it. Say or click "do it".
4. Tell Claude what happened.
