"""RH-02t: skip_reasons side-channel for collect_attestations.

A transient eth_getCode failure used to be indistinguishable from "the chain
has no contract" -- both collapsed into collect_skipped. These tests pin the
new skip_out side-channel: RPC_ERROR:<text[:80]> vs NO_CODE vs
CODE_NOT_STRING vs BLOCK_HASH_UNAVAILABLE:<text[:80]>, and that run_once
surfaces it as attestations.skip_reasons without touching collect_skipped.
Pure offline: fake rpc_fn, in-memory sqlite. No network.
"""
from __future__ import annotations

import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

import sqlite3

from scripts import lp_rh_store_v1_readonly as store
from scripts import lp_rh_evidence_collector_v1_readonly as col
from scripts import lp_rh_registry_v1_readonly as reg

CHAIN = reg.RH_CHAIN_ID
BLOCK_HASH = "0x" + "cd" * 32
CODE = "0x" + "11" * 32
IMPL = "0x" + "22" * 20
ADDR_A = "0x" + "aa" * 20
ADDR_B = "0x" + "bb" * 20
ADDR_C = "0x" + "cc" * 20


def _db():
    conn = sqlite3.connect(":memory:")
    store.migrate(conn)
    return conn


def _asset(address, symbol="TOK"):
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


def _rpc(spec, *, block_ok=True, impl=IMPL):
    """Fake rpc_fn. spec: {addr_lower: value} where value is:
    - a str -> the eth_getCode result (CODE, "0x", "", ...)
    - ("err", text) -> JSON-RPC error envelope with that message
    - any other non-tuple object -> returned as result as-is (bad type)
    Missing addr -> generic error envelope."""
    def rpc(method, params):
        if method == "eth_blockNumber":
            if not block_ok:
                return {"error": {"code": -1, "message": "no block"}}
            return {"result": "0x10"}
        if method == "eth_getBlockByNumber":
            if not block_ok:
                return {"error": {"code": -1, "message": "no block"}}
            return {"result": {"hash": BLOCK_HASH}}
        if method == "eth_getCode":
            value = spec.get(params[0].lower())
            if value is None:
                return {"error": {"code": -32000, "message": "no code"}}
            if isinstance(value, tuple) and value and value[0] == "err":
                return {"error": {"code": -32000, "message": value[1]}}
            return {"result": value}
        if method == "eth_call":
            if impl is None:
                return {"error": {"code": -1, "message": "no impl"}}
            return {"result": "0x" + "0" * 24 + impl[2:]}
        return {"error": {"code": -32601, "message": "unknown method"}}
    return rpc


def test_rpc_error_reason_and_address_not_in_records():
    """WULF repro: transient eth_getCode error -> RPC_ERROR:<...>, no record."""
    skip = {}
    records = col.collect_attestations(
        _rpc({ADDR_A: ("err", "upstream timeout")}), [ADDR_A],
        beacon=col.BEACON, skip_out=skip)
    assert records == []
    assert ADDR_A in skip
    assert skip[ADDR_A].startswith("RPC_ERROR:")


def test_no_code_reason_is_no_code():
    skip = {}
    records = col.collect_attestations(
        _rpc({ADDR_A: "0x"}), [ADDR_A], beacon=col.BEACON, skip_out=skip)
    assert records == []
    assert skip[ADDR_A] == "NO_CODE"


def test_no_code_and_rpc_error_are_distinct():
    skip = {}
    col.collect_attestations(
        _rpc({ADDR_A: ("err", "boom"), ADDR_B: "0x"}), [ADDR_A, ADDR_B],
        beacon=col.BEACON, skip_out=skip)
    assert skip[ADDR_A].startswith("RPC_ERROR:")
    assert skip[ADDR_B] == "NO_CODE"
    assert skip[ADDR_A] != skip[ADDR_B]


def test_code_not_string_reason():
    skip = {}
    records = col.collect_attestations(
        _rpc({ADDR_A: 123}), [ADDR_A], beacon=col.BEACON, skip_out=skip)
    assert records == []
    assert skip[ADDR_A] == "CODE_NOT_STRING"


def test_block_hash_unavailable_marks_every_address():
    skip = {}
    records = col.collect_attestations(
        _rpc({ADDR_A: CODE, ADDR_B: CODE, ADDR_C: CODE}, block_ok=False),
        [ADDR_A, ADDR_B, ADDR_C], beacon=col.BEACON, skip_out=skip)
    assert records == []
    for addr in (ADDR_A, ADDR_B, ADDR_C):
        assert addr in skip
        assert skip[addr].startswith("BLOCK_HASH_UNAVAILABLE:")


def test_normal_address_not_in_skip_out():
    skip = {}
    records = col.collect_attestations(
        _rpc({ADDR_A: CODE, ADDR_B: CODE}), [ADDR_A, ADDR_B],
        beacon=col.BEACON, skip_out=skip)
    assert [r["address"] for r in records] == [ADDR_A, ADDR_B]
    assert skip == {}


def test_middle_failure_does_not_stop_others():
    skip = {}
    records = col.collect_attestations(
        _rpc({ADDR_A: CODE, ADDR_B: ("err", "boom"), ADDR_C: CODE}),
        [ADDR_A, ADDR_B, ADDR_C], beacon=col.BEACON, skip_out=skip)
    assert [r["address"] for r in records] == [ADDR_A, ADDR_C]
    assert list(skip) == [ADDR_B]
    assert skip[ADDR_B].startswith("RPC_ERROR:")


def test_err_text_truncated_to_80_chars():
    skip = {}
    col.collect_attestations(
        _rpc({ADDR_A: ("err", "x" * 200)}), [ADDR_A],
        beacon=col.BEACON, skip_out=skip)
    reason = skip[ADDR_A]
    assert reason.startswith("RPC_ERROR:")
    assert len(reason) - len("RPC_ERROR:") <= 80


def test_without_skip_out_behavior_unchanged():
    spec = {ADDR_A: CODE, ADDR_B: ("err", "boom")}
    try:
        records = col.collect_attestations(
            _rpc(spec), [ADDR_A, ADDR_B], beacon=col.BEACON)
    except Exception:
        raise AssertionError("must not raise without skip_out")
    assert [r["address"] for r in records] == [ADDR_A]


def test_skip_out_preserves_existing_keys():
    skip = {"0xpreexisting": "KEEP_ME"}
    col.collect_attestations(
        _rpc({ADDR_A: ("err", "boom")}), [ADDR_A],
        beacon=col.BEACON, skip_out=skip)
    assert skip["0xpreexisting"] == "KEEP_ME"
    assert skip[ADDR_A].startswith("RPC_ERROR:")


def test_records_identical_with_and_without_skip_out():
    spec = {ADDR_A: CODE, ADDR_B: CODE, ADDR_C: ("err", "boom")}
    without = col.collect_attestations(
        _rpc(spec), [ADDR_A, ADDR_B, ADDR_C], beacon=col.BEACON)
    skip = {}
    with_ = col.collect_attestations(
        _rpc(spec), [ADDR_A, ADDR_B, ADDR_C], beacon=col.BEACON, skip_out=skip)
    assert with_ == without
    for r_with, r_without in zip(with_, without):
        for key in r_without:
            assert r_with[key] == r_without[key]


def _run_once(spec, payload=None):
    conn = _db()
    if payload is None:
        payload = {"assets": [_asset(ADDR_A), _asset(ADDR_B)]}
    return col.run_once(conn, fetch_fn=_ok_fetch(payload), rpc_fn=_rpc(spec),
                        chain_id=CHAIN, policy_version="v1")


def test_run_once_report_has_skip_reasons():
    report = _run_once({ADDR_A: CODE, ADDR_B: ("err", "boom")})
    assert "skip_reasons" in report["attestations"]
    assert report["attestations"]["skip_reasons"][ADDR_B].startswith(
        "RPC_ERROR:")


def test_run_once_collect_skipped_still_int():
    report = _run_once({ADDR_A: CODE, ADDR_B: ("err", "boom")})
    assert isinstance(report["attestations"]["collect_skipped"], int)
    assert report["attestations"]["collect_skipped"] == 1


def test_run_once_collect_skipped_equals_len_skip_reasons():
    report = _run_once({ADDR_A: ("err", "a"), ADDR_B: ("err", "b")})
    att = report["attestations"]
    assert att["collect_skipped"] == len(att["skip_reasons"]) == 2


def test_run_once_all_normal_skip_reasons_empty_dict():
    report = _run_once({ADDR_A: CODE, ADDR_B: CODE})
    assert report["attestations"]["skip_reasons"] == {}
    assert isinstance(report["attestations"]["skip_reasons"], dict)
