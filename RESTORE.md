# Restore point — known-good GitHub + website state

This file pins the exact submission-ready state so it can always be recovered,
whatever happens later.

| What | Value |
| --- | --- |
| **Tag (use this)** | `known-good-github-2026-11-01` |
| **Commit at the tag** | the commit that adds this file; the code commit beneath it is `f8269a4` ("Install ffmpeg in CI") |
| **Date** | Sun Nov 1, 2026 (IST) |
| **GitHub** | https://github.com/S-Raha23/Demobot (`main`, in sync) |
| **Live website** | https://soubhagyaraha24--demobot.us-east.modal.run (Modal app `demobot`, judge mode, health `ok`) |
| **CI** | GitHub Actions run 41256556266 — **success** (202 backend + 19 frontend tests) |
| **Judge verdict** | GitHub presentation **9.6/10 — TOP: YES** (conditional only on the human uploading the demo video) |
| **Only unfinished item** | Demo video link in README (human upload) |

## Get this exact code back

```bash
git fetch --tags
git switch --detach known-good-github-2026-11-01   # look, don't edit
# or, to work from it:
git switch -c restore-known-good known-good-github-2026-11-01
```

## Get this exact website back

The site is deployed from this code. From a checkout of the tag:

```bash
uv run python scripts/deploy_modal.py
curl -s https://soubhagyaraha24--demobot.us-east.modal.run/api/health
```

Expected health reply starts `{"ok":true,"mode":"judge",...}`.

## Older restore points (also tagged)

- `v1-submittable` — complete baseline submission (Gate 0).
- `known-good-submit` — earlier known-good point confirmed by the human.
