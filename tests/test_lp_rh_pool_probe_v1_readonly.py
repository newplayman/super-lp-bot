"""Paired tests for scripts/lp_rh_pool_probe_v1_readonly.py (offline only).

Driven by injected fake ``rpc`` callables and the synthetic fixtures under
tests/fixtures/rh/synthetic/; no network access. Covers T06 (attestation
expiry on implementation change), T07 (factory getPool mismatch withholds
economic fields), T08 (protocol dispatch), T09 (non-zero hooks rejected),
T10 (a PoolManager balance is never TVL) and T12 (RPC error text preserved,
never a 0).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import lp_rh_pool_probe_v1_readonly as probe

FIXTURES = Path(__file__).parent / "fixtures" / "rh" / "synthetic"
POOL = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
FACTORY = "0x1f7d7550b1b028f7571e69a784071f0205fd2efa"
POOL_MANAGER = "0x" + "cd" * 20
POOL_ID = "0x" + "ab" * 32


def _cand():
    return {"pool": POOL, "factory": FACTORY}


def _fixture_rpc(name):
    with open(FIXTURES / name, "r", encoding="utf-8") as handle:
        return probe._fixture_rpc(json.load(handle))


# --- T08: protocol dispatch -----------------------------------------------------
def test_dispatch_protocol_v4_v3_and_unsupported():
    assert probe.dispatch_protocol({"pool_id": "0x" + "ab" * 32}) == "v4"
    assert probe.dispatch_protocol({"pool": "0x" + "ab" * 20}) == "v3"
    assert probe.dispatch_protocol(
        {"pool_id": "0x" + "ab" * 32, "pool": "0x" + "ab" * 20}) == "UNSUPPORTED_PROTOCOL"
    assert probe.dispatch_protocol({}) == "UNSUPPORTED_PROTOCOL"


# --- T07: factory getPool mismatch withholds economic fields ---------------------
def test_v3_identity_fail_withholds_economic_fields():
    out = probe.probe_v3_pool(_cand(), _fixture_rpc("v3_pool_identity_fail.json"))
    assert out["attestation_status"] == "IDENTITY_FAIL"
    assert out["factory_get_pool_matches"] is False
    assert out["code_nonempty"] is True
    # economic fields are withheld on identity failure
    assert out["token0"] is None
    assert out["token1"] is None
    assert out["fee"] is None
    assert out["tick_spacing"] is None
    # no economic/TVL fields may appear in the result at all
    for key in ("netcover", "fee_ev", "tvl", "balance"):
        assert key not in out


# --- empty code stops the probe ----------------------------------------------------
def test_v3_empty_code_does_not_continue():
    out = probe.probe_v3_pool(_cand(), _fixture_rpc("v3_pool_code_empty.json"))
    assert out["attestation_status"] == "DISCOVERED_NOT_ATTESTED"
    assert out["code_nonempty"] is False
    assert out["error"] == "POOL_CODE_EMPTY"
    assert out["token0"] is None
    assert out["factory_get_pool_matches"] is None


# --- T12: RPC error keeps the original text, never a 0 ------------------------------
def test_v3_rpc_error_kept_original_text():
    out = probe.probe_v3_pool(_cand(), _fixture_rpc("v3_pool_rpc_error.json"))
    assert out["attestation_status"] == "DISCOVERED_NOT_ATTESTED"
    assert out["error"] is not None
    assert "boom getCode read failed" in out["error"]
    assert out["block_number"] is None


# --- T09: non-zero hooks rejected ----------------------------------------------------
def test_v4_nonzero_hooks_unsupported_policy():
    cand = {"pool_id": POOL_ID, "pool_manager": POOL_MANAGER,
            "currency0": "0x" + "11" * 20, "currency1": "0x" + "22" * 20,
            "tick_spacing": 60, "hooks": "0x" + "ee" * 20}
    out = probe.probe_v4_pool(cand, lambda method, params: {})
    assert out["attestation_status"] == "UNSUPPORTED_HOOK_POLICY"
    assert out["pool_id_computed"] is None


# --- T10: a PoolManager balance is never TVL -------------------------------------------
def test_v4_state_view_equal_to_pool_manager_rejected():
    cand = {"pool_id": POOL_ID, "pool_manager": POOL_MANAGER,
            "currency0": "0x" + "11" * 20, "currency1": "0x" + "22" * 20,
            "tick_spacing": 60}
    with pytest.raises(ValueError):
        probe.probe_v4_pool(cand, lambda method, params: {}, state_view=POOL_MANAGER)
    out = probe.probe_v4_pool(cand, lambda method, params: {}, state_view=None)
    assert out["tvl_source"] is None
    out2 = probe.probe_v4_pool(cand, lambda method, params: {},
                               state_view="0x" + "11" * 20)
    assert out2["tvl_source"] == "STATE_VIEW"


# --- T06: attestation expiry on implementation change -----------------------------------
def test_attestation_expired_on_code_hash_change():
    record = {"code_hash": "aaa"}
    res = probe.attestation_expired(record, "bbb")
    assert res["expired"] is True
    assert res["security_event"] == "IMPLEMENTATION_CHANGED"
    assert probe.attestation_expired(record, "aaa") == {
        "expired": False, "security_event": None}
    assert probe.attestation_expired(record, None) == {
        "expired": False, "security_event": None}
    assert probe.attestation_expired({"no_hash": 1}, "bbb") == {
        "expired": False, "security_event": None}


# --- success path ------------------------------------------------------------------------
def test_v3_success_path_attested_same_block():
    out = probe.probe_v3_pool(_cand(), _fixture_rpc("v3_pool_probe_ok.json"))
    assert out["attestation_status"] == "ATTESTED_SAME_BLOCK"
    assert out["error"] is None
    assert out["code_nonempty"] is True
    assert out["factory_get_pool_matches"] is True
    assert out["token0"] == "0x5fc5360d0400a0fd4f2af552add042d716f1d168"
    assert out["token1"] == "0x0bd7d308f8e1639fab988df18a8011f41eacad73"
    assert out["fee"] == 500
    assert out["tick_spacing"] == 60
    assert out["block_number"] == 0x1234
    assert out["block_hash"] == "0xpoolblockhash"
    assert out["code_hash"] is not None
