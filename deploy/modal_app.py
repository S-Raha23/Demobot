"""DemoBot judge mode on Modal: FastAPI (API + built frontend + baked runs) as one ASGI web endpoint.

Deploy with `uv run python scripts/deploy_modal.py` (it creates the `demobot-keys` secret first).
The ledger lives on a Modal Volume, so the judge-mode daily caps survive restarts.
"""

from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parents[1]

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libgl1", "libglib2.0-0", "fonts-dejavu-core")
    .uv_sync(uv_project_dir=str(ROOT), frozen=True)
    .env(
        {
            "DEMOBOT_MODE": "judge",
            "DATA_DIR": "/data",
            "PYTHONPATH": "/app/backend:/app",
            "PYTHONUNBUFFERED": "1",
        }
    )
    .add_local_dir(
        ROOT / "backend" / "demobot", "/app/backend/demobot", ignore=["**/__pycache__/**"]
    )
    .add_local_dir(
        ROOT / "backend" / "tests" / "fixtures" / "runs", "/app/backend/tests/fixtures/runs"
    )
    .add_local_dir(
        ROOT / "backend" / "tests" / "fixtures" / "samples", "/app/backend/tests/fixtures/samples"
    )
    .add_local_dir(ROOT / "frontend" / "dist", "/app/frontend/dist")
    .add_local_dir(ROOT / "assets", "/app/assets")
    .add_local_file(ROOT / "docs" / "skill_api.md", "/app/docs/skill_api.md")
    .add_local_dir(ROOT / "eval", "/app/eval", ignore=["**/__pycache__/**"])
)

app = modal.App("demobot")
data = modal.Volume.from_name("demobot-data", create_if_missing=True)


@app.function(
    image=image,
    volumes={"/data": data},
    secrets=[modal.Secret.from_name("demobot-keys")],
    cpu=2.0,
    memory=4096,
    timeout=1800,
    max_containers=1,  # one live job at a time; in-process locks and the job runner stay simple
    scaledown_window=900,
)
@modal.concurrent(max_inputs=64)
@modal.asgi_app(label="demobot")
def web():  # type: ignore[no-untyped-def]
    from demobot.api import app as fastapi_app

    return fastapi_app
