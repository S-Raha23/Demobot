import asyncio
from datetime import timedelta

import pytest
from sqlmodel import select

from demobot import budget, db
from demobot.config import settings, token_cost
from demobot.db import ApiCall, utcnow
from demobot.errors import DemoBotError


@pytest.fixture(autouse=True)
def caps(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        "cap_meta_total_usd": 130.0,
        "cap_meta_dev_daily_usd": 40.0,
        "cap_meta_judge_daily_usd": 6.0,
        "cap_baseten_total_usd": 90.0,
        "cap_baseten_dev_daily_usd": 35.0,
        "cap_modal_total_usd": 110.0,
        "cap_modal_judge_daily_usd": 5.0,
    }.items():
        monkeypatch.setattr(settings, name, value)


def add_row(**fields: object) -> None:
    row = {"mode": "dev", "model": "muse-spark-1.3", "purpose": "watch", "state": "settled"}
    with db.session() as s:
        s.add(ApiCall(**{**row, **fields}))  # type: ignore[arg-type]
        s.commit()


def reserve(mode: str = "dev", usd: float = 1.0, provider: str = "meta") -> int:
    return budget.reserve(
        mode=mode,
        run_id=None,
        provider=provider,
        model="m",
        purpose="watch",
        estimate_usd=usd,
        cache_key="k",
    )


def test_token_cost_formula() -> None:
    cost = token_cost("muse-spark-1.3", 1_000_000, 200_000, 100_000)
    assert cost == pytest.approx(800_000 * 1.25e-6 + 200_000 * 0.15e-6 + 100_000 * 4.25e-6)


@pytest.mark.parametrize(
    ("cap", "mode", "existing"),
    [
        ("meta_total", "dev", {"cost_usd": 129.5, "created_at": utcnow() - timedelta(2)}),
        ("meta_dev_daily", "dev", {"cost_usd": 39.5}),
        ("meta_judge_daily", "judge", {"mode": "judge", "cost_usd": 5.5}),
    ],
)
def test_reserve_over_each_cap_is_refused(cap: str, mode: str, existing: dict) -> None:
    add_row(**existing)
    with pytest.raises(DemoBotError) as err:
        reserve(mode, 1.0)
    assert err.value.code == "BUDGET_EXCEEDED" and cap in err.value.message
    reserve(mode, 0.4)  # still fits under the same cap


def test_replay_mode_never_reserves() -> None:
    with pytest.raises(DemoBotError) as err:
        reserve("replay", 0.01)
    assert err.value.code == "REPLAY_MODE"


async def test_twenty_concurrent_reserves_never_exceed_cap(monkeypatch) -> None:
    monkeypatch.setattr(settings, "cap_meta_dev_daily_usd", 10.0)

    async def one() -> int:
        await asyncio.sleep(0)
        return await asyncio.to_thread(reserve, "dev", 1.0)

    results = await asyncio.gather(*(one() for _ in range(20)), return_exceptions=True)
    ok = [r for r in results if isinstance(r, int)]
    assert len(ok) == 10
    assert all(isinstance(r, DemoBotError) for r in results if not isinstance(r, int))
    with db.session() as s:
        rows = s.exec(select(ApiCall).where(ApiCall.state == "reserved")).all()
    assert sum(r.reserved_usd for r in rows) <= 10.0


def test_stale_reserved_row_still_counts() -> None:
    add_row(state="reserved", reserved_usd=39.5, created_at=utcnow() - timedelta(minutes=20))
    with pytest.raises(DemoBotError):
        reserve("dev", 1.0)


def test_adjustment_rows_count_toward_total_only() -> None:
    add_row(state="adjustment", cost_usd=129.5, note="seed")
    left = budget.remaining("dev", "meta")
    assert left["meta_total"] == pytest.approx(0.5) and left["meta_dev_daily"] == pytest.approx(40)
    with pytest.raises(DemoBotError):
        reserve("dev", 1.0)


def test_released_and_cache_hit_rows_cost_nothing() -> None:
    add_row(state="released", reserved_usd=50.0)
    add_row(state="cache_hit", reserved_usd=50.0)
    assert budget.remaining("dev", "meta")["meta_total"] == pytest.approx(130)


def test_caps_are_counted_per_provider() -> None:
    add_row(provider="baseten", cost_usd=89.5)
    add_row(provider="modal", mode="judge", cost_usd=4.5)
    reserve("dev", 10.0, provider="meta")  # Meta caps ignore Baseten and Modal rows
    with pytest.raises(DemoBotError) as err:
        reserve("dev", 1.0, provider="baseten")
    assert "baseten_total" in err.value.message
    with pytest.raises(DemoBotError) as err:
        reserve("judge", 1.0, provider="modal")
    assert "modal_judge_daily" in err.value.message
    assert budget.remaining("dev", "meta")["meta_total"] == pytest.approx(120)


def test_settle_stores_usage() -> None:
    call_id = reserve("dev", 0.5)
    usage = {"input_tokens": 100, "cached_input_tokens": 7, "output_tokens": 20, "frames": 50}
    budget.settle(call_id, 0.01, usage, 123, note="incomplete")
    with db.session() as s:
        row = s.get(ApiCall, call_id)
    assert row is not None
    assert row.state == "settled" and row.cost_usd == 0.01 and row.note == "incomplete"
    assert (row.input_tokens, row.cached_input_tokens, row.output_tokens) == (100, 7, 20)
    assert row.frames == 50 and row.latency_ms == 123


def test_release_costs_nothing() -> None:
    call_id = reserve("dev", 39.0)
    budget.release(call_id, "http_500")
    with db.session() as s:
        row = s.get(ApiCall, call_id)
    assert row is not None and row.state == "released" and row.error == "http_500"
    reserve("dev", 39.0)  # the released reservation no longer blocks the cap


def test_summary_groups_by_provider_and_model() -> None:
    add_row(provider="meta", model="muse-wonder-1.0", cost_usd=1.5)
    add_row(provider="baseten", model="meta-models/muse-spark-open-1026", cost_usd=0.5)
    add_row(provider="baseten", model="meta-models/muse-spark-open-1026", state="cache_hit")
    s = budget.summary()
    assert s["by_provider"]["meta"]["usd"] == pytest.approx(1.5)
    assert s["by_provider"]["baseten"]["cache_hits"] == 1
    assert s["by_model"]["meta-models/muse-spark-open-1026"]["calls"] == 1
