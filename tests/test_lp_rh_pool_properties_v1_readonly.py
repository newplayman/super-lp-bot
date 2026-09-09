"""Paired tests for collect_pool_properties (RH-02v), offline.

scripts/lp_rh_evidence_collector_v1_readonly.py now asks the chain for the
four economic columns of the v3 pool (token0 / token1 / fee / tick_spacing)
and merges them into the registry candidate. In-memory SQLite; injected fake
rpc_fn returning JSON-RPC envelopes (the _call contract); no network.
"""
from __future__ import annotations

import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

import sqlite3

from scripts import lp_rh_store_v1_readonly as store
from scripts import lp_rh_evidence_collector_v1_readonly as col
from scripts import lp_rh_registry_v1_readonly as reg

CHAIN = reg.RH_CHAIN_ID
ADDR_A = "0x" + "aa" * 20
ADDR_B = "0x" + "bb" * 20
POOL = "0x" + "cc" * 20


def _db():
    conn = sqlite3.connect(":memory:")
    store.migrate(conn)
    return conn


def _word(addr):
    """A 32-byte word carrying a 20-byte address in its last 20 bytes."""
    return "0x" + "00" * 12 + addr[2:]


def _props_rpc(results):
    """Fake rpc_fn for eth_call. results: {selector: value | ('error', text)}."""
    def rpc(method, params):
        if method != "eth_call":
            return {"error": {"code": -32601, "message": "unknown method"}}
        data = params[0].get("data", "")
        if data not in results:
            return {"error": {"code": -1, "message": "unknown selector"}}
        item = results[data]
        if isinstance(item, tuple) and item[0] == "error":
            return {"error": {"code": -1, "message": item[1]}}
        return {"result": item}
    return rpc


def _full_results():
    return {
        col.SEL_TOKEN0: _word(ADDR_A),
        col.SEL_TOKEN1: _word(ADDR_B),
        col.SEL_FEE: "0x" + "00" * 31 + "64",
        col.SEL_TICK_SPACING: "0x" + "00" * 31 + "01",
    }


def _empty_fetch(url):
    return col.FetchResult(200, {"assets": []})


def test_all_four_succeed():
    out = col.collect_pool_properties(_props_rpc(_full_results()), POOL)
    assert set(out) == {"token0", "token1", "fee", "tick_spacing"}
    assert out["token0"] == ADDR_A
    assert out["token1"] == ADDR_B
    assert out["token0"].startswith("0x")
    assert len(out["token0"]) == 42
    assert out["token0"] == out["token0"].lower()


def test_fee_and_tick_spacing_are_int():
    out = col.collect_pool_properties(_props_rpc(_full_results()), POOL)
    assert isinstance(out["fee"], int)
    assert isinstance(out["tick_spacing"], int)
    assert not isinstance(out["fee"], str)
    assert not isinstance(out["tick_spacing"], str)


def test_measured_values():
    rpc = _props_rpc({col.SEL_FEE: "0x64", col.SEL_TICK_SPACING: "0x1"})
    out = col.collect_pool_properties(rpc, POOL)
    assert out["fee"] == 100
    assert out["tick_spacing"] == 1


def test_fee_error_omits_key():
    results = _full_results()
    results[col.SEL_FEE] = ("error", "boom")
    out = col.collect_pool_properties(_props_rpc(results), POOL)
    assert "fee" not in out
    assert out.get("fee") is None
    assert "token0" in out and "token1" in out and "tick_spacing" in out


def test_fee_zero_is_present():
    rpc = _props_rpc({col.SEL_FEE: "0x" + "0" * 64})
    out = col.collect_pool_properties(rpc, POOL)
    assert "fee" in out
    assert out["fee"] == 0


def test_token0_error_omits_only_token0():
    results = _full_results()
    results[col.SEL_TOKEN0] = ("error", "boom")
    out = col.collect_pool_properties(_props_rpc(results), POOL)
    assert "token0" not in out
    assert out["token1"] == ADDR_B
    assert out["fee"] == 100
    assert out["tick_spacing"] == 1


def test_bad_result_omits_key():
    rpc = _props_rpc({col.SEL_TOKEN0: "aa" * 32})
    assert "token0" not in col.collect_pool_properties(rpc, POOL)
    rpc = _props_rpc({col.SEL_TOKEN0: "0x" + "ab" * 10})
    assert "token0" not in col.collect_pool_properties(rpc, POOL)
    rpc = _props_rpc({col.SEL_FEE: "0x"})
    assert "fee" not in col.collect_pool_properties(rpc, POOL)


def test_never_contains_pool_id_or_hooks():
    out = col.collect_pool_properties(_props_rpc(_full_results()), POOL)
    assert "pool_id" not in out
    assert "hooks" not in out


def test_all_fail_returns_empty_dict():
    results = {sel: ("error", "e") for sel in
               (col.SEL_TOKEN0, col.SEL_TOKEN1, col.SEL_FEE,
                col.SEL_TICK_SPACING)}
    out = col.collect_pool_properties(_props_rpc(results), POOL)
    assert out == {}
    assert out is not None


def test_address_lowercased():
    rpc = _props_rpc({col.SEL_TOKEN0: "0x" + "00" * 12 + "AA" * 20})
    out = col.collect_pool_properties(rpc, POOL)
    assert out["token0"] == "0x" + "aa" * 20
    assert out["token0"] == out["token0"].lower()


def test_writer_integration_all_columns():
    conn = _db()
    props = col.collect_pool_properties(_props_rpc(_full_results()), POOL)
    col.write_pool_registry(conn, [{"pool": POOL, **props}], chain_id=CHAIN)
    row = conn.execute(
        "select token0, token1, fee, tick_spacing from rh_pool_registry"
    ).fetchone()
    assert row is not None
    assert row[0] == ADDR_A
    assert row[1] == ADDR_B
    assert row[2] is not None and int(row[2]) == 100  # fee is a TEXT column
    assert row[3] == 1


def test_writer_fee_absent_is_null():
    conn = _db()
    results = _full_results()
    results[col.SEL_FEE] = ("error", "boom")
    props = col.collect_pool_properties(_props_rpc(results), POOL)
    assert "fee" not in props
    col.write_pool_registry(conn, [{"pool": POOL, **props}], chain_id=CHAIN)
    row = conn.execute("select fee from rh_pool_registry").fetchone()
    assert row[0] is None


def test_writer_pool_id_hooks_null():
    conn = _db()
    props = col.collect_pool_properties(_props_rpc(_full_results()), POOL)
    col.write_pool_registry(conn, [{"pool": POOL, **props}], chain_id=CHAIN)
    row = conn.execute("select pool_id, hooks from rh_pool_registry").fetchone()
    assert row[0] is None
    assert row[1] is None


def test_run_once_pool_registry_written_still_one():
    conn = _db()
    report = col.run_once(conn, fetch_fn=_empty_fetch,
                          rpc_fn=_props_rpc(_full_results()),
                          chain_id=CHAIN, policy_version="v1")
    assert report["pool_registry"]["written"] == 1
