import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import openai
import pytest
from pydantic import BaseModel
from sqlmodel import select

from demobot import budget, db, gateway
from demobot.config import settings
from demobot.db import ApiCall
from demobot.errors import DemoBotError
from demobot.events import EventLog, RunContext, read_events


class Answer(BaseModel):
    answer: str


validate = gateway.validator(Answer)


def request(**extra: Any) -> dict[str, Any]:
    return {"purpose": "judge", "reasoning_effort": "low", "clip_sha256": "abc", **extra}


@pytest.fixture
def live(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gateway tests exercise the live path with fake calls (never the network)."""
    monkeypatch.setattr(settings, "demobot_fixtures", False)


@pytest.fixture
def ctx(tmp_path: Path) -> RunContext:
    return RunContext("run1", "dev", EventLog(tmp_path / "run1" / "events.jsonl", "run1"), "verify")


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    waited: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        waited.append(seconds)

    monkeypatch.setattr(gateway, "_sleep", fake_sleep)
    monkeypatch.setattr(gateway, "HEARTBEAT_S", 3600.0)
    return waited


class FakeCall:
    """call(timeout) that plays back a script of results or exceptions."""

    def __init__(self, *script: Any) -> None:
        self.script = list(script)
        self.timeouts: list[float] = []

    async def __call__(self, timeout: float) -> Any:
        self.timeouts.append(timeout)
        item = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(item, BaseException):
            raise item
        return item


def status_error(code: int, headers: dict | None = None) -> openai.APIStatusError:
    req = httpx.Request("POST", "https://api.meta.ai/v1/responses")
    resp = httpx.Response(code, headers=headers or {}, request=req)
    return openai.APIStatusError(f"http {code}", response=resp, body=None)


async def go(call: Any, ctx: RunContext, req: dict | None = None, **kw: Any) -> Any:
    return await gateway.cached_call(
        ctx=ctx,
        purpose=kw.pop("purpose", "judge"),
        provider=kw.pop("provider", "meta"),
        model="muse-spark-1.3",
        request=req or request(),
        estimate_usd=0.05,
        call=call,
        validate=kw.pop("validate", validate),
        **kw,
    )


def rows() -> list[ApiCall]:
    with db.session() as s:
        return list(s.exec(select(ApiCall).order_by(ApiCall.id)).all())  # type: ignore[arg-type]


def model_calls(ctx: RunContext) -> list[Any]:
    assert ctx.events is not None
    return [e for e in read_events(ctx.events.path) if e.type == "model_call"]


# ---------- cache key ----------
def test_same_request_same_key() -> None:
    assert gateway.cache_key(request()) == gateway.cache_key(request())


@pytest.mark.parametrize("change", [{"phrase": "mug"}, {"reasoning_effort": "high"}])
def test_changed_input_changes_key(change: dict) -> None:
    base = request(phrase="pen")
    assert gateway.cache_key(base) != gateway.cache_key({**base, **change})


def test_key_order_does_not_matter() -> None:
    req = request()
    assert gateway.cache_key(req) == gateway.cache_key(dict(reversed(list(req.items()))))


def test_key_includes_provider_model_and_versions(monkeypatch) -> None:
    k = gateway.request_key(request(), "meta", "m")
    assert k != gateway.request_key(request(), "baseten", "m")
    assert k != gateway.request_key(request(), "meta", "m2")
    monkeypatch.setattr(settings, "prompt_version", "p2")
    assert k != gateway.request_key(request(), "meta", "m")


# ---------- gateway ----------
async def test_repeated_call_costs_nothing_and_emits_cached_event(live, ctx) -> None:
    usage = {"input_tokens": 900, "cached_input_tokens": 100, "output_tokens": 50}
    call = FakeCall(({"answer": "yes"}, 0.0123, usage))
    first = await go(call, ctx)
    second = await go(call, ctx)
    assert first == second == Answer(answer="yes")
    assert len(call.timeouts) == 1  # the second call never reached the provider
    settled, hit = rows()
    assert settled.state == "settled" and settled.cost_usd == pytest.approx(0.0123)
    assert hit.state == "cache_hit" and hit.cost_usd == 0.0 and hit.cache_key == settled.cache_key
    live_ev, cached_ev = model_calls(ctx)
    assert live_ev.cached is False and live_ev.cost_usd == pytest.approx(0.0123)
    assert live_ev.tokens is not None and live_ev.tokens.in_ == 900 and live_ev.tokens.out == 50
    assert live_ev.model == "muse-spark-1.3" and live_ev.provider == "meta"
    assert live_ev.stage == "verify" and live_ev.payload["purpose"] == "judge"
    assert cached_ev.cached is True and cached_ev.cost_usd == 0.0


async def test_call_gets_purpose_timeout(live, ctx) -> None:
    call = FakeCall(({"answer": "a"}, 0.0, {}))
    await go(call, ctx, purpose="track:pen", req=request(phrase="pen"))
    assert call.timeouts == [gateway.TIMEOUTS["track"]]


async def test_use_cache_false_skips_read_but_writes(live, ctx) -> None:
    call = FakeCall(({"answer": "a"}, 0.01, {}), ({"answer": "b"}, 0.01, {}))
    await go(call, ctx)
    assert await go(call, ctx, use_cache=False) == Answer(answer="b")
    assert await go(call, ctx) == Answer(answer="b")  # the fresh answer replaced the cache
    assert [r.state for r in rows()] == ["settled", "settled", "cache_hit"]


async def test_invalid_output_is_billed_not_cached_and_raises(live, ctx) -> None:
    call = FakeCall(({"wrong": 1}, 0.02, {"output_tokens": 10}))
    with pytest.raises(DemoBotError) as err:
        await go(call, ctx)
    assert err.value.code == "INVALID_MODEL_OUTPUT"
    (row,) = rows()
    assert row.state == "settled" and row.cost_usd == pytest.approx(0.02)
    assert not list(gateway.cache_dir().glob("*.json"))
    with pytest.raises(DemoBotError):
        await go(call, ctx)
    assert len(call.timeouts) == 2  # not cached: the provider is called again


async def test_400_releases_and_raises_without_retry(live, ctx, sleeps) -> None:
    call = FakeCall(status_error(400))
    with pytest.raises(DemoBotError) as err:
        await go(call, ctx)
    assert err.value.code == "API_CLIENT_ERROR"
    assert len(call.timeouts) == 1 and sleeps == []
    (row,) = rows()
    assert row.state == "released" and row.error == "http_400"


async def test_429_waits_for_retry_after(live, ctx, sleeps) -> None:
    call = FakeCall(status_error(429, {"retry-after": "7"}), ({"answer": "ok"}, 0.01, {}))
    assert await go(call, ctx) == Answer(answer="ok")
    assert len(sleeps) == 1 and sleeps[0] >= 7
    assert [r.state for r in rows()] == ["released", "settled"]


async def test_incomplete_settles_then_retries(live, ctx, sleeps) -> None:
    incomplete = gateway.IncompleteResponse(0.03, {"input_tokens": 500, "output_tokens": 16000})
    call = FakeCall(incomplete, ({"answer": "ok"}, 0.01, {}))
    assert await go(call, ctx) == Answer(answer="ok")
    first, second = rows()
    assert (first.state, first.note, first.cost_usd) == ("settled", "incomplete", 0.03)
    assert first.output_tokens == 16000 and second.state == "settled"
    notes = [e.payload.get("note") for e in model_calls(ctx)]
    assert notes == ["incomplete", None]  # the billed incomplete attempt is visible too


async def test_timeout_settles_at_estimate_and_retries(live, ctx, sleeps) -> None:
    timeout = openai.APITimeoutError(httpx.Request("POST", "https://api.meta.ai/v1/responses"))
    call = FakeCall(timeout, ({"answer": "ok"}, 0.01, {}))
    assert await go(call, ctx) == Answer(answer="ok")
    first, _ = rows()
    assert (first.state, first.note, first.cost_usd) == ("settled", "timeout", 0.05)


async def test_repeated_failures_give_api_unavailable(live, ctx, sleeps) -> None:
    conn = openai.APIConnectionError(request=httpx.Request("POST", "https://api.meta.ai/v1"))
    call = FakeCall(status_error(503), status_error(500), conn, status_error(502))
    with pytest.raises(DemoBotError) as err:
        await go(call, ctx)
    assert err.value.code == "API_UNAVAILABLE"
    assert len(call.timeouts) == gateway.MAX_ATTEMPTS
    assert [r.state for r in rows()] == ["released"] * gateway.MAX_ATTEMPTS
    assert sleeps == sorted(sleeps) and len(sleeps) == gateway.MAX_ATTEMPTS - 1


async def test_cancel_settles_at_estimate(live, ctx) -> None:
    started = asyncio.Event()

    async def slow(timeout: float) -> Any:
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(go(slow, ctx))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    (row,) = rows()
    assert (row.state, row.note, row.cost_usd) == ("settled", "cancelled", 0.05)


async def test_heartbeat_events_while_in_flight(live, ctx, monkeypatch) -> None:
    monkeypatch.setattr(gateway, "HEARTBEAT_S", 0.01)

    async def slow(timeout: float) -> Any:
        await asyncio.sleep(0.08)
        return {"answer": "ok"}, 0.0, {}

    await go(slow, ctx)
    assert ctx.events is not None
    beats = [e for e in read_events(ctx.events.path) if e.payload.get("heartbeat")]
    assert len(beats) >= 2 and beats[0].payload["purpose"] == "judge"


async def test_budget_refusal_happens_before_the_call(live, ctx, monkeypatch) -> None:
    monkeypatch.setattr(settings, "cap_meta_dev_daily_usd", 0.01)
    call = FakeCall(({"answer": "a"}, 0.0, {}))
    with pytest.raises(DemoBotError) as err:
        await go(call, ctx)
    assert err.value.code == "BUDGET_EXCEEDED" and call.timeouts == []


async def test_fixtures_mode_reads_recorded_response(ctx, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "fixtures_dir", str(tmp_path / "fixtures"))
    key = gateway.request_key(request(), "meta", "muse-spark-1.3")
    settings.fixtures_path.mkdir(parents=True)
    rec = {"raw": {"answer": "recorded"}, "usage": {"input_tokens": 5}}
    (settings.fixtures_path / f"{key}.json").write_text(json.dumps(rec))
    call = FakeCall(RuntimeError("network must not be used"))
    assert await go(call, ctx, use_cache=False) == Answer(answer="recorded")
    assert call.timeouts == [] and [r.state for r in rows()] == ["cache_hit"]


async def test_fixtures_mode_missing_file(ctx, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "fixtures_dir", str(tmp_path / "fixtures"))
    call = FakeCall(RuntimeError("network must not be used"))
    with pytest.raises(DemoBotError) as err:
        await go(call, ctx)
    assert err.value.code == "FIXTURE_MISSING" and call.timeouts == [] and rows() == []


async def test_provider_rows_are_tagged_and_capped_separately(live, ctx) -> None:
    call = FakeCall(({"answer": "a"}, 0.01, {}))
    await go(call, ctx, provider="baseten")
    await go(call, ctx, provider="baseten")
    await go(call, ctx, provider="modal")
    assert [(r.provider, r.state) for r in rows()] == [
        ("baseten", "settled"),
        ("baseten", "cache_hit"),
        ("modal", "settled"),
    ]
    assert budget.remaining("dev", "baseten")["baseten_total"] == pytest.approx(90 - 0.01)
    assert budget.remaining("dev", "meta")["meta_total"] == pytest.approx(130)


# ---------- fallback chains ----------
def route(provider: str, call: Any, model: str = "m") -> gateway.Route:
    return gateway.Route(provider, model, request(), 0.02, call)


async def test_chain_falls_back_and_emits_visible_event(live, ctx, sleeps, monkeypatch) -> None:
    monkeypatch.setattr(settings, "baseten_api_key", "k")
    monkeypatch.setattr(settings, "model_api_key", "k")
    bad = FakeCall(({"nope": 1}, 0.001, {}))
    good = FakeCall(({"answer": "meta"}, 0.002, {}))
    result, used = await gateway.chain_call(
        ctx=ctx,
        purpose="judge",
        routes=[route("baseten", bad, "open"), route("meta", good, "muse-spark-1.3")],
        validate=validate,
    )
    assert result == Answer(answer="meta") and used.provider == "meta"
    assert ctx.events is not None
    fb = [e for e in read_events(ctx.events.path) if e.payload.get("fallback")]
    assert len(fb) == 1 and fb[0].payload["code"] == "INVALID_MODEL_OUTPUT"
    assert "Baseten" in fb[0].payload["from"] and "Meta" in fb[0].payload["to"]


async def test_chain_skips_providers_without_keys(live, ctx, monkeypatch) -> None:
    monkeypatch.setattr(settings, "baseten_api_key", None)
    monkeypatch.setattr(settings, "model_api_key", "k")
    never = FakeCall(RuntimeError("must not be called"))
    good = FakeCall(({"answer": "ok"}, 0.0, {}))
    _, used = await gateway.chain_call(
        ctx=ctx,
        purpose="judge",
        routes=[route("baseten", never), route("meta", good)],
        validate=validate,
    )
    assert used.provider == "meta" and never.timeouts == []


async def test_chain_reraises_non_fallback_errors(live, ctx, monkeypatch) -> None:
    monkeypatch.setattr(settings, "baseten_api_key", "k")

    async def boom(timeout: float) -> Any:
        raise DemoBotError("BAD_INPUT", "x")

    with pytest.raises(DemoBotError) as err:
        await gateway.chain_call(
            ctx=ctx,
            purpose="judge",
            routes=[route("baseten", boom), route("meta", boom)],
            validate=validate,
        )
    assert err.value.code == "BAD_INPUT"


def test_modal_llm_flag_disables_modal(live, monkeypatch) -> None:
    monkeypatch.setattr(settings, "modal_api_key", "wk-1.ws-2")
    monkeypatch.setattr(settings, "modal_base_url", "https://x.modal.run/v1")
    monkeypatch.setattr(settings, "modal_llm", True)
    assert gateway.provider_available("modal")
    monkeypatch.setattr(settings, "modal_llm", False)
    assert not gateway.provider_available("modal")


async def test_two_incomplete_answers_hand_over_to_the_fallback(live, ctx, sleeps) -> None:
    cut = gateway.IncompleteResponse(0.01, {"output_tokens": 5000})
    call = FakeCall(cut, cut, ({"answer": "never"}, 0.01, {}))
    with pytest.raises(DemoBotError) as err:
        await go(call, ctx)
    assert err.value.code == "API_UNAVAILABLE" and len(call.timeouts) == gateway.MAX_INCOMPLETE
    assert [r.note for r in rows()] == ["incomplete", "incomplete"]  # both were billed
