"""Deploy DemoBot judge mode to Modal.

    uv run python scripts/deploy_modal.py

Builds the frontend, (re)creates the `demobot-keys` Modal secret from .env through config.py (values
are never printed), then runs `modal deploy deploy/modal_app.py`.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import modal  # noqa: E402

from demobot.config import settings  # noqa: E402

KEYS = {
    "MODEL_API_KEY": settings.model_api_key, "BASETEN_API_KEY": settings.baseten_api_key,
    "MODAL_API_KEY": settings.modal_api_key, "MODAL_BASE_URL": settings.modal_base_url,
    "META_BASE_URL": settings.meta_base_url, "BASETEN_BASE_URL": settings.baseten_base_url,
    "MODEL_SPARK_OPEN": settings.model_spark_open, "MODEL_SPARK_OPEN_MODAL": settings.model_spark_open_modal,
    "MODAL_LLM": "1" if settings.modal_llm else "0",
}  # fmt: skip


def main() -> None:
    subprocess.run(["npx", "vite", "build"], cwd=ROOT / "frontend", check=True)
    env = {k: v for k, v in KEYS.items() if v}
    try:
        modal.Secret.objects.delete("demobot-keys")
    except Exception:
        pass
    modal.Secret.objects.create("demobot-keys", env)
    print(f"secret demobot-keys: {len(env)} values set")
    subprocess.run(["modal", "deploy", "deploy/modal_app.py"], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
