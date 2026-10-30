"""The run's append-only event log (docs/02 "Event schema"). The UI renders only from these."""

import json
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

EventType = Literal[
    "stage_start",
    "stage_end",
    "model_call",
    "tool_call",
    "artifact",
    "decision",
    "metric",
    "log",
    "error",
    "question",
]
ProviderTag = Literal["meta", "baseten", "modal", "local"]


class Tokens(BaseModel):
    in_: int = Field(0, alias="in")
    cached: int = 0
    out: int = 0

    model_config = {"populate_by_name": True}


class Event(BaseModel):
    ts: str
    run_id: str
    seq: int
    stage: str
    type: EventType
    model: str | None = None
    provider: ProviderTag | None = None
    latency_ms: int | None = None
    tokens: Tokens | None = None
    cost_usd: float | None = None
    cached: bool | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    def to_json(self) -> str:
        return self.model_dump_json(by_alias=True, exclude_none=True)


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class EventLog:
    """Appends events to `<run_dir>/events.jsonl`. seq continues across restarts (resume)."""

    def __init__(self, path: Path, run_id: str) -> None:
        self.path = path
        self.run_id = run_id
        self._lock = threading.Lock()
        self._subscribers: list[Callable[[Event], None]] = []
        path.parent.mkdir(parents=True, exist_ok=True)
        self._seq = sum(1 for _ in read_events(path)) if path.exists() else 0

    def subscribe(self, fn: Callable[[Event], None]) -> Callable[[], None]:
        self._subscribers.append(fn)
        return lambda: self._subscribers.remove(fn)

    def emit(self, type: EventType, stage: str, **fields: Any) -> Event:
        tokens = fields.pop("tokens", None)
        with self._lock:
            ev = Event(
                ts=now_iso(),
                run_id=self.run_id,
                seq=self._seq,
                stage=stage,
                type=type,
                tokens=Tokens(**tokens) if isinstance(tokens, dict) else tokens,
                **fields,
            )
            self._seq += 1
            with self.path.open("a", encoding="utf-8") as f:
                f.write(ev.to_json() + "\n")
        for fn in list(self._subscribers):
            fn(ev)
        return ev


def read_events(path: Path) -> Iterator[Event]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield Event.model_validate(json.loads(line))


@dataclass
class RunContext:
    """What every stage and the gateway need from a run: its id, mode and event log.
    `events` is None for ad-hoc calls (probes, scripts), which then only hit the ledger."""

    run_id: str | None
    mode: str = "dev"
    events: EventLog | None = None
    stage: str = "run"
    extra: dict[str, Any] = field(default_factory=dict)

    def emit(self, type: EventType, stage: str | None = None, **fields: Any) -> Event | None:
        if self.events is None:
            return None
        return self.events.emit(type, stage or self.stage, **fields)

    def at(self, stage: str) -> "RunContext":
        return RunContext(self.run_id, self.mode, self.events, stage, self.extra)
