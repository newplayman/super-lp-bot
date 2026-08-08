#!/usr/bin/env python3
"""Keyless, free, read-only HTTP adapters for the WP-05 RWA anchors.

Only documented public GET endpoints are present.  The module has no request
method other than GET, no credential argument, and no paid fallback.  xStocks
fails closed when its public quote does not include usable bid/ask and an
exchange-generated timestamp (the observed official weekend behavior).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import time
from typing import Callable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

from scripts.lp_rwa_instrument_v1_readonly import Instrument, PriceObservation


ALLOWED_PUBLIC_DOMAINS = frozenset({"api.backed.fi", "api.bybit.com", "api.robinhood.com"})


class AnchorUnavailable(RuntimeError):
    """A named public source cannot safely produce a complete quote."""


class JsonTransport(Protocol):
    def get_json(self, url: str) -> object: ...


class UrllibJsonTransport:
    """Bounded public HTTPS GET transport; intentionally no header injection."""

    def __init__(self, *, timeout_seconds: float = 10.0, max_response_bytes: int = 2_000_000):
        self.timeout_seconds = float(timeout_seconds)
        self.max_response_bytes = int(max_response_bytes)

    def get_json(self, url: str) -> object:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_PUBLIC_DOMAINS:
            raise AnchorUnavailable("transport rejected non-public or unapproved endpoint")
        request = Request(url, method="GET", headers={"Accept": "application/json", "User-Agent": "lpbot-rwa-readonly/1"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310 - strict allowlist above
                body = response.read(self.max_response_bytes + 1)
                if len(body) > self.max_response_bytes:
                    raise AnchorUnavailable(f"{parsed.hostname}: response exceeds safe size")
                return json.loads(body)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise AnchorUnavailable(f"{parsed.hostname}: public GET failed: {type(exc).__name__}") from exc


def _mapping(value: object, source: str, context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise AnchorUnavailable(f"{source}: {context} must be an object")
    return value


def _list(value: object, source: str, context: str) -> list[object]:
    if not isinstance(value, list):
        raise AnchorUnavailable(f"{source}: {context} must be a list")
    return value


def _nonempty_text(value: object, source: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AnchorUnavailable(f"{source}: missing {field}")
    return value.strip()


def _positive_decimal(value: object, source: str, field: str) -> Decimal:
    if isinstance(value, bool):
        raise AnchorUnavailable(f"{source}: invalid {field}")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise AnchorUnavailable(f"{source}: invalid {field}") from exc
    if not result.is_finite() or result <= 0:
        raise AnchorUnavailable(f"{source}: invalid {field}")
    return result


def _mid(bid: object, ask: object, source: str) -> Decimal:
    if bid is None or ask is None:
        raise AnchorUnavailable(f"{source}: bid/ask unavailable")
    bid_value = _positive_decimal(bid, source, "bid")
    ask_value = _positive_decimal(ask, source, "ask")
    if bid_value > ask_value:
        raise AnchorUnavailable(f"{source}: crossed bid/ask")
    return (bid_value + ask_value) / Decimal("2")


def _iso_timestamp(value: object, source: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AnchorUnavailable(f"{source}: source timestamp unavailable")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise AnchorUnavailable(f"{source}: invalid source timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AnchorUnavailable(f"{source}: source timestamp lacks timezone")
    return parsed.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class _CacheEntry:
    stored_at: float
    quote: PriceObservation


class _CachedClient:
    source_name = "unknown"
    cache_ttl_seconds = 15.0
    max_requests_per_second = 1.0

    def __init__(self, *, transport: JsonTransport | None = None, clock: Callable[[], float] | None = None):
        self._transport = transport or UrllibJsonTransport()
        self._clock = clock or time.time
        self._cache: dict[tuple[str, str], _CacheEntry] = {}
        self._last_fetch_at: float | None = None

    def _cached(self, symbol: str, session: str) -> PriceObservation | None:
        entry = self._cache.get((symbol, session))
        if entry is not None and self._clock() - entry.stored_at < self.cache_ttl_seconds:
            return entry.quote
        return None

    def _begin_fetch(self) -> float:
        now = float(self._clock())
        minimum_interval = 1.0 / self.max_requests_per_second
        if self._last_fetch_at is not None and now - self._last_fetch_at < minimum_interval:
            raise AnchorUnavailable(f"{self.source_name}: local public-API rate limit")
        self._last_fetch_at = now
        return now

    def _store(self, symbol: str, session: str, stored_at: float, observation: PriceObservation) -> PriceObservation:
        self._cache[(symbol, session)] = _CacheEntry(stored_at, observation)
        return observation


class XStocksAnchorClient(_CachedClient):
    """Official Backed/xStocks public API adapter."""

    source_name = "xstocks_official"
    cache_ttl_seconds = 15.0
    max_requests_per_second = 4.0
    base_url = "https://api.backed.fi/api/v1"

    def quote(self, symbol: str, *, market_session: str) -> PriceObservation:
        token_symbol = _nonempty_text(symbol, self.source_name, "symbol")
        cached = self._cached(token_symbol, market_session)
        if cached is not None:
            return cached
        stored_at = self._begin_fetch()
        token_payload = _mapping(self._transport.get_json(f"{self.base_url}/token?type=xstocks"), self.source_name, "token payload")
        nodes = _list(token_payload.get("nodes"), self.source_name, "nodes")
        metadata = next((row for row in nodes if isinstance(row, Mapping) and row.get("symbol") == token_symbol), None)
        if metadata is None:
            raise AnchorUnavailable(f"{self.source_name}: token metadata not found for {token_symbol}")
        multiplier_payload = _mapping(
            self._transport.get_json(
                f"{self.base_url}/token/{quote(token_symbol, safe='')}/multiplier?{urlencode({'network': 'Solana'})}"
            ), self.source_name, "multiplier payload",
        )
        multiplier = _positive_decimal(multiplier_payload.get("currentMultiplier"), self.source_name, "currentMultiplier")
        quote_payload = _mapping(
            self._transport.get_json(f"{self.base_url}/quotes/assets/{quote(token_symbol, safe='')}"),
            self.source_name, "quote payload",
        )
        # AssetAvailabilityResponse defines both values as USD cents.
        price = _mid(quote_payload.get("bid"), quote_payload.get("ask"), self.source_name) / Decimal("100")
        timestamp_value = quote_payload.get("sourceTimestamp", quote_payload.get("timestamp"))
        timestamp = _iso_timestamp(timestamp_value, self.source_name)
        halted = bool(metadata.get("isTradingHalted")) or bool(quote_payload.get("isTradingHalted"))
        session = "HALTED" if halted else market_session
        can_quote = quote_payload.get("canQuote") is True
        observation = PriceObservation(Instrument.from_mapping({
            "instrument_id": f"backed:{token_symbol}",
            "issuer": "Backed",
            "underlying_ticker": _nonempty_text(metadata.get("underlyingSymbol"), self.source_name, "underlyingSymbol"),
            "quote_currency": _nonempty_text(quote_payload.get("currency"), self.source_name, "currency"),
            "multiplier": multiplier,
            "price_semantics": "mid",
            "source_timestamp": timestamp,
            "market_session": session,
            "redemption_status": "PAUSED" if halted else ("OPEN" if can_quote else "CLOSED"),
        }), price, self.source_name)
        return self._store(token_symbol, market_session, stored_at, observation)


class BybitAnchorClient(_CachedClient):
    """Bybit's public xStock spot ticker plus official Backed multiplier metadata."""

    source_name = "bybit_public_spot"
    cache_ttl_seconds = 15.0
    max_requests_per_second = 10.0
    base_url = "https://api.bybit.com"
    metadata_url = "https://api.backed.fi/api/v1"

    def quote(self, symbol: str, *, market_session: str) -> PriceObservation:
        market_symbol = _nonempty_text(symbol, self.source_name, "symbol").upper()
        cached = self._cached(market_symbol, market_session)
        if cached is not None:
            return cached
        stored_at = self._begin_fetch()
        payload = _mapping(self._transport.get_json(
            f"{self.base_url}/v5/market/tickers?{urlencode({'category': 'spot', 'symbol': market_symbol})}"
        ), self.source_name, "ticker payload")
        if payload.get("retCode") != 0:
            raise AnchorUnavailable(f"{self.source_name}: API error {payload.get('retMsg', 'unknown')}")
        result = _mapping(payload.get("result"), self.source_name, "result")
        rows = _list(result.get("list"), self.source_name, "result.list")
        row = next((item for item in rows if isinstance(item, Mapping) and item.get("symbol") == market_symbol), None)
        if row is None:
            raise AnchorUnavailable(f"{self.source_name}: ticker not found for {market_symbol}")
        if not market_symbol.endswith("USDT"):
            raise AnchorUnavailable(f"{self.source_name}: only explicit USDT xStock pairs are supported")
        base = market_symbol[:-4]
        if not base.endswith("X"):
            raise AnchorUnavailable(f"{self.source_name}: symbol is not an xStock")
        token_symbol = base[:-1] + "x"
        multiplier_payload = _mapping(self._transport.get_json(
            f"{self.metadata_url}/token/{quote(token_symbol, safe='')}/multiplier?{urlencode({'network': 'Solana'})}"
        ), self.source_name, "official multiplier payload")
        multiplier = _positive_decimal(multiplier_payload.get("currentMultiplier"), self.source_name, "currentMultiplier")
        try:
            timestamp = datetime.fromtimestamp(int(payload["time"]) / 1000, timezone.utc).isoformat()
        except (KeyError, TypeError, ValueError, OSError) as exc:
            raise AnchorUnavailable(f"{self.source_name}: invalid server timestamp") from exc
        observation = PriceObservation(Instrument.from_mapping({
            "instrument_id": f"backed:{token_symbol}", "issuer": "Backed", "underlying_ticker": base[:-1],
            "quote_currency": "USDT", "multiplier": multiplier, "price_semantics": "mid",
            "source_timestamp": timestamp, "market_session": market_session, "redemption_status": "UNKNOWN",
        }), _mid(row.get("bid1Price"), row.get("ask1Price"), self.source_name), self.source_name)
        return self._store(market_symbol, market_session, stored_at, observation)


class RobinhoodAnchorClient(_CachedClient):
    """Official Robinhood Stock Token read-only REST adapter."""

    source_name = "robinhood_stock_token"
    cache_ttl_seconds = 15.0
    max_requests_per_second = 60.0
    base_url = "https://api.robinhood.com/rhj"

    def quote(self, symbol: str, *, market_session: str) -> PriceObservation:
        token_symbol = _nonempty_text(symbol, self.source_name, "symbol").upper()
        cached = self._cached(token_symbol, market_session)
        if cached is not None:
            return cached
        stored_at = self._begin_fetch()
        price_payload = _mapping(self._transport.get_json(
            f"{self.base_url}/prices/{quote(token_symbol, safe='')}"
        ), self.source_name, "price payload")
        quotes = _list(price_payload.get("quotes"), self.source_name, "quotes")
        price_row = next((row for row in quotes if isinstance(row, Mapping) and row.get("tokenSymbol") == token_symbol), None)
        if price_row is None:
            raise AnchorUnavailable(f"{self.source_name}: quote not found for {token_symbol}")
        asset_payload = _mapping(self._transport.get_json(f"{self.base_url}/assets"), self.source_name, "assets payload")
        assets = _list(asset_payload.get("assets"), self.source_name, "assets")
        asset = next((row for row in assets if isinstance(row, Mapping) and row.get("tokenSymbol") == token_symbol), None)
        if asset is None:
            raise AnchorUnavailable(f"{self.source_name}: asset metadata not found for {token_symbol}")
        multiplier = _positive_decimal(asset.get("currentMultiplier"), self.source_name, "currentMultiplier")
        # Robinhood /prices is raw underlying bid/ask.  Convert to token-equivalent
        # here; normalize_quote divides by the same multiplier back to shares.
        price = _mid(price_row.get("bid"), price_row.get("ask"), self.source_name) * multiplier
        halted = price_row.get("isTradingHalt") is True
        status = asset.get("status")
        redemption = "PAUSED" if halted else ("OPEN" if status == "ASSET_STATUS_ACTIVE" else "UNAVAILABLE")
        observation = PriceObservation(Instrument.from_mapping({
            "instrument_id": f"robinhood:{token_symbol}", "issuer": "Robinhood", "underlying_ticker": token_symbol,
            "quote_currency": _nonempty_text(price_row.get("currency"), self.source_name, "currency"),
            "multiplier": multiplier, "price_semantics": "mid",
            "source_timestamp": _iso_timestamp(price_row.get("generatedAt"), self.source_name),
            "market_session": "HALTED" if halted else market_session, "redemption_status": redemption,
        }), price, self.source_name)
        return self._store(token_symbol, market_session, stored_at, observation)


def quote_to_safe_mapping(observation: PriceObservation) -> dict[str, object]:
    """Small live-smoke output; never exposes response bodies or headers."""

    return {"source": observation.source_name, "price": str(observation.price), "instrument": observation.instrument.to_mapping()}
