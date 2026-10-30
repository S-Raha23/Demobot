"""Fail if any key leaks into the repo. Prints file names and rule names only, never values.

uv run python scripts/secret_scan.py            # files git would commit (tracked + untracked)
uv run python scripts/secret_scan.py --history  # every commit on every branch
"""

import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from demobot.config import settings  # noqa: E402

PATTERNS = {
    "modal_proxy_token": re.compile(r"wk-[A-Za-z0-9]{6,}\.ws-[A-Za-z0-9]{6,}"),
    "modal_token_secret": re.compile(r"\bas-[A-Za-z0-9]{16,}"),
    "hf_token": re.compile(r"\bhf_[A-Za-z0-9]{30,}"),
    "openai_style_key": re.compile(r"\bsk-[A-Za-z0-9_-]{24,}"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}


def known_secrets() -> dict[str, str]:
    """The real key values from .env and ~/.modal.toml (compared, never printed)."""
    out = {
        name: value
        for name in ("model_api_key", "baseten_api_key", "modal_api_key", "hf_token")
        if (value := getattr(settings, name)) and len(value) >= 12
    }
    modal = Path.home() / ".modal.toml"
    if modal.exists():
        for profile, conf in tomllib.loads(modal.read_text()).items():
            if isinstance(conf, dict):
                for k in ("token_id", "token_secret"):
                    if isinstance(conf.get(k), str) and len(conf[k]) >= 12:
                        out[f"modal_{profile}_{k}"] = conf[k]
    return out


def scan_text(text: str, secrets: dict[str, str]) -> list[str]:
    hits = [name for name, value in secrets.items() if value in text]
    hits += [name for name, rx in PATTERNS.items() if rx.search(text)]
    return hits


def main() -> int:
    secrets = known_secrets()
    problems: list[str] = []
    if "--history" in sys.argv:
        log = subprocess.run(
            ["git", "log", "-p", "--all", "--no-color"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            errors="replace",
        ).stdout
        problems += [f"git history: {h}" for h in scan_text(log, secrets)]
    else:
        files = subprocess.run(
            ["git", "ls-files", "-co", "--exclude-standard"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        ).stdout.split()
        for f in files:
            p = ROOT / f
            if not p.is_file() or p.stat().st_size > 5_000_000 or f == ".env.example":
                continue
            try:
                text = p.read_text(errors="ignore")
            except OSError:
                continue
            problems += [f"{f}: {h}" for h in scan_text(text, secrets)]
    if problems:
        print("SECRET SCAN FAILED:", *problems, sep="\n  ")
        return 1
    print(f"secret scan clean ({len(secrets)} known keys checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
