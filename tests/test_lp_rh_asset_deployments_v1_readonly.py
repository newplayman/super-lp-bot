"""Paired tests for the RH-02m deployments[] address fallback (offline only).

Locks the RH-02m defect: real /rhj/assets records carry the token address in
``deployments[].contractAddress`` (filtered by ``chainId``), not in a top-level
key. In-memory SQLite (migrate() builds the schema); no network.
"""
from __future__ import annotations

import copy
import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

import sqlite3

import pytest

from scripts import lp_rh_store_v1_readonly as store
from scripts import lp_rh_evidence_writer_v1_readonly as writer
from scripts import lp_rh_evidence_collector_v1_readonly as collector
from scripts import lp_rh_registry_v1_readonly as reg

CHAIN = 4663
CRM = "0xd95B44124e475743a7589e68F3D74008A5536D44"
CRM_LOW = CRM.lower()

# Real /rhj/assets record shape (verbatim from the 2026-09-09 capture). The
# address lives in deployments[], not at the top level.
REAL_SHAPE = {
    "tokenSymbol": "CRM",
    "status": "ASSET_STATUS_ACTIVE",
    "tokenDecimals": 18,
    "isin": "...",
    "currentMultiplier": "...",
    "pendingMultiplier": "...",
    "tradingCapabilities": {
        "market": {"whole": "TRADING_STATUS_TRADABLE",
                   "fractional": "TRADING_STATUS_TRADABLE"},
        "extended": {"whole": "TRADING_STATUS_NOT_TRADABLE",
                     "fractional": "TRADING_STATUS_NOT_TRADABLE"},
        "overnight": {"whole": "TRADING_STATUS_UNKNOWN",
                      "fractional": "TRADING_STATUS_UNKNOWN"},
    },
    "deployments": [
        {"contractAddress": CRM, "chainId": 4663,
         "networkName": "Robinhood Chain"},
    ],
}


def _db():
    conn = sqlite3.connect(":memory:")
    store.migrate(conn)
    return conn


def _rec(**over):
    """A deep copy of REAL_SHAPE with top-level keys overridden (safe)."""
    rec = copy.deepcopy(REAL_SHAPE)
    rec.update(over)
    return rec


# --- asset_from_json: deployments[] fallback -------------------------------
def test_real_shape_asset_from_json():
    ident = reg.asset_from_json(CHAIN, REAL_SHAPE, "1", "s")
    assert ident.address == CRM_LOW


def test_top_level_address_takes_priority_over_deployments():
    top = "0x" + "aa" * 20
    rec = _rec(tokenAddress=top)  # deployments still holds CRM
    ident = reg.asset_from_json(CHAIN, rec, "1", "s")
    assert ident.address == top.lower()
    assert ident.address != CRM_LOW


def test_top_level_backward_compat_still_works():
    top = "0x" + "bb" * 20
    ident = reg.asset_from_json(CHAIN, {"tokenAddress": top, "symbol": "WETH"},
                                "1", "s")
    assert ident.address == top.lower()


def test_deployments_only_other_chain_raises():
    rec = _rec(deployments=[{"contractAddress": "0x" + "cc" * 20,
                             "chainId": 9999, "networkName": "X"}])
    with pytest.raises(ValueError, match="ASSET_ADDRESS_INVALID"):
        reg.asset_from_json(CHAIN, rec, "1", "s")


def test_deployments_empty_list_raises():
    with pytest.raises(ValueError, match="ASSET_ADDRESS_INVALID"):
        reg.asset_from_json(CHAIN, _rec(deployments=[]), "1", "s")


def test_deployments_missing_raises():
    rec = {k: v for k, v in REAL_SHAPE.items() if k != "deployments"}
    with pytest.raises(ValueError, match="ASSET_ADDRESS_INVALID"):
        reg.asset_from_json(CHAIN, rec, "1", "s")


def test_deployments_not_a_list_raises():
    rec = _rec(deployments={"contractAddress": "0x" + "dd" * 20,
                            "chainId": 4663})
    with pytest.raises(ValueError, match="ASSET_ADDRESS_INVALID"):
        reg.asset_from_json(CHAIN, rec, "1", "s")


def test_deployments_element_not_dict_raises():
    with pytest.raises(ValueError, match="ASSET_ADDRESS_INVALID"):
        reg.asset_from_json(CHAIN, _rec(deployments=["not-a-dict"]), "1", "s")


def test_deployments_multiple_takes_matching_not_first():
    first = "0x" + "11" * 20
    match = "0x" + "22" * 20
    rec = _rec(deployments=[
        {"contractAddress": first, "chainId": 9999, "networkName": "X"},
        {"contractAddress": match, "chainId": 4663,
         "networkName": "Robinhood Chain"},
    ])
    ident = reg.asset_from_json(CHAIN, rec, "1", "s")
    assert ident.address == match.lower()
    assert ident.address != first.lower()


def test_deployments_contract_address_not_40hex_raises():
    rec = _rec(deployments=[{"contractAddress": "0x1234", "chainId": 4663,
                             "networkName": "X"}])
    with pytest.raises(ValueError, match="ASSET_ADDRESS_INVALID"):
        reg.asset_from_json(CHAIN, rec, "1", "s")


# --- _asset_addresses: deployments[] fallback ------------------------------
def test_asset_addresses_real_shape_one_lower():
    assert collector._asset_addresses([REAL_SHAPE], chain_id=CHAIN) == [CRM_LOW]


def test_asset_addresses_dedup_order_preserving():
    other = ("0x" + "ee" * 20).lower()
    recs = [copy.deepcopy(REAL_SHAPE), copy.deepcopy(REAL_SHAPE),
            {"tokenAddress": "0x" + "ee" * 20}]
    assert collector._asset_addresses(recs, chain_id=CHAIN) == [CRM_LOW, other]


def test_asset_addresses_chain_mismatch_empty():
    assert collector._asset_addresses([REAL_SHAPE], chain_id=9999) == []


# --- write_assets: skip_reasons + existing keys ----------------------------
def test_write_assets_real_shape_all_written():
    res = writer.write_assets(_db(), [REAL_SHAPE] * 3, chain_id=CHAIN,
                              metadata_version=1, source="s")
    assert res["written"] == 3
    assert res["skipped"] == 0


def test_write_assets_skip_reasons_all_fail():
    bad = [_rec(deployments=[]) for _ in range(3)]
    res = writer.write_assets(_db(), bad, chain_id=CHAIN,
                              metadata_version=1, source="s")
    assert res["written"] == 0
    assert res["skipped"] == 3
    assert res["skip_reasons"] == {"ASSET_ADDRESS_INVALID": 3}


def test_write_assets_skip_reasons_all_success_empty():
    res = writer.write_assets(_db(), [REAL_SHAPE] * 3, chain_id=CHAIN,
                              metadata_version=1, source="s")
    assert res["skip_reasons"] == {}
    assert res["skip_reasons"] is not None


def test_write_assets_existing_keys_types_unchanged():
    res = writer.write_assets(_db(), [REAL_SHAPE], chain_id=CHAIN,
                              metadata_version=1, source="s")
    assert isinstance(res["written"], int)
    assert isinstance(res["skipped"], int)
    assert isinstance(res["missing_fields"], dict)
    assert set(res) >= {"written", "skipped", "missing_fields", "skip_reasons"}
