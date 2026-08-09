"""FIX-D2 RWA collector daemon contracts."""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from scripts.lp_rwa_anchors_v1_readonly import AnchorUnavailable
from scripts.lp_rwa_collector_daemon_v1_readonly import (
    DEFAULT_INTERVAL_SECS,
    DEFAULT_POOL_IDS,
    DEFAULT_WATCHLIST,
    DexQuote,
    RaydiumDexClient,
    RwaCollector,
    RwaCollectorDaemon,
    main,
)
from scripts.lp_rwa_instrument_v1_readonly import Instrument, PriceObservation


AS_OF = datetime(2026, 8, 7, 15, 0, 1, tzinfo=timezone.utc)


def _observation(
    symbol: str,
    *,
    issuer: str = "Backed",
    instrument_id: str | None = None,
    source: str = "xstocks_official",
    price: str = "100",
    source_timestamp: datetime = AS_OF,
) -> PriceObservation:
    underlying = symbol[:-1].upper()
    return PriceObservation(
        Instrument.from_mapping({
            "instrument_id": instrument_id or f"backed:{symbol}",
            "issuer": issuer,
            "underlying_ticker": underlying,
            "quote_currency": "USD",
            "multiplier": "1",
            "price_semantics": "mid",
            "source_timestamp": source_timestamp.isoformat(),
            "market_session": "REGULAR",
            "redemption_status": "OPEN",
        }),
        Decimal(price),
        source,
    )


class FakeAnchor:
    def __init__(self, factory=None, *, unavailable=False):
        self.factory = factory
        self.unavailable = unavailable
        self.calls = []

    def quote(self, symbol, *, market_session):
        self.calls.append((symbol, market_session))
        if self.unavailable:
            raise AnchorUnavailable("expected unavailable")
        return self.factory(symbol)


class FakeDex:
    def __init__(self, *, price="101", unavailable=False):
        self.price = price
        self.unavailable = unavailable

    def quotes(self, symbols, *, market_session, as_of, reference_instruments):
        if self.unavailable:
            return {}
        return {
            symbol: DexQuote(
                DEFAULT_POOL_IDS[symbol],
                _observation(symbol, source="raydium_api_v3", price=self.price),
            )
            for symbol in symbols
        }


class AlertSpy:
    def __init__(self):
        self.calls = []

    def send_event(self, event_type, message, **kwargs):
        self.calls.append((event_type, message, kwargs))


def _collector(tmp_path, anchors, dex=None, *, watchlist=("SPYx",), alerter=None):
    return RwaCollector(
        watchlist=watchlist,
        clients=anchors,
        dex_client=dex or FakeDex(),
        db_path=tmp_path / "scanner.db",
        jsonl_dir=tmp_path / "jsonl",
        now=lambda: AS_OF,
        sleep=lambda _: None,
        alerter=alerter,
        all_anchor_failure_threshold=2,
    )


def test_defaults_match_fix_d2_task_package():
    assert DEFAULT_WATCHLIST == ("SPYx", "QQQx", "NVDAx", "TSLAx", "CRCLx")
    assert DEFAULT_INTERVAL_SECS == 30.0
    assert set(DEFAULT_POOL_IDS) == set(DEFAULT_WATCHLIST)


def test_all_anchor_unavailable_is_explicit_fail_closed_in_db_and_jsonl(tmp_path):
    anchors = {name: FakeAnchor(unavailable=True) for name in ("xstocks", "bybit", "robinhood")}
    collector = _collector(tmp_path, anchors, dex=FakeDex(unavailable=True))

    result = collector.collect_tick()

    assert result.all_anchors_unavailable is True
    with sqlite3.connect(tmp_path / "scanner.db") as conn:
        rows = conn.execute(
            "SELECT source, reference_price, basis_bps, redemption_status FROM market_sessions"
        ).fetchall()
    assert len(rows) == 4  # three anchors plus the missing Raydium pool quote
    assert all(reference is None and basis is None for _, reference, basis, _ in rows)
    assert all(status == "UNAVAILABLE" for _, _, _, status in rows)
    details = [json.loads(line) for line in (tmp_path / "jsonl/SPYx.jsonl").read_text().splitlines()]
    assert {row["status"] for row in details} == {"unavailable"}
    assert all(row["basis_bps"] is None for row in details)


def test_backed_identity_writes_basis_but_robinhood_cross_issuer_does_not(tmp_path):
    anchors = {
        "xstocks": FakeAnchor(lambda symbol: _observation(symbol, price="100")),
        "bybit": FakeAnchor(lambda _symbol: _observation("SPYx", source="bybit_public_spot", price="100.5")),
        "robinhood": FakeAnchor(lambda symbol: _observation(
            "SPYx",
            issuer="Robinhood",
            instrument_id=f"robinhood:{symbol.rstrip('x').upper()}",
            source="robinhood_stock_token",
            price="99",
        )),
    }
    collector = _collector(tmp_path, anchors)

    collector.collect_tick()

    records = [json.loads(line) for line in (tmp_path / "jsonl/SPYx.jsonl").read_text().splitlines()]
    snapshots = [row for row in records if "instrument" in row]
    by_source = {row["source"]: row for row in snapshots}
    assert by_source["xstocks_official"]["basis_bps"] == "100.00"
    assert by_source["bybit_public_spot"]["basis_bps"] is not None
    assert by_source["robinhood_stock_token"]["basis_bps"] is None
    lead = next(row for row in records if row.get("feature_name") == "cex_dex_basis_lead")
    assert lead["instrument_id"].startswith("robinhood:")
    with sqlite3.connect(tmp_path / "scanner.db") as conn:
        robinhood_basis = conn.execute(
            "SELECT basis_bps FROM market_sessions WHERE source='robinhood_stock_token'"
        ).fetchone()[0]
    assert robinhood_basis is None


def test_consecutive_all_anchor_failure_uses_warning_bridge_once_threshold_reached(tmp_path):
    alerter = AlertSpy()
    anchors = {name: FakeAnchor(unavailable=True) for name in ("xstocks", "bybit", "robinhood")}
    collector = _collector(tmp_path, anchors, alerter=alerter)

    collector.collect_tick()
    collector.collect_tick()

    assert len(alerter.calls) == 1
    event_type, message, kwargs = alerter.calls[0]
    assert event_type == "rwa_all_anchors_unavailable"
    assert "consecutive_ticks=2" in message
    assert kwargs["severity"] == "WARNING"


def test_post_fetch_clock_prevents_valid_later_source_timestamp_from_looking_future(tmp_path):
    later = AS_OF.replace(second=6)
    finished = AS_OF.replace(second=11)
    clock_values = iter((AS_OF, finished))
    anchors = {
        "xstocks": FakeAnchor(lambda _symbol: _observation("SPYx", source_timestamp=later)),
        "bybit": FakeAnchor(unavailable=True),
        "robinhood": FakeAnchor(unavailable=True),
    }
    collector = RwaCollector(
        watchlist=("SPYx",), clients=anchors, dex_client=FakeDex(),
        db_path=tmp_path / "scanner.db", jsonl_dir=tmp_path / "jsonl",
        now=lambda: next(clock_values), sleep=lambda _: None,
    )

    collector.collect_tick()

    snapshots = [
        json.loads(line)
        for line in (tmp_path / "jsonl/SPYx.jsonl").read_text().splitlines()
        if '"instrument"' in line
    ]
    assert next(row for row in snapshots if row["source"] == "xstocks_official")["basis_bps"] == "100.00"


def test_daemon_isolates_tick_exception_and_removes_pid_on_stop(tmp_path):
    calls = []

    def cycle():
        calls.append(len(calls))
        if len(calls) == 1:
            raise RuntimeError("one bad tick")
        daemon.request_stop()

    pid = tmp_path / "collector.pid"
    daemon = RwaCollectorDaemon(cycle, interval_secs=0.001, pid_file=pid)
    thread = threading.Thread(target=daemon.run)
    thread.start()
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert len(calls) == 2
    assert not pid.exists()


def test_once_writes_then_removes_pid(tmp_path):
    pid = tmp_path / "collector.pid"
    daemon = RwaCollectorDaemon(lambda: {"ok": True}, interval_secs=30, pid_file=pid)

    assert daemon.run(once=True) == 0
    assert not pid.exists()


def test_main_once_with_injected_clients_persists_one_tick(tmp_path):
    anchors = {
        "xstocks": FakeAnchor(lambda _symbol: _observation("SPYx")),
        "bybit": FakeAnchor(lambda _symbol: _observation("SPYx", source="bybit_public_spot")),
        "robinhood": FakeAnchor(lambda _symbol: _observation(
            "SPYx", issuer="Robinhood", instrument_id="robinhood:SPY",
            source="robinhood_stock_token",
        )),
    }
    db = tmp_path / "scanner.db"

    rc = main(
        ["--once", "--watchlist", "SPYx", "--db", str(db),
         "--jsonl-dir", str(tmp_path / "jsonl")],
        clients=anchors,
        dex_client=FakeDex(),
        now=lambda: AS_OF,
        sleep=lambda _: None,
        alerter=AlertSpy(),
    )

    assert rc == 0
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM market_sessions").fetchone()[0] == 4


def test_sigterm_gracefully_stops_process_and_removes_pid(tmp_path):
    pid = tmp_path / "collector.pid"
    code = (
        "from scripts.lp_rwa_collector_daemon_v1_readonly import RwaCollectorDaemon;"
        f"raise SystemExit(RwaCollectorDaemon(lambda: None, interval_secs=30, pid_file={str(pid)!r}).run())"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", code], cwd=str(Path(__file__).resolve().parents[1])
    )
    try:
        deadline = time.monotonic() + 2
        while not pid.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert pid.exists()
        os.kill(process.pid, signal.SIGTERM)
        assert process.wait(timeout=2) == 0
        assert not pid.exists()
    finally:
        if process.poll() is None:
            process.kill()


def test_raydium_client_is_public_get_only_and_parses_mid_with_injected_transport():
    calls = []

    class Transport:
        def get_json(self, url):
            calls.append(url)
            return {"success": True, "data": [{
                "id": DEFAULT_POOL_IDS["SPYx"],
                "price": "101.25",
                "mintA": {"symbol": "SPYx"},
                "mintB": {"symbol": "USDC"},
            }]}

    client = RaydiumDexClient(transport=Transport(), pool_ids={"SPYx": DEFAULT_POOL_IDS["SPYx"]})
    out = client.quotes(
        ("SPYx",), market_session="REGULAR", as_of=AS_OF,
        reference_instruments={"SPYx": _observation("SPYx").instrument},
    )

    assert str(out["SPYx"].observation.price) == "101.25"
    assert calls == [
        "https://api-v3.raydium.io/pools/info/ids?ids=" + DEFAULT_POOL_IDS["SPYx"]
    ]
