"""HTTP API (docs/02 "HTTP API"). Grows milestone by milestone."""

from importlib.metadata import version

from fastapi import FastAPI

from demobot import budget
from demobot.config import PROVIDERS, settings

app = FastAPI(title="DemoBot", version=version("demobot"))


@app.get("/api/health")
def health() -> dict[str, object]:
    mode = settings.demobot_mode
    headroom = {} if mode == "replay" else {p: budget.remaining(mode, p) for p in PROVIDERS}
    return {"ok": True, "mode": mode, "version": app.version, "headroom_usd": headroom}
