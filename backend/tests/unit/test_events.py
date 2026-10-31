from pathlib import Path

from pydantic import BaseModel

from demobot.events import EventLog, RunContext, read_events
from demobot.schemas_util import strict_schema


def test_events_append_with_increasing_seq_and_resume(tmp_path: Path) -> None:
    path = tmp_path / "r" / "events.jsonl"
    log = EventLog(path, "r")
    log.emit("stage_start", "watch")
    log.emit("model_call", "watch", model="m", provider="meta", tokens={"in": 3, "out": 1})
    resumed = EventLog(path, "r")  # a restart continues the sequence
    resumed.emit("stage_end", "watch")
    events = list(read_events(path))
    assert [e.seq for e in events] == [0, 1, 2]
    assert [e.type for e in events] == ["stage_start", "model_call", "stage_end"]
    assert events[1].tokens is not None and events[1].tokens.in_ == 3
    assert '"in":3' in path.read_text().splitlines()[1]  # serialised with the docs/02 name


def test_subscribers_see_every_event(tmp_path: Path) -> None:
    log = EventLog(tmp_path / "events.jsonl", "r")
    seen: list[int] = []
    unsubscribe = log.subscribe(lambda e: seen.append(e.seq))
    log.emit("log", "x")
    unsubscribe()
    log.emit("log", "x")
    assert seen == [0]


def test_context_without_log_is_silent() -> None:
    assert RunContext(None).emit("log") is None


class Inner(BaseModel):
    a: int = 1


class Outer(BaseModel):
    inner: Inner
    items: list[Inner]
    note: str | None = None


def test_strict_schema_inlines_refs_and_requires_everything() -> None:
    s = strict_schema(Outer)
    assert "$defs" not in s and "$ref" not in str(s)
    assert s["additionalProperties"] is False and set(s["required"]) == {"inner", "items", "note"}
    assert s["properties"]["inner"]["additionalProperties"] is False
    assert "default" not in str(s)
