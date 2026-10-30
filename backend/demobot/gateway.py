"""The single choke point for every paid call (Meta, Baseten, Modal). docs/02 "The gateway".

Every call is cached by the SHA-256 of its full request, reserved against its provider's caps
before it runs, settled (or released) after, and reported as a `model_call` event.
Provider-specific request building lives in providers.py; this module is provider-agnostic.
"""

import asyncio
import contextlib
import hashlib
import json
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError
from pydantic import BaseModel, ValidationError

from demobot import budget
from demobot.config import OPEN_WEIGHT_MODELS, settings
from demobot.errors import DemoBotError
from demobot.events import RunContext
from demobot.logging import get_logger

T = TypeVar("T")
M = TypeVar("M", bound=BaseModel)

# call(timeout) -> (raw JSON-able output, cost_usd, usage dict)
# usage keys: input_tokens, cached_input_tokens, output_tokens, frames, images, audio_s
Call = Callable[[float], Awaitable[tuple[Any, float, dict[str, Any]]]]

TIMEOUTS = {  # seconds, per purpose prefix
    "watch": 300,
    "crosswatch": 300,
    "arbitrate": 300,
    "rewatch": 180,
    "listen": 120,
    "track": 600,
    "segment_image": 120,
    "upload": 300,
    "synth": 300,
    "harden": 300,
    "correct": 300,
    "draft": 180,
    "supervise": 120,
    "redteam": 120,
    "judge": 120,
    "card": 180,
    "texture": 180,
    "narrative": 120,
    "probe": 300,
}
MAX_ATTEMPTS = 4
HEARTBEAT_S = 5.0

_sleep = asyncio.sleep  # patched in tests


class IncompleteResponse(Exception):
    """Raised by a call() when the response was cut short (status incomplete or finish=length).
    It was billed."""

    def __init__(self, cost: float, usage: dict[str, Any]) -> None:
        super().__init__("incomplete response")
        self.cost, self.usage = cost, usage


# ---------- cache ----------
def cache_key(request: dict[str, Any]) -> str:
    blob = json.dumps(request, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def request_key(request: dict[str, Any], provider: str, model: str) -> str:
    """Provider, model and the prompt/schema versions are always part of the key."""
    return cache_key(
        {
            "prompt_version": settings.prompt_version,
            "schema_version": settings.schema_version,
            **request,
            "provider": provider,
            "model": model,
        }
    )


def cache_dir() -> Path:
    if settings.demobot_fixtures:
        return settings.fixtures_path
    return settings.data_path / "cache"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validator(schema: type[M]) -> Callable[[Any], M]:
    """validate() for cached_call: a Pydantic model, or INVALID_MODEL_OUTPUT."""

    def validate(raw: Any) -> M:
        try:
            return schema.model_validate(raw)
        except ValidationError as e:
            raise DemoBotError("INVALID_MODEL_OUTPUT", f"{schema.__name__}: {e}") from e

    return validate


def passthrough(raw: Any) -> Any:
    return raw


def _retry_after(e: APIStatusError) -> float:
    try:
        return float(e.response.headers.get("retry-after", 0) or 0)
    except ValueError:  # an HTTP date: fall back to the backoff
        return 0.0


def _ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)


def _tokens(usage: dict[str, Any]) -> dict[str, int]:
    return {
        "in": int(usage.get("input_tokens") or 0),
        "cached": int(usage.get("cached_input_tokens") or 0),
        "out": int(usage.get("output_tokens") or 0),
    }


def _emit_call(
    ctx: RunContext,
    *,
    purpose: str,
    provider: str,
    model: str,
    cost: float,
    usage: dict[str, Any],
    latency_ms: int,
    cached: bool,
    note: str | None = None,
) -> None:
    payload: dict[str, Any] = {"purpose": purpose, "open_weight": model in OPEN_WEIGHT_MODELS}
    for k in ("frames", "images", "audio_s"):
        if usage.get(k):
            payload[k] = usage[k]
    if note:
        payload["note"] = note
    ctx.emit(
        "model_call",
        model=model,
        provider=provider,
        latency_ms=latency_ms,
        tokens=_tokens(usage),
        cost_usd=round(cost, 6),
        cached=cached,
        payload=payload,
    )


async def _heartbeat(ctx: RunContext, purpose: str, model: str) -> None:
    """A `log` event every HEARTBEAT_S while a call is in flight keeps the UI alive."""
    t0 = time.monotonic()
    while True:
        await _sleep(HEARTBEAT_S)
        ctx.emit(
            "log",
            payload={
                "heartbeat": True,
                "purpose": purpose,
                "model": model,
                "elapsed_s": round(time.monotonic() - t0, 1),
            },
        )


# ---------- the one way to call a model ----------
async def cached_call(
    *,
    ctx: RunContext,
    purpose: str,
    provider: str,
    model: str,
    request: dict[str, Any],
    estimate_usd: float,
    call: Call,
    validate: Callable[[Any], T],
    use_cache: bool = True,
) -> T:
    """Serve from cache, or reserve, call, settle, emit, validate and cache.

    use_cache=False skips the read but still writes. Invalid output is billed, never cached.
    call(timeout) must apply the timeout to its client."""
    key = request_key(request, provider, model)
    path = cache_dir() / f"{key}.json"
    log = get_logger(run_id=ctx.run_id, purpose=purpose, model=model, provider=provider)

    if (use_cache or settings.demobot_fixtures) and path.exists():
        budget.log_cache_hit(
            run_id=ctx.run_id,
            mode=ctx.mode,
            provider=provider,
            model=model,
            purpose=purpose,
            cache_key=key,
        )
        cached = json.loads(path.read_text())  # {"raw", "usage", "purpose"}
        _emit_call(
            ctx,
            purpose=purpose,
            provider=provider,
            model=model,
            cost=0.0,
            usage=cached.get("usage", {}),
            latency_ms=0,
            cached=True,
        )
        log.info("gateway_call", cache_hit=True, cost_usd=0.0)
        return validate(cached["raw"])
    if settings.demobot_fixtures:
        raise DemoBotError("FIXTURE_MISSING", f"no fixture for {purpose} {key}", stage=purpose)

    timeout = TIMEOUTS.get(purpose.split(":")[0], 180)
    last_err: BaseException | None = None
    for attempt in range(MAX_ATTEMPTS):
        call_id = budget.reserve(
            mode=ctx.mode,
            run_id=ctx.run_id,
            provider=provider,
            model=model,
            purpose=purpose,
            estimate_usd=estimate_usd,
            cache_key=key,
        )
        t0 = time.monotonic()
        wait = 0.0
        beat = asyncio.create_task(_heartbeat(ctx, purpose, model)) if ctx.events else None
        try:
            raw, cost, usage = await call(timeout)
        except asyncio.CancelledError:  # cancelled mid-call: assume billed
            budget.settle(call_id, estimate_usd, {}, _ms(t0), note="cancelled")
            raise
        except IncompleteResponse as e:  # billed: record it, then retry
            budget.settle(call_id, e.cost, e.usage, _ms(t0), note="incomplete")
            _emit_call(
                ctx,
                purpose=purpose,
                provider=provider,
                model=model,
                cost=e.cost,
                usage=e.usage,
                latency_ms=_ms(t0),
                cached=False,
                note="incomplete",
            )
            last_err = e
        except (APITimeoutError, httpx.TimeoutException) as e:  # may be billed: the estimate
            budget.settle(call_id, estimate_usd, {}, _ms(t0), note="timeout")
            last_err = e
        except APIStatusError as e:  # no output produced: nothing billed
            budget.release(call_id, f"http_{e.status_code}")
            if e.status_code != 429 and e.status_code < 500:
                raise DemoBotError("API_CLIENT_ERROR", str(e)[:500], stage=purpose) from e
            last_err, wait = e, _retry_after(e)
        except httpx.HTTPStatusError as e:
            budget.release(call_id, f"http_{e.response.status_code}")
            if e.response.status_code != 429 and e.response.status_code < 500:
                raise DemoBotError("API_CLIENT_ERROR", str(e)[:500], stage=purpose) from e
            last_err = e
        except (APIConnectionError, httpx.TransportError) as e:
            budget.release(call_id, type(e).__name__)
            last_err = e
        except DemoBotError as e:  # raised by the call itself before billing (e.g. bad input)
            budget.release(call_id, e.code)
            raise
        except Exception:  # unknown failure, maybe after billing: err high, at the estimate
            budget.settle(call_id, estimate_usd, {}, _ms(t0), note="error")
            raise
        else:
            latency = _ms(t0)
            budget.settle(call_id, cost, usage, latency)  # billed whether valid or not
            _emit_call(
                ctx,
                purpose=purpose,
                provider=provider,
                model=model,
                cost=cost,
                usage=usage,
                latency_ms=latency,
                cached=False,
            )
            log.info("gateway_call", cache_hit=False, cost_usd=cost, latency_ms=latency)
            result = validate(raw)  # raises INVALID_MODEL_OUTPUT; nothing is cached
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"raw": raw, "usage": usage, "purpose": purpose}))
            tmp.replace(path)
            return result
        finally:
            if beat is not None:
                beat.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await beat
        log.warning("gateway_retry", attempt=attempt + 1, error=repr(last_err)[:300])
        ctx.emit(
            "log", payload={"retry": attempt + 1, "purpose": purpose, "error": repr(last_err)[:200]}
        )
        if attempt + 1 < MAX_ATTEMPTS:
            await _sleep(max(wait, 1.0 * 2**attempt) + random.uniform(0, 0.3))
    raise DemoBotError("API_UNAVAILABLE", repr(last_err)[:500], stage=purpose)


# ---------- fallback chains ----------
FALLBACK_CODES = {"API_UNAVAILABLE", "API_CLIENT_ERROR", "BUDGET_EXCEEDED", "INVALID_MODEL_OUTPUT"}
PROVIDER_LABELS = {"meta": "Meta API", "baseten": "Baseten", "modal": "Modal", "local": "local"}


@dataclass
class Route:
    """One link of a fallback chain: where to send it, what it costs, and how to call it."""

    provider: str
    model: str
    request: dict[str, Any]
    estimate_usd: float
    call: Call
    label: str = ""

    def name(self) -> str:
        return self.label or f"{self.model} @ {PROVIDER_LABELS.get(self.provider, self.provider)}"


def provider_available(name: str) -> bool:
    """Fixtures keep every provider; otherwise each needs its key (and Modal its URL and flag)."""
    if settings.demobot_fixtures:
        return True
    if name == "meta":
        return bool(settings.model_api_key)
    if name == "baseten":
        return bool(settings.baseten_api_key)
    if name == "modal":
        return bool(settings.modal_llm and settings.modal_api_key and settings.modal_base_url)
    return name == "local"


async def chain_call(
    *,
    ctx: RunContext,
    purpose: str,
    routes: list[Route],
    validate: Callable[[Any], T],
    use_cache: bool = True,
) -> tuple[T, Route]:
    """Try each available route in order. A route ending in one of FALLBACK_CODES hands over to
    the next, and the fallback is emitted as a visible `log` event. Returns the result and the
    route that answered."""
    live = [r for r in routes if provider_available(r.provider)]
    if not live:
        raise DemoBotError("API_UNAVAILABLE", f"no provider available for {purpose}", stage=purpose)
    for i, route in enumerate(live):
        try:
            result = await cached_call(
                ctx=ctx,
                purpose=purpose,
                provider=route.provider,
                model=route.model,
                request=route.request,
                estimate_usd=route.estimate_usd,
                call=route.call,
                validate=validate,
                use_cache=use_cache,
            )
        except DemoBotError as e:
            if e.code not in FALLBACK_CODES or i + 1 == len(live):
                raise
            nxt = live[i + 1]
            get_logger(run_id=ctx.run_id).warning(
                "provider_fallback", purpose=purpose, frm=route.name(), to=nxt.name(), code=e.code
            )
            ctx.emit(
                "log",
                payload={
                    "fallback": True,
                    "purpose": purpose,
                    "from": route.name(),
                    "to": nxt.name(),
                    "code": e.code,
                    "message": f"{route.name()} failed ({e.code}); using {nxt.name()}",
                },
            )
            continue
        return result, route
    raise DemoBotError("API_UNAVAILABLE", f"no provider answered {purpose}", stage=purpose)
