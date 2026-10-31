"""Reserve, then settle: every paid call reserves its estimate against its provider's caps first.

Meta has no hard spend limit, so this ledger is the only safety (docs/03 "Budget caps").
"""

import threading
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, func
from sqlmodel import Session, select

from demobot import db
from demobot.config import PROVIDERS, settings
from demobot.db import ApiCall
from demobot.errors import DemoBotError

# a thread lock, not an asyncio one: the red-team pool and the API share one process
_lock = threading.Lock()

# settled and adjustment rows count their cost; reserved rows their reservation
_BILLED = ("settled", "adjustment")


def _day_start() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def _committed(s: Session, *where: Any) -> float:
    """Settled spend plus open reservations. A reserved row left over from a crash counts at its
    reserved amount whatever its age, the conservative choice."""
    spend = case(
        (ApiCall.state == "reserved", ApiCall.reserved_usd),  # type: ignore[arg-type]
        (ApiCall.state.in_(_BILLED), ApiCall.cost_usd),  # type: ignore[attr-defined]
        else_=0.0,
    )
    return float(s.exec(select(func.coalesce(func.sum(spend), 0.0)).where(*where)).one())


def _caps(s: Session, provider: str, mode: str) -> list[tuple[str, float, float]]:
    """(name, used, cap) for every cap that applies. Each provider counts its own rows only.
    Adjustment rows (ledger seeds, reconciliation) count toward the total cap only."""
    if provider not in PROVIDERS:
        raise DemoBotError("UNKNOWN_PROVIDER", f"no caps for provider {provider!r}")
    mine = ApiCall.provider == provider
    caps = [(f"{provider}_total", _committed(s, mine), settings.cap(provider, "total"))]
    if mode in ("dev", "judge"):
        today = (
            ApiCall.mode == mode,
            ApiCall.created_at >= _day_start(),
            ApiCall.state != "adjustment",
        )
        caps.append(
            (
                f"{provider}_{mode}_daily",
                _committed(s, mine, *today),
                settings.cap(provider, f"{mode}_daily"),
            )
        )
    return caps


def reserve(
    *,
    mode: str,
    run_id: str | None,
    provider: str,
    model: str,
    purpose: str,
    estimate_usd: float,
    cache_key: str | None,
) -> int:
    """Check every cap of this provider, then write a `reserved` row; returns its id."""
    if mode == "replay":
        raise DemoBotError("REPLAY_MODE", "replay mode makes no paid calls", stage=purpose)
    with _lock, db.session() as s:
        for name, used, cap in _caps(s, provider, mode):
            if used + estimate_usd > cap:
                raise DemoBotError(
                    "BUDGET_EXCEEDED",
                    f"{name} cap ${cap:.2f} reached (used ${used:.2f})",
                    stage=purpose,
                    http=402,
                )
        row = ApiCall(
            run_id=run_id,
            mode=mode,
            provider=provider,
            model=model,
            purpose=purpose,
            cache_key=cache_key,
            state="reserved",
            reserved_usd=estimate_usd,
        )
        s.add(row)
        s.commit()
        s.refresh(row)
        assert row.id is not None
        return row.id


def settle(
    call_id: int, cost_usd: float, usage: dict[str, Any], latency_ms: int, note: str | None = None
) -> None:
    """state=settled with the real cost and usage."""
    with db.session() as s:
        row = s.get(ApiCall, call_id)
        assert row is not None
        row.state = "settled"
        row.cost_usd = cost_usd
        row.note = note
        row.latency_ms = latency_ms
        row.input_tokens = int(usage.get("input_tokens") or 0)
        row.cached_input_tokens = int(usage.get("cached_input_tokens") or 0)
        row.output_tokens = int(usage.get("output_tokens") or 0)
        row.frames = int(usage.get("frames") or 0)
        row.images = int(usage.get("images") or 0)
        row.audio_s = float(usage.get("audio_s") or 0.0)
        s.add(row)
        s.commit()


def release(call_id: int, error: str) -> None:
    """state=released: the call failed before producing output, so nothing was billed."""
    with db.session() as s:
        row = s.get(ApiCall, call_id)
        assert row is not None
        row.state = "released"
        row.error = error
        s.add(row)
        s.commit()


def log_cache_hit(
    *, run_id: str | None, mode: str, provider: str, model: str, purpose: str, cache_key: str
) -> None:
    """A $0 `cache_hit` row, so the costs page can count hits."""
    with db.session() as s:
        s.add(
            ApiCall(
                run_id=run_id,
                mode=mode,
                provider=provider,
                model=model,
                purpose=purpose,
                cache_key=cache_key,
                state="cache_hit",
            )
        )
        s.commit()


def remaining(mode: str, provider: str) -> dict[str, float]:
    """Dollars left under each cap that applies to `mode` on `provider`."""
    with db.session() as s:
        return {name: cap - used for name, used, cap in _caps(s, provider, mode)}


def summary() -> dict[str, Any]:
    """Per-provider and per-model spend, call counts and cache hits, for `make costs` and the UI."""
    with db.session() as s:
        rows = s.exec(select(ApiCall)).all()
    by_provider: dict[str, dict[str, float]] = {}
    by_model: dict[str, dict[str, float]] = {}
    for r in rows:
        cost = (
            r.reserved_usd if r.state == "reserved" else r.cost_usd if r.state in _BILLED else 0.0
        )
        for key, table in ((r.provider, by_provider), (r.model, by_model)):
            t = table.setdefault(key, {"usd": 0.0, "calls": 0, "cache_hits": 0, "today_usd": 0.0})
            t["usd"] += cost
            if r.state == "cache_hit":
                t["cache_hits"] += 1
            elif r.state in ("settled", "reserved"):
                t["calls"] += 1
            created = r.created_at if r.created_at.tzinfo else r.created_at.replace(tzinfo=UTC)
            if created >= _day_start() and r.state != "adjustment":
                t["today_usd"] += cost
    return {
        "by_provider": by_provider,
        "by_model": by_model,
        "remaining": {
            p: remaining(settings.demobot_mode if settings.demobot_mode != "replay" else "dev", p)
            for p in PROVIDERS
        },
    }
