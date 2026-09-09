"""Paired tests for scripts/lp_rh_evidence_collector_v1_readonly.py (offline).

In-memory SQLite (migrate() builds the schema); injected fake fetch_fn/rpc_fn;
no network, no reports/ writes, no real sleep.
"""
from __future__ import annotations

import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

import os
import sqlite3
import tempfile

from scripts import lp_rh_store_v1_readonly as store
from scripts import lp_rh_evidence_collector_v1_readonly as col
from scripts import lp_rh_registry_v1_readonly as reg

CHAIN = reg.RH_CHAIN_ID
BLOCK_HASH = "0x" + "cd" * 32
CODE = "0x" + "11" * 32
IMPL = "0x" + "22" * 20
ADDR_A = "0x" + "aa" * 20
ADDR_B = "0x" + "bb" * 20


def _db():
    conn = sqlite3.connect(":memory:")
    store.migrate(conn)
    return conn


def _asset(address=ADDR_A, symbol="TOK"):
    return {"tokenAddress": address, "symbol": symbol, "tokenDecimals": 18,
            "tradingCapabilities": {
                "market": {"whole": "TRADING_STATUS_TRADABLE",
                           "fractional": "TRADING_STATUS_TRADABLE"},
                "extended": {"whole": "TRADING_STATUS_NOT_TRADABLE",
                             "fractional": "TRADING_STATUS_NOT_TRADABLE"},
                "overnight": {"whole": "TRADING_STATUS_UNKNOWN",
                              "fractional": "TRADING_STATUS_UNKNOWN"}}}


def _ok_fetch(payload):
    def fetch(url):
        return col.FetchResult(200, payload)
    return fetch


def _assets_payload():
    return {"assets": [_asset(ADDR_A), _asset(ADDR_B, "TOK2")]}


def _rpc_fn(code_by_addr=None, block_hash=BLOCK_HASH, impl=IMPL):
    """Fake rpc_fn. code_by_addr: {addr: code} (missing -> error)."""
    code_by_addr = code_by_addr or {}

    def rpc(method, params):
        if method == "eth_blockNumber":
            return {"result": "0x10"}
        if method == "eth_getBlockByNumber":
            return {"result": {"hash": block_hash}}
        if method == "eth_getCode":
            addr = params[0].lower()
            code = code_by_addr.get(addr)
            if code is None:
                return {"error": {"code": -1, "message": "no code"}}
            return {"result": code}
        if method == "eth_call":
            data = params[0].get("data", "")
            if data == col.SEL_IMPLEMENTATION:
                if impl is None:
                    return {"error": {"code": -1, "message": "no impl"}}
                return {"result": "0x" + "0" * 24 + impl[2:]}
            return {"error": {"code": -1, "message": "unknown selector"}}
        return {"error": {"code": -32601, "message": "unknown method"}}
    return rpc


def test_collector_never_writes_collector_tables():
    conn = _db()
    before = {t: conn.execute(f"select count(*) from {t}").fetchone()[0]
              for t in ("rh_market_states", "rh_rpc_health", "rh_source_snapshots")}
    col.run_once(conn, fetch_fn=_ok_fetch(_assets_payload()),
                 rpc_fn=_rpc_fn(code_by_addr={ADDR_A: CODE, ADDR_B: CODE}),
                 chain_id=CHAIN, policy_version="v1")
    after = {t: conn.execute(f"select count(*) from {t}").fetchone()[0]
             for t in ("rh_market_states", "rh_rpc_health", "rh_source_snapshots")}
    assert before == after


def test_collect_assets_missing_container_key_returns_empty():
    fetch = _ok_fetch({"quotes": [_asset()]})
    assert col.collect_assets(fetch) == []


def test_collect_attestations_no_code_hash_skipped():
    records = col.collect_attestations(
        _rpc_fn(code_by_addr={ADDR_B: CODE}), [ADDR_A, ADDR_B], beacon=col.BEACON)
    addrs = [r["address"] for r in records]
    assert ADDR_A not in addrs
    assert ADDR_B in addrs


def test_collect_attestations_no_block_hash_skipped():
    def rpc(method, params):
        if method == "eth_blockNumber":
            return {"error": {"code": -1, "message": "no block"}}
        return {"result": "0x"}
    records = col.collect_attestations(rpc, [ADDR_A], beacon=col.BEACON)
    assert records == []


def test_run_once_assets_failure_does_not_stop_others():
    conn = _db()

    def bad_fetch(url):
        raise RuntimeError("REST down")
    report = col.run_once(conn, fetch_fn=bad_fetch,
                          rpc_fn=_rpc_fn(code_by_addr={ADDR_A: CODE}),
                          chain_id=CHAIN, policy_version="v1")
    assert any("collect_assets" in e for e in report["errors"])
    assert report["pool_registry"]["written"] == 1
    assert "written" in report["attestations"]


def test_run_once_returns_three_subresults():
    conn = _db()
    report = col.run_once(conn, fetch_fn=_ok_fetch(_assets_payload()),
                          rpc_fn=_rpc_fn(code_by_addr={ADDR_A: CODE, ADDR_B: CODE}),
                          chain_id=CHAIN, policy_version="v1")
    for key in ("assets", "pool_registry", "attestations"):
        for field in ("written", "skipped", "missing_fields"):
            assert field in report[key], (key, field)


def test_dry_run_no_db_write():
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "scanner.db")
        conn = store.open_store(db)
        store.migrate(conn)
        before = {t: conn.execute(f"select count(*) from {t}").fetchone()[0]
                  for t in ("rh_assets", "rh_pool_registry", "rh_contract_attestations")}
        conn.close()
        rc = col.main(["--db", db, "--dry-run"],
                      fetch_fn=_ok_fetch(_assets_payload()), rpc_fn=_rpc_fn())
        conn = store.open_store(db)
        after = {t: conn.execute(f"select count(*) from {t}").fetchone()[0]
                 for t in ("rh_assets", "rh_pool_registry", "rh_contract_attestations")}
        conn.close()
        assert rc == 0
        assert before == after


def test_once_writes_to_db():
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "scanner.db")
        conn = store.open_store(db)
        store.migrate(conn)
        conn.close()
        rc = col.main(["--db", db, "--once"],
                      fetch_fn=_ok_fetch(_assets_payload()),
                      rpc_fn=_rpc_fn(code_by_addr={ADDR_A: CODE, ADDR_B: CODE}))
        conn = store.open_store(db)
        assets = conn.execute("select count(*) from rh_assets").fetchone()[0]
        pools = conn.execute("select count(*) from rh_pool_registry").fetchone()[0]
        attests = conn.execute("select count(*) from rh_contract_attestations").fetchone()[0]
        conn.close()
        assert rc == 0
        assert assets == 2
        assert pools == 1
        assert attests == 2


def test_run_once_wrong_chain_id_skips_all():
    conn = _db()
    report = col.run_once(conn, fetch_fn=_ok_fetch(_assets_payload()),
                          rpc_fn=_rpc_fn(code_by_addr={ADDR_A: CODE, ADDR_B: CODE}),
                          chain_id=8453, policy_version="v1")
    assert report["assets"]["written"] == 0
    assert report["pool_registry"]["written"] == 0
    assert report["attestations"]["written"] == 0
    assert conn.execute("select count(*) from rh_assets").fetchone()[0] == 0
    assert conn.execute("select count(*) from rh_pool_registry").fetchone()[0] == 0
    assert conn.execute("select count(*) from rh_contract_attestations").fetchone()[0] == 0


def test_attestations_impl_unobtainable_is_none():
    conn = _db()
    col.run_once(conn, fetch_fn=_ok_fetch(_assets_payload()),
                 rpc_fn=_rpc_fn(code_by_addr={ADDR_A: CODE}, impl=None),
                 chain_id=CHAIN, policy_version="v1")
    row = conn.execute("select implementation from rh_contract_attestations").fetchone()
    assert row is not None
    assert row[0] is None


def test_run_once_empty_assets_no_raise():
    conn = _db()
    report = col.run_once(conn, fetch_fn=_ok_fetch({"assets": []}),
                          rpc_fn=_rpc_fn(), chain_id=CHAIN, policy_version="v1")
    assert report["assets"]["written"] == 0
    assert report["errors"] == []


def test_collect_assets_429_backoff():
    calls = {"n": 0}
    sleeps = []

    def fetch(url):
        calls["n"] += 1
        if calls["n"] <= 2:
            return col.FetchResult(429, None)
        return col.FetchResult(200, _assets_payload())

    def sleep_fn(secs):
        sleeps.append(secs)
    records = col.collect_assets(fetch, sleep_fn=sleep_fn)
    assert len(records) == 2
    assert sleeps == [5, 15]
    assert calls["n"] == 3


def test_run_loop_deadline_from_round_start():
    sleeps = []
    state = {"t": 0.0}

    def fake_clock():
        return state["t"]

    def fake_sleep(secs):
        sleeps.append(secs)
        state["t"] += secs

    def fake_run_once():
        state["t"] += 100.0

    def fake_stop():
        return len(sleeps) >= 1
    col.run_loop(fake_run_once, period_secs=300, clock=fake_clock,
                 sleep_fn=fake_sleep, stop_check=fake_stop, tick=1000.0)
    assert sleeps == [200.0]


def test_run_once_idempotent():
    conn = _db()
    for _ in range(2):
        col.run_once(conn, fetch_fn=_ok_fetch(_assets_payload()),
                     rpc_fn=_rpc_fn(code_by_addr={ADDR_A: CODE, ADDR_B: CODE}),
                     chain_id=CHAIN, policy_version="v1")
    assert conn.execute("select count(*) from rh_assets").fetchone()[0] == 2
    assert conn.execute("select count(*) from rh_pool_registry").fetchone()[0] == 1
    assert conn.execute("select count(*) from rh_contract_attestations").fetchone()[0] == 2
