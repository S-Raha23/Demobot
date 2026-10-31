"""Create or update the Hugging Face Space (judge mode) from this repo (docs/07 "Judge mode").

    uv run python scripts/deploy_space.py [--no-secrets]

Keys are read through config.py and set as Space secrets; they are never printed. Only the files the
image needs are uploaded (allow-list below); .env, data/ and reference/ never leave the machine.
"""

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from huggingface_hub import HfApi  # noqa: E402

from demobot.config import settings  # noqa: E402

ALLOW = [
    "Dockerfile", "pyproject.toml", "uv.lock",
    "backend/demobot/**", "backend/tests/fixtures/runs/**", "backend/tests/fixtures/samples/**",
    "frontend/src/**", "frontend/public/**", "frontend/index.html", "frontend/package.json",
    "frontend/package-lock.json", "frontend/tsconfig.json", "frontend/vite.config.ts",
    "assets/print/markers.pdf", "assets/textures/**", "docs/skill_api.md", "eval/*.md", "eval/*.py",
]  # fmt: skip
IGNORE = ["**/__pycache__/**", "**/*.pyc", "**/.env*"]

SPACE_README = """---
title: DemoBot · Show it once
emoji: 🤖
colorFrom: indigo
colorTo: green
sdk: docker
app_port: 7860
pinned: true
short_description: Show a robot a tabletop task once, with a phone video.
---

# DemoBot: show it once

Film a tabletop task once with your phone. A team of agents on Meta's models (Muse Spark, SAM 3.1,
Muse Wonder, Muse Spark Open, Muse Voice, Muse Image) watches it, writes a robot program, tests it on
a simulated Franka Panda, attacks its own program and hardens it, and hands you a verified,
robot-agnostic skill.

- **Recorded runs** replay with their original timing (labelled as replays).
- **Try it** moves the objects in the 3D twin; the robot re-plans in simulation (free).
- **Live runs** on the sample clips and uploads run within a small daily budget.

The robot is simulated (PyBullet); no physical robot was used. Code: https://github.com/S-Raha23/Demobot
Built for the Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026).
"""

SECRETS = {
    "MODEL_API_KEY": "model_api_key", "BASETEN_API_KEY": "baseten_api_key",
    "MODAL_API_KEY": "modal_api_key", "MODAL_BASE_URL": "modal_base_url",
}  # fmt: skip
VARIABLES = {
    "DEMOBOT_MODE": "judge", "META_BASE_URL": settings.meta_base_url, "BASETEN_BASE_URL": settings.baseten_base_url,
    "MODEL_SPARK_OPEN": settings.model_spark_open, "MODEL_SPARK_OPEN_MODAL": settings.model_spark_open_modal,
    "MODAL_LLM": "1" if settings.modal_llm else "0",
}  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-secrets", action="store_true")
    a = ap.parse_args()
    if not settings.hf_token:
        sys.exit("HF_TOKEN is not set in .env")
    api = HfApi(token=settings.hf_token)
    user = api.whoami()["name"]
    repo = f"{user}/{settings.hf_space_name}"
    api.create_repo(repo, repo_type="space", space_sdk="docker", exist_ok=True)
    if not a.no_secrets:
        for env, attr in SECRETS.items():
            value = getattr(settings, attr)
            if value:
                api.add_space_secret(repo, env, value)
        for k, v in VARIABLES.items():
            api.add_space_variable(repo, k, v)
        print(
            f"set {sum(bool(getattr(settings, a)) for a in SECRETS.values())} secrets and {len(VARIABLES)} variables"
        )
    with tempfile.TemporaryDirectory() as tmp:
        readme = Path(tmp) / "README.md"
        readme.write_text(SPACE_README)
        api.upload_file(
            path_or_fileobj=str(readme), path_in_repo="README.md", repo_id=repo, repo_type="space"
        )
    api.upload_folder(folder_path=str(ROOT), repo_id=repo, repo_type="space", allow_patterns=ALLOW,
                      ignore_patterns=IGNORE, commit_message="Deploy DemoBot judge mode")  # fmt: skip
    print(f"https://huggingface.co/spaces/{repo}")


if __name__ == "__main__":
    main()
