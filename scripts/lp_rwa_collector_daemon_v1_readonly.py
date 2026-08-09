#!/usr/bin/env python3
"""Persistent, keyless RWA session collector for the M0 shadow period.

The collector only performs public HTTPS GETs.  It has no wallet, key,
transaction, signing, or broadcast surface.  Each tick records explicit
unavailability rather than silently substituting a stale or unrelated price.
Direct basis is calculated only when both observations have the same
``economic_identity`` (INV-RWA-01).  Robinhood cross-issuer spreads are kept
solely as append-only ``ShadowBasisLeadLogger`` features.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rwa_anchors_v1_readonly import (  # noqa: E402
    BybitAnchorClient,
    RobinhoodAnchorClient,
    XStocksAnchorClient,
)
from scripts.lp_rwa_instrument_v1_readonly import (  # noqa: E402
    Instrument,
    InstrumentValidationError,
    PriceObservation,
    normalize_quote,
)
from scripts.lp_rwa_session_v1_readonly import (  # noqa: E402
    RwaSession,
    ShadowBasisLeadLogger,
    SnapshotRecorder,
    classify_us_equity_session,
)
from scripts.lp_scanner_daemon_v1_readonly import ScannerStore  # noqa: E402
from scripts.lp_tg_alerter_v1_readonly import (  # noqa: E402
    TelegramAlerter,
    safe_send_event,
)


DEFAULT_WATCHLIST = ("SPYx", "QQQx", "NVDAx", "TSLAx", "CRCLx")
DEFAULT_INTERVAL_SECS = 30.0
DEFAULT_ALL_ANCHOR_FAILURE_THRESHOLD = 3
DEFAULT_DB_PATH = REPO_ROOT / "reports/lp_scanner/scanner.db"
DEFAULT_JSONL_DIR = REPO_ROOT / "reports/lp_scanner/rwa_sessions"
RAYDIUM_API_ROOT = "https://api-v3.raydium.io"

# Highest-liquidity Raydium USDC pools verified in MARKET_SNAPSHOT_M0.md.
DEFAULT_POOL_IDS = {
    "SPYx": "6truu3rZuiB9rKQg4VYC3Dt3QwV7DgwGqXrYUcrvnDDE",
    "QQQx": "GMjGLWzvK75LPetrgAmdeXnvxc4fUuQPwJxeQqTDU1aG",
    "NVDAx": "49iMatQtoyabsYAQc8GafVq6aeBFVDxSRH44oiatyyw6",
    "TSLAx": "8aDaBQkTrS6HVMjyc6EZebgdiaXhLYGriDWKWWp1NpFF",
    "CRCLx": "G39wywquKbHK8F2wZZZFX3fcsyG91VCCbbr6WEVp5axy",
}

ANCHOR_NAMES = ("xstocks", "bybit", "robinhood")
ANCHOR_SOURCES = {
    "xstocks": "xstocks_official",
    "bybit": "bybit_public_spot",
    "robinhood": "robinhood_stock_token",
}


class JsonTransport(Protocol):
    def get_json(self, url: str) -> object: ...


class RaydiumUnavailable(RuntimeError):
    """The free Raydium v3 endpoint did not provide a safe current pool mid."""


class RaydiumJsonTransport:
    """Bounded GET-only transport locked to Raydium's free API v3 host."""

    def __init__(self, *, timeout_seconds: float = 10.0, max_response_bytes: int = 4_000_000):
        self.timeout_seconds = float(timeout_seconds)
        self.max_response_bytes = int(max_response_bytes)

    def get_json(self, url: str) -> object:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "api-v3.raydium.io":
            raise RaydiumUnavailable("transport rejected non-public or unapproved endpoint")
        request = Request(
            url,
            method="GET",
            headers={"Accept": "application/json", "User-Agent": "lpbot-rwa-readonly/1"},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310 - host allowlist above
                body = response.read(self.max_response_bytes + 1)
                if len(body) > self.max_response_bytes:
                    raise RaydiumUnavailable("Raydium response exceeds safe size")
                return json.loads(body)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RaydiumUnavailable(f"Raydium public GET failed: {type(exc).__name__}") from exc


def _positive_decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool):
        raise RaydiumUnavailable(f"invalid {field}")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise RaydiumUnavailable(f"invalid {field}") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise RaydiumUnavailable(f"invalid {field}")
    return parsed


def _underlying(symbol: str) -> str:
    value = str(symbol).strip()
    if len(value) < 2 or not value.endswith("x") or not value[:-1].isalnum():
        raise ValueError(f"invalid xStock symbol: {symbol}")
    return value[:-1].upper()


def _bybit_symbol(symbol: str) -> str:
    return f"{_underlying(symbol)}XUSDT"


@dataclass(frozen=True)
class DexQuote:
    pool_id: str
    observation: PriceObservation


class RaydiumDexClient:
    """Batch reader for known Raydium xStock/USDC pool mids."""

    def __init__(
        self,
        *,
        transport: JsonTransport | None = None,
        pool_ids: Mapping[str, str] | None = None,
    ):
        self.transport = transport or RaydiumJsonTransport()
        self.pool_ids = dict(DEFAULT_POOL_IDS if pool_ids is None else pool_ids)

    @staticmethod
    def _instrument(
        symbol: str,
        *,
        market_session: str,
        as_of: datetime,
        reference: Instrument | None,
    ) -> Instrument:
        if reference is not None and reference.economic_identity == (
            "backed", f"backed:{symbol}".casefold(), _underlying(symbol)
        ):
            raw = reference.to_mapping()
            raw.update({
                "quote_currency": "USD",
                "source_timestamp": as_of.astimezone(timezone.utc).isoformat(),
                "market_session": market_session,
                "redemption_status": reference.redemption_status,
            })
            return Instrument.from_mapping(raw)
        return Instrument.from_mapping({
            "instrument_id": f"backed:{symbol}",
            "issuer": "Backed",
            "underlying_ticker": _underlying(symbol),
            "quote_currency": "USD",
            # Without a fresh official/Bybit instrument the multiplier is not
            # trusted for basis; this placeholder remains snapshot-only.
            "multiplier": "1",
            "price_semantics": "mid",
            "source_timestamp": as_of.astimezone(timezone.utc).isoformat(),
            "market_session": market_session,
            "redemption_status": "UNKNOWN",
        })

    def quotes(
        self,
        symbols: Sequence[str],
        *,
        market_session: str,
        as_of: datetime,
        reference_instruments: Mapping[str, Instrument],
    ) -> dict[str, DexQuote]:
        requested = {symbol: self.pool_ids.get(symbol) for symbol in symbols}
        ids = [pool_id for pool_id in requested.values() if pool_id]
        if not ids:
            return {}
        url = f"{RAYDIUM_API_ROOT}/pools/info/ids?{urlencode({'ids': ','.join(ids)})}"
        payload = self.transport.get_json(url)
        if not isinstance(payload, Mapping) or payload.get("success") is not True:
            raise RaydiumUnavailable("Raydium API reported unsuccessful response")
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise RaydiumUnavailable("Raydium data must be a list")
        by_pool = {
            str(row.get("id")): row
            for row in rows
            if isinstance(row, Mapping) and row.get("id") in set(ids)
        }
        result: dict[str, DexQuote] = {}
        for symbol, pool_id in requested.items():
            row = by_pool.get(str(pool_id))
            if row is None:
                continue
            mint_a = row.get("mintA")
            mint_b = row.get("mintB")
            if not isinstance(mint_a, Mapping) or not isinstance(mint_b, Mapping):
                continue
            symbol_a = str(mint_a.get("symbol") or "")
            symbol_b = str(mint_b.get("symbol") or "")
            raw_price = _positive_decimal(row.get("price"), "Raydium price")
            if symbol_a == symbol and symbol_b == "USDC":
                price = raw_price
            elif symbol_b == symbol and symbol_a == "USDC":
                price = Decimal("1") / raw_price
            else:
                continue
            instrument = self._instrument(
                symbol,
                market_session=market_session,
                as_of=as_of,
                reference=reference_instruments.get(symbol),
            )
            result[symbol] = DexQuote(
                str(pool_id), PriceObservation(instrument, price, "raydium_api_v3")
            )
        return result


def _basis_bps_same_identity(
    left: PriceObservation,
    reference: PriceObservation,
    *,
    now: datetime,
) -> Decimal | None:
    left_instrument = left.instrument
    reference_instrument = reference.instrument
    if (
        left_instrument.economic_identity != reference_instrument.economic_identity
        or left_instrument.price_semantics != reference_instrument.price_semantics
        or left_instrument.market_session != reference_instrument.market_session
        or left_instrument.quote_currency not in {"USD", "USDC", "USDT"}
        or reference_instrument.quote_currency not in {"USD", "USDC", "USDT"}
    ):
        return None
    try:
        normalized_left = normalize_quote(left, now=now)
        normalized_reference = normalize_quote(reference, now=now)
    except InstrumentValidationError:
        return None
    value = (
        abs(normalized_left.normalized_price - normalized_reference.normalized_price)
        / normalized_reference.normalized_price
        * Decimal("10000")
    )
    return value.quantize(Decimal("0.01"))


def _shadow_spread_bps(
    left: PriceObservation,
    reference: PriceObservation,
    *,
    now: datetime,
) -> Decimal | None:
    """Normalized cross-issuer spread for shadow logging, never direct basis."""
    try:
        normalized_left = normalize_quote(left, now=now)
        normalized_reference = normalize_quote(reference, now=now)
    except InstrumentValidationError:
        return None
    value = (
        abs(normalized_left.normalized_price - normalized_reference.normalized_price)
        / normalized_reference.normalized_price
        * Decimal("10000")
    )
    return value.quantize(Decimal("0.01"))


def _json_default(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _append_status(sink: Any, record: Mapping[str, object]) -> None:
    sink.write(json.dumps(dict(record), sort_keys=True, separators=(",", ":"), default=_json_default) + "\n")
    sink.flush()


@dataclass(frozen=True)
class TickResult:
    as_of: str
    symbols: int
    available_anchors: int
    available_dex_quotes: int
    all_anchors_unavailable: bool
    market_session_rows: int


class RwaCollector:
    """One-tick RWA collector with all external clients and clocks injected."""

    def __init__(
        self,
        *,
        watchlist: Sequence[str] = DEFAULT_WATCHLIST,
        clients: Mapping[str, Any] | None = None,
        dex_client: Any = None,
        db_path: str | os.PathLike[str] = DEFAULT_DB_PATH,
        jsonl_dir: str | os.PathLike[str] = DEFAULT_JSONL_DIR,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        sleep: Callable[[float], None] = time.sleep,
        alerter: Any = None,
        all_anchor_failure_threshold: int = DEFAULT_ALL_ANCHOR_FAILURE_THRESHOLD,
    ):
        symbols = tuple(str(symbol).strip() for symbol in watchlist)
        if not symbols or len(set(symbols)) != len(symbols):
            raise ValueError("watchlist must contain unique symbols")
        for symbol in symbols:
            _underlying(symbol)
        if all_anchor_failure_threshold <= 0:
            raise ValueError("all-anchor failure threshold must be positive")
        self.watchlist = symbols
        self.clients = dict(clients or {
            "xstocks": XStocksAnchorClient(),
            "bybit": BybitAnchorClient(),
            "robinhood": RobinhoodAnchorClient(),
        })
        missing = set(ANCHOR_NAMES) - set(self.clients)
        if missing:
            raise ValueError(f"missing anchor clients: {sorted(missing)}")
        self.dex_client = dex_client or RaydiumDexClient()
        self.db_path = Path(db_path)
        self.jsonl_dir = Path(jsonl_dir)
        self.now = now
        self.sleep = sleep
        self.alerter = alerter
        self.all_anchor_failure_threshold = int(all_anchor_failure_threshold)
        self._consecutive_all_anchor_failures = 0

    def _anchor_symbol(self, source: str, symbol: str) -> str:
        if source == "bybit":
            return _bybit_symbol(symbol)
        if source == "robinhood":
            return _underlying(symbol)
        return symbol

    def _collect_anchors(
        self, market_session: str
    ) -> tuple[dict[str, dict[str, PriceObservation]], dict[str, dict[str, str]]]:
        observations = {symbol: {} for symbol in self.watchlist}
        failures = {symbol: {} for symbol in self.watchlist}
        for source in ANCHOR_NAMES:
            client = self.clients[source]
            for index, symbol in enumerate(self.watchlist):
                try:
                    observation = client.quote(
                        self._anchor_symbol(source, symbol), market_session=market_session
                    )
                    if not isinstance(observation, PriceObservation):
                        raise TypeError("anchor returned non-PriceObservation")
                    observations[symbol][source] = observation
                except Exception as exc:  # noqa: BLE001 - one unavailable anchor cannot abort a tick
                    failures[symbol][source] = type(exc).__name__
                # XStocks performs up to three GETs per quote under a 4 rps
                # sliding-window gate.  Space symbols so the adapter never
                # manufactures local rate-limit failures during normal use.
                if source == "xstocks" and index + 1 < len(self.watchlist):
                    self.sleep(1.01)
        return observations, failures

    @staticmethod
    def _unavailable_row(
        *, symbol: str, source: str, market_session: str, pool: str
    ) -> dict[str, object]:
        instrument_id = (
            f"robinhood:{_underlying(symbol)}"
            if source == "robinhood"
            else f"backed:{symbol}"
        )
        return {
            "instrument_id": instrument_id,
            "pool": pool,
            "market_session": market_session,
            "source_timestamp": None,
            "reference_price": None,
            "basis_bps": None,
            "redemption_status": "UNAVAILABLE",
            "source": ANCHOR_SOURCES.get(source, source) + ":unavailable",
        }

    @staticmethod
    def _available_row(
        observation: PriceObservation,
        *,
        pool: str,
        basis_bps: Decimal | None,
    ) -> dict[str, object]:
        return {
            "instrument_id": observation.instrument.instrument_id,
            "pool": pool,
            "market_session": observation.instrument.market_session,
            "source_timestamp": observation.instrument.source_timestamp.isoformat(),
            "reference_price": float(observation.price),
            "basis_bps": None if basis_bps is None else float(basis_bps),
            "redemption_status": observation.instrument.redemption_status,
            "source": observation.source_name,
        }

    def _write_symbol(
        self,
        *,
        symbol: str,
        as_of: datetime,
        market_session: str,
        anchors: Mapping[str, PriceObservation],
        failures: Mapping[str, str],
        dex: DexQuote | None,
        freshness_as_of: datetime,
    ) -> list[dict[str, object]]:
        self.jsonl_dir.mkdir(parents=True, exist_ok=True)
        path = self.jsonl_dir / f"{symbol}.jsonl"
        rows: list[dict[str, object]] = []
        with path.open("a", encoding="utf-8") as sink:
            recorder = SnapshotRecorder(sink)
            lead_logger = ShadowBasisLeadLogger(sink)
            dex_basis: Decimal | None = None
            if dex is not None:
                for source in ("xstocks", "bybit"):
                    anchor = anchors.get(source)
                    if anchor is not None:
                        dex_basis = _basis_bps_same_identity(
                            dex.observation, anchor, now=freshness_as_of
                        )
                    if dex_basis is not None:
                        break
                recorder.append(
                    as_of=as_of,
                    instrument=dex.observation.instrument,
                    observed_price=dex.observation.price,
                    basis_bps=dex_basis,
                    source=dex.observation.source_name,
                )
                rows.append(self._available_row(
                    dex.observation, pool=dex.pool_id, basis_bps=dex_basis
                ))
            else:
                pool = getattr(self.dex_client, "pool_ids", {}).get(symbol, DEFAULT_POOL_IDS.get(symbol, ""))
                _append_status(sink, {
                    "as_of": as_of.astimezone(timezone.utc).isoformat(),
                    "symbol": symbol,
                    "source": "raydium_api_v3",
                    "status": "unavailable",
                    "failure": "RaydiumUnavailable",
                    "basis_bps": None,
                    "session": market_session,
                })
                rows.append(self._unavailable_row(
                    symbol=symbol, source="raydium_api_v3", market_session=market_session,
                    pool=str(pool or f"raydium:{symbol}:unavailable"),
                ))

            for source in ANCHOR_NAMES:
                observation = anchors.get(source)
                if observation is None:
                    _append_status(sink, {
                        "as_of": as_of.astimezone(timezone.utc).isoformat(),
                        "symbol": symbol,
                        "source": ANCHOR_SOURCES[source],
                        "status": "unavailable",
                        "failure": failures.get(source, "AnchorUnavailable"),
                        "basis_bps": None,
                        "session": market_session,
                    })
                    rows.append(self._unavailable_row(
                        symbol=symbol,
                        source=source,
                        market_session=market_session,
                        pool=f"anchor:{source}",
                    ))
                    continue

                direct_basis = None
                if source != "robinhood" and dex is not None:
                    direct_basis = _basis_bps_same_identity(
                        dex.observation, observation, now=freshness_as_of
                    )
                recorder.append(
                    as_of=as_of,
                    instrument=observation.instrument,
                    observed_price=observation.price,
                    basis_bps=direct_basis,
                    source=observation.source_name,
                )
                rows.append(self._available_row(
                    observation, pool=f"anchor:{source}", basis_bps=direct_basis
                ))

                if source == "robinhood" and dex is not None:
                    shadow_spread = _shadow_spread_bps(
                        observation, dex.observation, now=freshness_as_of
                    )
                    if shadow_spread is not None:
                        lead_logger.log(
                            as_of=as_of,
                            instrument_id=observation.instrument.instrument_id,
                            cex_source=observation.source_name,
                            dex_source=dex.observation.source_name,
                            cex_price=observation.price,
                            dex_price=dex.observation.price,
                            basis_bps=shadow_spread,
                            session=RwaSession(market_session),
                        )
        return rows

    def collect_tick(self) -> TickResult:
        as_of = self.now()
        if not isinstance(as_of, datetime) or as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("now() must return a timezone-aware datetime")
        as_of = as_of.astimezone(timezone.utc)
        market_session = classify_us_equity_session(as_of).session.value
        observations, failures = self._collect_anchors(market_session)
        reference_instruments: dict[str, Instrument] = {}
        for symbol, anchors in observations.items():
            reference = anchors.get("xstocks") or anchors.get("bybit")
            if reference is not None:
                reference_instruments[symbol] = reference.instrument
        try:
            dex_quotes = self.dex_client.quotes(
                self.watchlist,
                market_session=market_session,
                as_of=as_of,
                reference_instruments=reference_instruments,
            )
            if not isinstance(dex_quotes, Mapping):
                raise TypeError("DEX client returned non-mapping")
        except Exception as exc:  # noqa: BLE001 - DEX outage is explicit per symbol
            dex_quotes = {}
            print(
                f"[rwa-collector] Raydium unavailable error_type={type(exc).__name__}",
                file=sys.stderr,
                flush=True,
            )

        # The tick's persisted ``as_of`` is captured before I/O, while public
        # endpoints may stamp responses a few seconds later.  Freshness must be
        # evaluated against a post-fetch clock sample so those quotes are not
        # falsely rejected as future data.
        freshness_as_of = self.now()
        if (
            not isinstance(freshness_as_of, datetime)
            or freshness_as_of.tzinfo is None
            or freshness_as_of.utcoffset() is None
        ):
            raise ValueError("now() must return a timezone-aware datetime")
        freshness_as_of = freshness_as_of.astimezone(timezone.utc)

        rows: list[dict[str, object]] = []
        for symbol in self.watchlist:
            try:
                rows.extend(self._write_symbol(
                    symbol=symbol,
                    as_of=as_of,
                    market_session=market_session,
                    anchors=observations[symbol],
                    failures=failures[symbol],
                    dex=dex_quotes.get(symbol),
                    freshness_as_of=freshness_as_of,
                ))
            except Exception as exc:  # noqa: BLE001 - isolate a malformed symbol
                print(
                    f"[rwa-collector] symbol={symbol} failed error_type={type(exc).__name__}",
                    file=sys.stderr,
                    flush=True,
                )

        ScannerStore(self.db_path).write_cycle(
            as_of,
            pool_snapshots=[],
            opportunity_scores=[],
            market_sessions=rows,
        )
        available_anchors = sum(len(item) for item in observations.values())
        all_unavailable = available_anchors == 0
        if all_unavailable:
            self._consecutive_all_anchor_failures += 1
            if self._consecutive_all_anchor_failures >= self.all_anchor_failure_threshold:
                safe_send_event(
                    self.alerter,
                    "rwa_all_anchors_unavailable",
                    "RWA collector all three anchors unavailable "
                    f"consecutive_ticks={self._consecutive_all_anchor_failures}; fail-closed",
                    severity="WARNING",
                    throttle_key="rwa:all-anchors-unavailable",
                )
        else:
            self._consecutive_all_anchor_failures = 0
        return TickResult(
            as_of=as_of.isoformat(),
            symbols=len(self.watchlist),
            available_anchors=available_anchors,
            available_dex_quotes=len(dex_quotes),
            all_anchors_unavailable=all_unavailable,
            market_session_rows=len(rows),
        )


class RwaCollectorDaemon:
    """SIGTERM-aware 30-second loop; failed ticks never kill later ticks."""

    def __init__(
        self,
        cycle: Callable[[], Any],
        *,
        interval_secs: float = DEFAULT_INTERVAL_SECS,
        pid_file: str | os.PathLike[str] | None = None,
        on_shutdown: Callable[[], None] | None = None,
    ):
        if interval_secs <= 0:
            raise ValueError("collector interval must be positive")
        self.cycle = cycle
        self.interval_secs = float(interval_secs)
        self.pid_file = Path(pid_file) if pid_file else None
        self.on_shutdown = on_shutdown
        self._stop = threading.Event()

    def request_stop(self, signum: int | None = None, frame: Any = None) -> None:
        del signum, frame
        self._stop.set()

    def _write_pid(self) -> None:
        if self.pid_file is None:
            return
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file.write_text(str(os.getpid()) + "\n", encoding="utf-8")

    def _remove_own_pid(self) -> None:
        if self.pid_file is None or not self.pid_file.exists():
            return
        try:
            if self.pid_file.read_text(encoding="utf-8").strip() == str(os.getpid()):
                self.pid_file.unlink()
        except OSError:
            pass

    def _run_tick(self) -> bool:
        try:
            result = self.cycle()
            print(f"[rwa-collector] tick={result}", flush=True)
            return True
        except Exception as exc:  # noqa: BLE001 - daemon tick isolation contract
            print(
                f"[rwa-collector] tick failed error_type={type(exc).__name__}",
                file=sys.stderr,
                flush=True,
            )
            return False

    def run(self, *, once: bool = False) -> int:
        previous: dict[int, Any] = {}
        if threading.current_thread() is threading.main_thread():
            for signum in (signal.SIGINT, signal.SIGTERM):
                previous[signum] = signal.getsignal(signum)
                signal.signal(signum, self.request_stop)
        self._write_pid()
        try:
            if not self._stop.is_set():
                succeeded = self._run_tick()
                if once:
                    return 0 if succeeded else 1
            while not self._stop.wait(self.interval_secs):
                self._run_tick()
            return 0
        finally:
            if self.on_shutdown is not None:
                self.on_shutdown()
            self._remove_own_pid()
            for signum, handler in previous.items():
                signal.signal(signum, handler)


def _positive(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Persistent read-only RWA session collector")
    parser.add_argument("--once", action="store_true", help="collect one tick then exit")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--jsonl-dir", default=str(DEFAULT_JSONL_DIR))
    parser.add_argument("--pid-file", default=None)
    parser.add_argument("--interval-secs", type=_positive, default=DEFAULT_INTERVAL_SECS)
    parser.add_argument("--watchlist", default=",".join(DEFAULT_WATCHLIST))
    parser.add_argument(
        "--pool", action="append", default=[], metavar="SYMBOL=POOL_ID",
        help="override/add a Raydium pool mapping",
    )
    parser.add_argument(
        "--all-anchor-failure-threshold", type=int,
        default=DEFAULT_ALL_ANCHOR_FAILURE_THRESHOLD,
    )
    return parser


def _pool_overrides(values: Sequence[str]) -> dict[str, str]:
    result = dict(DEFAULT_POOL_IDS)
    for raw in values:
        symbol, separator, pool_id = raw.partition("=")
        symbol, pool_id = symbol.strip(), pool_id.strip()
        if not separator or not symbol or not pool_id:
            raise ValueError("--pool must be SYMBOL=POOL_ID")
        _underlying(symbol)
        result[symbol] = pool_id
    return result


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    clients: Mapping[str, Any] | None = None,
    dex_client: Any = None,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    sleep: Callable[[float], None] = time.sleep,
    alerter: Any = None,
) -> int:
    args = _parser().parse_args(argv)
    watchlist = tuple(item.strip() for item in args.watchlist.split(",") if item.strip())
    if args.all_anchor_failure_threshold <= 0:
        _parser().error("all-anchor-failure-threshold must be positive")
    try:
        pool_ids = _pool_overrides(args.pool)
        selected_dex = dex_client or RaydiumDexClient(pool_ids=pool_ids)
        selected_alerter = TelegramAlerter.from_env() if alerter is None else alerter
        collector = RwaCollector(
            watchlist=watchlist,
            clients=clients,
            dex_client=selected_dex,
            db_path=args.db,
            jsonl_dir=args.jsonl_dir,
            now=now,
            sleep=sleep,
            alerter=selected_alerter,
            all_anchor_failure_threshold=args.all_anchor_failure_threshold,
        )
    except ValueError as exc:
        _parser().error(str(exc))
    pid_file = args.pid_file or str(Path(args.db).with_name("rwa_collector.pid"))
    return RwaCollectorDaemon(
        collector.collect_tick,
        interval_secs=args.interval_secs,
        pid_file=pid_file,
    ).run(once=args.once)


if __name__ == "__main__":
    raise SystemExit(main())
