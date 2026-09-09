"""Paired tests for scripts/lp_rh_collector_v1_readonly.py (RH-02c round 2).

The collector is running in production (72h forward observation); this file
only adds its missing paired tests. All RPC traffic is injected via fake
rpc_fn callables (never the network), all databases live under tmp_path
(never reports/lp_rh/, the live store).
"""
from __future__ import annotations

import os
import subprocess
from decimal import Decimal
from pathlib import Path

from scripts import lp_rh_collector_v1_readonly as collector
from scripts.lp_rh_store_v1_readonly import migrate, open_store

# sqrtPriceX96 observed on-chain for the identity-gated target pool
# (token0=WETH dec0=18, token1=USDG dec1=6); price ~ 2490.58 USDG/WETH.
SQRT_PRICE = 3953938817749275760872870
SLOT0_HEX = "0x" + format(SQRT_PRICE, "064x")
BLOCK_HEX = "0x1dcd1"


def _fake_rpc(fail_block=False, fail_calls=frozenset()):
    """Injected rpc_fn returning (result, error, latency_ms); no network.

    fail_calls is a subset of {"slot0", "liquidity", "balance"}.
    """
    def rpc_fn(method, params=None, **_kw):
        if method == "eth_getBlockByNumber":
            if fail_block:
                return None, {"code": -32601, "message": "method not found"}, 12
            return {"number": BLOCK_HEX, "hash": "0xh", "timestamp": "0x65",
                    "baseFeePerGas": "0x3b9aca00"}, None, 5
        assert method == "eth_call"
        data = params[0]["data"]
        if data == collector.SEL_DECIMALS:
            dec = "0x12" if params[0]["to"] == collector.TOKEN0 else "0x6"
            return dec, None, 4
        kind = ("slot0" if data == collector.SEL_SLOT0
                else "liquidity" if data == collector.SEL_LIQUIDITY
                else "balance")
        if kind in fail_calls:
            return None, {"code": -32603, "message": f"{kind} failed"}, 9
        return SLOT0_HEX if kind == "slot0" else "0x1", None, 4
    return rpc_fn


def _open(tmp_path):
    conn = open_store(tmp_path / "rh_test.db")
    migrate(conn)
    return conn


def _count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _unique_stamps():
    """Monotonic fake _utc_now: unique RFC3339 stamps, no clock dependency."""
    state = {"i": 0}

    def stamp():
        state["i"] += 1
        i = state["i"]
        return "2026-09-08T00:%02d:%02d.000000Z" % (i // 60, i % 60)

    return stamp


# --- 1. price precision (the costliest bug in this project) -----------------
def test_price_precision_usdg_six_decimals():
    # USDG is a 6-decimal asset (dec1=6); WETH is 18 (dec0=18).
    price = collector.compute_price_human(SQRT_PRICE, 18, 6)
    assert Decimal("2490.0") < price < Decimal("2491.0")
    wrong = collector.compute_price_human(SQRT_PRICE, 18, 18)
    assert wrong < Decimal("1e-6")
    # 10**(18-6) = 1e12 apart: assuming dec1=18 is the classic 1e12 error.
    assert price / wrong == Decimal("1e12")


# --- 2. T12: a JSON-RPC error is never a 0 ----------------------------------
def test_rpc_error_keeps_last_good_block(tmp_path):
    conn = _open(tmp_path)
    try:
        out = collector.collect_round(
            conn, dec0=18, dec1=6, last_good_block=193000,
            rpc_fn=_fake_rpc(fail_block=True))
        error, last_good, state = conn.execute(
            "SELECT error, last_good_block, state FROM rh_rpc_health"
        ).fetchone()
        assert error  # error text recorded, not silently dropped
        assert last_good == 193000  # previous value kept, not 0/None
        assert out["block_number"] == 193000
        assert state == "DEGRADED"
    finally:
        conn.close()


# --- 3. rpc health state machine ---------------------------------------------
def test_rpc_health_state_transitions(tmp_path):
    conn = _open(tmp_path)
    try:
        collector.collect_round(conn, dec0=18, dec1=6, last_good_block=None,
                                rpc_fn=_fake_rpc())
        collector.collect_round(conn, dec0=18, dec1=6, last_good_block=None,
                                rpc_fn=_fake_rpc(fail_calls={"slot0"}))
        collector.collect_round(
            conn, dec0=18, dec1=6, last_good_block=None,
            rpc_fn=_fake_rpc(fail_block=True,
                             fail_calls={"slot0", "liquidity", "balance"}))
        states = [row[0] for row in conn.execute(
            "SELECT state FROM rh_rpc_health ORDER BY rowid")]
        assert states == ["NORMAL", "DEGRADED", "EXIT_ONLY"]
    finally:
        conn.close()


# --- 4. one successful round writes exactly one row per table ----------------
def test_successful_round_writes_one_row_per_table(tmp_path):
    conn = _open(tmp_path)
    try:
        collector.collect_round(conn, dec0=18, dec1=6, last_good_block=None,
                                rpc_fn=_fake_rpc())
        for table in ("rh_market_states", "rh_rpc_health",
                      "rh_source_snapshots"):
            assert _count(conn, table) == 1
    finally:
        conn.close()


# --- 5. market-state row fields ----------------------------------------------
def test_market_state_row_fields(tmp_path):
    conn = _open(tmp_path)
    try:
        collector.collect_round(conn, dec0=18, dec1=6, last_good_block=None,
                                rpc_fn=_fake_rpc())
        mid, session, chain_id = conn.execute(
            "SELECT reference_mid, session, chain_id FROM rh_market_states"
        ).fetchone()
        assert Decimal(mid)  # decimal text, parseable by the store guard
        assert Decimal("2490.0") < Decimal(mid) < Decimal("2491.0")
        assert session == "UNKNOWN"
        assert chain_id == 4663
    finally:
        conn.close()


# --- 6. snapshot idempotency --------------------------------------------------
def test_identical_payload_snapshot_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(collector, "_utc_now", _unique_stamps())
    conn = _open(tmp_path)
    try:
        rpc = _fake_rpc()
        collector.collect_round(conn, dec0=18, dec1=6, last_good_block=None,
                                rpc_fn=rpc)
        collector.collect_round(conn, dec0=18, dec1=6, last_good_block=None,
                                rpc_fn=rpc)  # identical raw payload
        assert _count(conn, "rh_source_snapshots") == 1  # dup swallowed
        assert _count(conn, "rh_market_states") == 2     # still recorded
        assert _count(conn, "rh_rpc_health") == 2
    finally:
        conn.close()


# --- 7. backoff cap ------------------------------------------------------------
def test_backoff_exponent_capped():
    assert collector.backoff_seconds(2000) == collector.backoff_seconds(11)
    assert collector.backoff_seconds(2000) == 1.0 * 2 ** 10


# --- 8/9. pid file double-write guard -----------------------------------------
def test_pid_file_blocks_second_instance(tmp_path):
    pid_file = tmp_path / "collector.pid"
    pid_file.write_text(str(os.getpid()))
    assert collector.pid_file_is_free(str(pid_file)) is False
    rc = collector.run(str(tmp_path / "rh.db"), interval_secs=0,
                       max_rounds=1, pid_file=str(pid_file), once=True,
                       rpc_fn=_fake_rpc())
    assert rc == 2


def test_stale_pid_file_is_free(tmp_path):
    proc = subprocess.Popen(["true"])
    proc.wait()
    dead_pid = proc.pid  # exited, definitely dead
    pid_file = tmp_path / "collector.pid"
    pid_file.write_text(str(dead_pid))
    assert collector.pid_file_is_free(str(pid_file)) is True


# --- 10. budget gate (T57) ------------------------------------------------------
def test_budget_over_stops_collection_cleanly(tmp_path, monkeypatch):
    monkeypatch.setattr(
        collector, "budget_status",
        lambda path: {"state": "OVER", "bytes": 1,
                      "soft_budget_bytes": 1, "fraction": 1.0})
    monkeypatch.setattr(collector, "_utc_now", _unique_stamps())
    rc = collector.run(str(tmp_path / "rh.db"), interval_secs=0,
                       max_rounds=25, pid_file=None, once=False,
                       rpc_fn=_fake_rpc())
    assert rc == 0  # budget stop is clean, not a crash
    conn = open_store(str(tmp_path / "rh.db"))
    try:
        # round-20 gate fired before max_rounds=25
        assert _count(conn, "rh_market_states") == 20
    finally:
        conn.close()


# --- 11. decimals: never guess ---------------------------------------------------
def test_read_decimals_none_on_rpc_error():
    def broken(method, params=None, **_kw):
        return None, {"code": -32603, "message": "boom"}, 7
    assert collector.read_decimals(collector.TOKEN0, broken) is None


def test_run_refuses_to_guess_decimals(tmp_path):
    def rpc_fn(method, params=None, **_kw):
        if method == "eth_call" and params[0]["data"] == collector.SEL_DECIMALS:
            if params[0]["to"] == collector.TOKEN1:
                return None, {"code": -32603, "message": "boom"}, 7
            return "0x12", None, 4
        raise AssertionError(f"unexpected {method}")
    rc = collector.run(str(tmp_path / "rh.db"), interval_secs=0,
                       max_rounds=1, pid_file=None, once=True,
                       rpc_fn=rpc_fn)
    assert rc == 3


# --- 12. source guard -------------------------------------------------------------
def test_source_guard_no_untrusted_endpoint_or_heavy_deps():
    src = (Path(__file__).resolve().parents[1] / "scripts"
           / "lp_rh_collector_v1_readonly.py").read_text()
    assert "drpc" not in src
    assert "import requests" not in src
    # "web3" appears once in the module docstring ("no requests/web3/");
    # guard the actual risk: no import or use of the web3 library.
    assert "import web3" not in src
    assert "from web3" not in src
    assert "curl/8.5.0" in src


# --- 13. RH-02i: reference_age_secs is the true data age ---------------------
def _fake_rpc_ts(timestamp_hex, fail_calls=frozenset()):
    """Fake rpc_fn with a controllable block timestamp (hex int) plus call
    counters. No network. fail_calls is a subset of {"slot0", "liquidity",
    "balance"} (same convention as _fake_rpc)."""
    calls = {"n": 0, "block_fetches": 0}

    def rpc_fn(method, params=None, **_kw):
        calls["n"] += 1
        if method == "eth_getBlockByNumber":
            calls["block_fetches"] += 1
            return {"number": BLOCK_HEX, "hash": "0xh",
                    "timestamp": timestamp_hex,
                    "baseFeePerGas": "0x3b9aca00"}, None, 5
        assert method == "eth_call"
        data = params[0]["data"]
        if data == collector.SEL_DECIMALS:
            dec = "0x12" if params[0]["to"] == collector.TOKEN0 else "0x6"
            return dec, None, 4
        kind = ("slot0" if data == collector.SEL_SLOT0
                else "liquidity" if data == collector.SEL_LIQUIDITY
                else "balance")
        if kind in fail_calls:
            return None, {"code": -32603, "message": f"{kind} failed"}, 9
        return SLOT0_HEX if kind == "slot0" else "0x1", None, 4
    rpc_fn.calls = calls
    return rpc_fn


def test_reference_age_differs_across_block_timestamps(tmp_path, monkeypatch):
    # Two rounds whose blocks carry different timestamps must yield
    # different reference_age_secs (guards against the column regressing to
    # a constant). A fixed clock isolates the timestamp as the variable.
    monkeypatch.setattr(collector, "_utc_now", _unique_stamps())
    conn = _open(tmp_path)
    try:
        fixed_now = lambda: 1_000_000.0
        collector.collect_round(conn, dec0=18, dec1=6, last_good_block=None,
                                rpc_fn=_fake_rpc_ts("0x64"), now_fn=fixed_now)
        collector.collect_round(conn, dec0=18, dec1=6, last_good_block=None,
                                rpc_fn=_fake_rpc_ts("0x65"), now_fn=fixed_now)
        ages = [r[0] for r in conn.execute(
            "SELECT reference_age_secs FROM rh_market_states ORDER BY rowid")]
        assert ages[0] != ages[1]
        assert ages == [1_000_000 - 0x64, 1_000_000 - 0x65]
    finally:
        conn.close()


def test_reference_age_none_when_block_timestamp_unavailable(tmp_path):
    # The good_block re-fetch fails -> no timestamp -> age is None (not 0).
    conn = _open(tmp_path)
    try:
        def rpc_fn(method, params=None, **_kw):
            if method == "eth_getBlockByNumber":
                if params[0] == "latest":
                    return {"number": BLOCK_HEX, "hash": "0xh",
                            "timestamp": "0x65",
                            "baseFeePerGas": "0x3b9aca00"}, None, 5
                return None, {"code": -32603, "message": "no such block"}, 12
            data = params[0]["data"]
            if data == collector.SEL_DECIMALS:
                return ("0x12" if params[0]["to"] == collector.TOKEN0
                        else "0x6"), None, 4
            kind = ("slot0" if data == collector.SEL_SLOT0
                    else "liquidity" if data == collector.SEL_LIQUIDITY
                    else "balance")
            return SLOT0_HEX if kind == "slot0" else "0x1", None, 4
        collector.collect_round(conn, dec0=18, dec1=6, last_good_block=None,
                                rpc_fn=rpc_fn)
        mid, age = conn.execute(
            "SELECT reference_mid, reference_age_secs FROM rh_market_states"
        ).fetchone()
        assert mid is not None  # the price was computed
        assert age is None      # not 0, not a fabricated value
    finally:
        conn.close()


def test_reference_age_exact_from_fixed_clock_and_timestamp(tmp_path):
    # Age is exactly now - block_timestamp under a fixed clock + timestamp.
    conn = _open(tmp_path)
    try:
        now_epoch = 2_000_500.75
        ts = 0x100  # 256
        collector.collect_round(conn, dec0=18, dec1=6, last_good_block=None,
                                rpc_fn=_fake_rpc_ts(hex(ts)),
                                now_fn=lambda: now_epoch)
        age = conn.execute(
            "SELECT reference_age_secs FROM rh_market_states").fetchone()[0]
        assert age == int(now_epoch - ts)
        assert age == 2_000_500 - 256
    finally:
        conn.close()


def test_clock_skew_clamps_to_zero_and_flags(tmp_path):
    # A block timestamp in the future (clock skew) clamps age to 0 and adds
    # a CLOCK_SKEW health flag instead of silently hiding the negative age.
    conn = _open(tmp_path)
    try:
        now_epoch = 1_000.0
        ts = 0x500  # 1280 > 1000 -> future
        collector.collect_round(conn, dec0=18, dec1=6, last_good_block=None,
                                rpc_fn=_fake_rpc_ts(hex(ts)),
                                now_fn=lambda: now_epoch)
        age, flags_json = conn.execute(
            "SELECT reference_age_secs, health_flags_json FROM rh_market_states"
        ).fetchone()
        assert age == 0
        assert "CLOCK_SKEW" in flags_json
    finally:
        conn.close()


def test_reference_age_none_when_price_missing(tmp_path):
    # slot0 fails -> no price. Even though the block timestamp is available,
    # the age stays None (no price, no age), preserving the prior behavior.
    conn = _open(tmp_path)
    try:
        collector.collect_round(conn, dec0=18, dec1=6, last_good_block=None,
                                rpc_fn=_fake_rpc_ts("0x65", fail_calls={"slot0"}),
                                now_fn=lambda: 1_000_000.0)
        mid, age = conn.execute(
            "SELECT reference_mid, reference_age_secs FROM rh_market_states"
        ).fetchone()
        assert mid is None
        assert age is None
    finally:
        conn.close()


def test_module_docstring_documents_reference_mid_semantics():
    # Guard against the column-semantics note being deleted from the doc.
    doc = collector.__doc__ or ""
    assert "DEX pool price" in doc
    assert "not an external reference" in doc


def test_session_still_unknown(tmp_path):
    # RH-02i must not change the session="UNKNOWN" behavior (regression).
    conn = _open(tmp_path)
    try:
        collector.collect_round(conn, dec0=18, dec1=6, last_good_block=None,
                                rpc_fn=_fake_rpc_ts("0x65"))
        session = conn.execute(
            "SELECT session FROM rh_market_states").fetchone()[0]
        assert session == "UNKNOWN"
    finally:
        conn.close()


def test_round_makes_at_most_one_extra_rpc_call(tmp_path):
    # Baseline round: 1 block + slot0 + liquidity + 2 balances = 5 calls.
    # RH-02i adds exactly 1 (the good_block timestamp fetch) -> 6 total,
    # i.e. 2 eth_getBlockByNumber calls ("latest" + good_block).
    conn = _open(tmp_path)
    try:
        rpc = _fake_rpc_ts("0x65")
        collector.collect_round(conn, dec0=18, dec1=6, last_good_block=None,
                                rpc_fn=rpc)
        assert rpc.calls["n"] == 6
        assert rpc.calls["block_fetches"] == 2
    finally:
        conn.close()
