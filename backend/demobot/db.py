"""The SQLite ledger of every paid call. Runs themselves live on disk (docs/02 "run model")."""

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlmodel import Field, Session, SQLModel, create_engine

from demobot.config import settings


def utcnow() -> datetime:
    return datetime.now(UTC)


class ApiCall(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: str | None = Field(default=None, index=True)
    mode: str  # dev | judge
    provider: str = Field(default="meta", index=True)  # meta | baseten | modal
    model: str
    purpose: str  # watch | track:<phrase> | synth | judge | redteam:<persona> | probe:<item> ...
    cache_key: str | None = Field(default=None, index=True)
    state: str = Field(index=True)  # reserved | settled | released | cache_hit | adjustment
    note: str | None = None  # incomplete | timeout | cancelled | error | reconciliation ...
    reserved_usd: float = 0.0
    cost_usd: float = 0.0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    frames: int = 0
    images: int = 0
    audio_s: float = 0.0
    latency_ms: int = 0
    error: str | None = None
    created_at: datetime = Field(default_factory=utcnow, index=True)


_engine: Engine | None = None


def make_engine(url: str) -> Engine:
    """Create an engine; for a SQLite file, create its parent folder first."""
    if ":memory:" not in url:
        Path(url.split("///", 1)[1]).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(url, connect_args={"check_same_thread": False})


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = make_engine(f"sqlite:///{settings.db_path}")
        init_db(_engine)
    return _engine


def init_db(engine: Engine | None = None) -> None:
    SQLModel.metadata.create_all(engine or get_engine())


def session() -> Session:
    return Session(get_engine())
