"""Settings from the environment and `.env`. The only module that reads keys (CLAUDE.md rule 5)."""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderName = Literal["meta", "baseten", "modal"]
PROVIDERS: tuple[ProviderName, ...] = ("meta", "baseten", "modal")

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", extra="ignore", protected_namespaces=()
    )

    # Meta Model API
    model_api_key: str | None = None
    meta_base_url: str = "https://api.meta.ai/v1"

    # Baseten (Muse Spark Open)
    baseten_api_key: str | None = None
    baseten_base_url: str = "https://inference.baseten.co/v1"
    model_spark_open: str = "meta-models/muse-spark-open-1026"

    # Modal Shared Endpoint (Muse Spark Open, also video)
    modal_api_key: str | None = None
    modal_base_url: str | None = None
    model_spark_open_modal: str = "meta-models/Muse-Spark-Open-816B-A42B"
    modal_llm: bool = True

    hf_token: str | None = None
    hf_space_name: str = "the-demobot"

    # app
    demobot_mode: Literal["dev", "replay", "judge"] = "dev"
    demobot_fixtures: bool = False
    data_dir: str = "data"
    fixtures_dir: str = "backend/tests/fixtures/responses"
    log_level: str = "INFO"

    # Meta models
    model_spark: str = "muse-spark-1.3"
    model_wonder: str = "muse-wonder-1.0"
    model_sam: str = "sam-3.1"
    model_asr: str = "muse-voice-transcribe-1.0"
    model_image: str = "muse-image-1.0"

    # caps (docs/03-models.md; never raise them)
    cap_meta_total_usd: float = 130
    cap_meta_dev_daily_usd: float = 40
    cap_meta_judge_daily_usd: float = 6
    cap_baseten_total_usd: float = 90
    cap_baseten_dev_daily_usd: float = 35
    cap_baseten_judge_daily_usd: float = 5
    cap_modal_total_usd: float = 110
    cap_modal_dev_daily_usd: float = 40
    cap_modal_judge_daily_usd: float = 5

    # versions that go into every cache key
    prompt_version: str = "p1"
    schema_version: str = "s1"

    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir)
        return p if p.is_absolute() else ROOT / p

    @property
    def fixtures_path(self) -> Path:
        p = Path(self.fixtures_dir)
        return p if p.is_absolute() else ROOT / p

    @property
    def db_path(self) -> Path:
        return self.data_path / "ledger.db"

    def cap(self, provider: str, kind: str) -> float:
        """kind is total, dev_daily or judge_daily."""
        return float(getattr(self, f"cap_{provider}_{kind}_usd"))


settings = Settings()


# USD, from Meta's pricing page (Oct 2026). Baseten and Modal price Spark Open the same.
PRICES: dict[str, dict[str, float]] = {
    "muse-spark-1.3": {"in": 1.25e-6, "cached": 0.15e-6, "out": 4.25e-6},
    "muse-spark-1.3-contributor": {"in": 0.10e-6, "cached": 0.002e-6, "out": 0.20e-6},
    "muse-wonder-1.0": {"in": 4.00e-6, "cached": 0.20e-6, "out": 20.0e-6},
    "meta-models/muse-spark-open-1026": {"in": 1.25e-6, "cached": 1.25e-6, "out": 4.25e-6},
    "meta-models/Muse-Spark-Open-816B-A42B": {"in": 1.25e-6, "cached": 0.15e-6, "out": 4.25e-6},
    "sam-3.1": {"video_frame": 0.20e-3, "image": 2.50e-3},
    "muse-voice-transcribe-1.0": {"audio_hour": 0.18},
    "muse-image-1.0": {"image": 0.01},
}

# Models whose weights are open; the UI's open-weight meter counts these.
OPEN_WEIGHT_MODELS = {"meta-models/muse-spark-open-1026", "meta-models/Muse-Spark-Open-816B-A42B"}


def token_cost(model: str, input_tokens: int, cached_tokens: int, output_tokens: int) -> float:
    """Reasoning tokens are billed as output. input_tokens includes the cached ones."""
    p = PRICES[model]
    return (
        (input_tokens - cached_tokens) * p["in"]
        + cached_tokens * p["cached"]
        + output_tokens * p["out"]
    )


def sam_cost(frames: int = 0, images: int = 0) -> float:
    p = PRICES["sam-3.1"]
    return frames * p["video_frame"] + images * p["image"]


def audio_cost(seconds: float) -> float:
    return seconds / 3600 * PRICES["muse-voice-transcribe-1.0"]["audio_hour"]
