#!/usr/bin/env python3
"""Stop hook: keeps Claude Code working until The_Demobot is finished.

Claude may stop only when the first lines of PROGRESS.md contain
'PROJECT_STATUS: DONE' or 'PROJECT_STATUS: BLOCKED_ON_HUMAN', or when the
human creates the file .claude/ALLOW_STOP. Safety cap: 400 continuations per session.
"""
import json
import os
import pathlib
import re
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    data = {}

root = pathlib.Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))
if (root / ".claude" / "ALLOW_STOP").exists():
    sys.exit(0)

progress = root / "PROGRESS.md"
text = progress.read_text(encoding="utf-8", errors="ignore") if progress.exists() else ""
if re.search(r"^PROJECT_STATUS:\s*(DONE|BLOCKED_ON_HUMAN)\b", text, re.M):
    sys.exit(0)

session = re.sub(r"[^A-Za-z0-9_-]", "", str(data.get("session_id", "default")))[:64] or "default"
counter = root / ".claude" / f".keep_going_{session}"
count = int(counter.read_text()) if counter.exists() else 0
if count >= 400:
    sys.exit(0)
counter.write_text(str(count + 1))

print(json.dumps({
    "decision": "block",
    "reason": (
        "Do not stop: The_Demobot is not finished. Update PROGRESS.md if needed, "
        "then immediately continue with the next unfinished milestone in docs/08-build-plan.md "
        "(or the next step of the current one). Do not wait for the human and do not summarise. "
        "You may stop only by setting 'PROJECT_STATUS: DONE' (Definition of Done in CLAUDE.md met) "
        "or 'PROJECT_STATUS: BLOCKED_ON_HUMAN' (truly nothing can progress without the human; "
        "synthetic clips and fixtures exhausted) at the top of PROGRESS.md."
    ),
}))
