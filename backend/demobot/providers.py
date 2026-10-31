"""Provider clients and the call builders the gateway runs. Each builder returns a gateway.Call:
call(timeout) -> (raw JSON-able output, cost_usd, usage).

Facts confirmed by the M0 probes (docs/probe-results.md) are isolated in one function each here.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from openai import AsyncOpenAI

from demobot.config import settings, token_cost
from demobot.errors import DemoBotError
from demobot.gateway import Call, IncompleteResponse


@dataclass(frozen=True)
class Provider:
    name: str
    url_setting: str
    key_setting: str
    client_timeout_s: float

    def base_url(self) -> str | None:
        return getattr(settings, self.url_setting)

    def api_key(self) -> str | None:
        return getattr(settings, self.key_setting)


PROVIDERS: dict[str, Provider] = {
    "meta": Provider("meta", "meta_base_url", "model_api_key", 600),
    "baseten": Provider("baseten", "baseten_base_url", "baseten_api_key", 300),
    "modal": Provider("modal", "modal_base_url", "modal_api_key", 300),
}

_clients: dict[str, tuple[tuple[str, str], AsyncOpenAI]] = {}


def client(name: str) -> AsyncOpenAI:
    """One OpenAI-compatible client per provider, rebuilt only if its URL or key changes."""
    try:
        prov = PROVIDERS[name]
    except KeyError:
        raise DemoBotError("UNKNOWN_PROVIDER", f"no provider {name!r}") from None
    url = prov.base_url() or "https://invalid.local/v1"
    key = prov.api_key() or "fixtures"
    cached = _clients.get(name)
    if cached is None or cached[0] != (url, key):
        c = AsyncOpenAI(
            base_url=url,
            api_key=key,
            timeout=prov.client_timeout_s,
            max_retries=0,
        )
        cached = _clients[name] = ((url, key), c)
    return cached[1]


# ---------- usage and cost ----------
def responses_usage(resp: Any) -> dict[str, Any]:
    u = getattr(resp, "usage", None)
    if u is None:
        return {}
    details = getattr(u, "input_tokens_details", None)
    out_details = getattr(u, "output_tokens_details", None)
    return {
        "input_tokens": int(getattr(u, "input_tokens", 0) or 0),
        "cached_input_tokens": int(getattr(details, "cached_tokens", 0) or 0),
        "output_tokens": int(getattr(u, "output_tokens", 0) or 0),
        "reasoning_tokens": int(getattr(out_details, "reasoning_tokens", 0) or 0),
    }


def chat_usage(resp: Any) -> dict[str, Any]:
    u = getattr(resp, "usage", None)
    if u is None:
        return {}
    details = getattr(u, "prompt_tokens_details", None)
    return {
        "input_tokens": int(u.prompt_tokens or 0),
        "cached_input_tokens": int(getattr(details, "cached_tokens", 0) or 0),
        "output_tokens": int(u.completion_tokens or 0),
    }


def tokens_cost(model: str, usage: dict[str, Any]) -> float:
    return token_cost(
        model,
        usage.get("input_tokens", 0),
        usage.get("cached_input_tokens", 0),
        usage.get("output_tokens", 0),
    )


def dump(resp: Any) -> Any:
    return resp.model_dump(mode="json") if hasattr(resp, "model_dump") else resp


# ---------- generic call builders ----------
def responses_call(model: str, *, cost_fn: Any = None, **kwargs: Any) -> Call:
    """A Meta Responses API call. Returns the full response dump; an incomplete response is
    raised as IncompleteResponse (billed). cost_fn(usage) overrides token pricing (SAM)."""

    async def call(timeout: float) -> tuple[Any, float, dict[str, Any]]:
        resp = (
            await client("meta")
            .with_options(timeout=timeout)
            .responses.create(model=model, **kwargs)
        )
        usage = responses_usage(resp)
        cost = cost_fn(usage) if cost_fn else tokens_cost(model, usage)
        if getattr(resp, "status", None) == "incomplete":
            raise IncompleteResponse(cost, usage)
        return dump(resp), cost, usage

    return call


def chat_call(provider: str, model: str, *, affinity_key: str | None = None, **kwargs: Any) -> Call:
    """A Chat Completions call on Baseten, Modal or Meta. Truncation raises IncompleteResponse."""

    async def call(timeout: float) -> tuple[Any, float, dict[str, Any]]:
        headers = None
        if provider == "modal" and affinity_key:  # same key per run helps Modal's prompt cache
            headers = {"Modal-Routing-Affinity-Key": affinity_key}
        resp = (
            await client(provider)
            .with_options(timeout=timeout)
            .chat.completions.create(model=model, extra_headers=headers, **kwargs)
        )
        usage = chat_usage(resp)
        cost = tokens_cost(model, usage) if model in _priced() else 0.0
        if resp.choices and resp.choices[0].finish_reason == "length":
            raise IncompleteResponse(cost, usage)
        return dump(resp), cost, usage

    return call


def _priced() -> set[str]:
    from demobot.config import PRICES

    return set(PRICES)


async def raw_post(
    path: str, *, timeout: float, json_body: Any = None, files: Any = None, data: Any = None
) -> httpx.Response:
    """A plain authenticated POST to the Meta API (Voice Transcribe, images)."""
    url = settings.meta_base_url.rstrip("/") + "/" + path.lstrip("/")
    headers = {"Authorization": f"Bearer {settings.model_api_key or ''}"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=15)) as h:
        resp = await h.post(url, headers=headers, json=json_body, files=files, data=data)
    resp.raise_for_status()
    return resp


# ---------- files ----------
_FILE_MAP = "files.json"


async def upload_file(path: Path, sha256: str) -> str:
    """Upload once per content hash (Files API, free); the id is remembered in data/cache."""
    index = settings.data_path / "cache" / _FILE_MAP
    known: dict[str, str] = json.loads(index.read_text()) if index.exists() else {}
    if sha256 in known:
        return known[sha256]
    if settings.demobot_fixtures:
        return f"file-fixture-{sha256[:12]}"
    with path.open("rb") as f:
        resp = await client("meta").files.create(file=f, purpose="user_data")
    known[sha256] = resp.id
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text(json.dumps(known, indent=1))
    return resp.id


def forget_file(sha256: str) -> None:
    """Drop a remembered upload (e.g. the provider expired it)."""
    index = settings.data_path / "cache" / _FILE_MAP
    if index.exists():
        known = json.loads(index.read_text())
        known.pop(sha256, None)
        index.write_text(json.dumps(known, indent=1))
