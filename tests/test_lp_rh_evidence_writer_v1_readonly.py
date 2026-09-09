"""Paired tests for scripts/lp_rh_evidence_writer_v1_readonly.py (offline only).

In-memory SQLite (migrate() builds the schema); no network, no reports/ writes.
"""
from __future__ import annotations

import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

import json
import sqlite3

import pytest

from scripts import lp_rh_store_v1_readonly as store
from scripts import lp_rh_evidence_writer_v1_readonly as writer
from scripts import lp_rh_registry_v1_readonly as reg

WETH = "0x0Bd7D308f8E1639FAb988df18A8011f41EAcAD73"
USDG = "0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168"
POOL = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
POOL_ID = "0x" + "ab" * 32
BLOCK_HASH = "0x" + "cd" * 32
CHAIN = reg.RH_CHAIN_ID


def _db():
    conn = sqlite3.connect(":memory:")
    store.migrate(conn)
    return conn


def _asset(address=WETH, symbol="WETH", decimals=18):
    return {"tokenAddress": address, "symbol": symbol, "tokenDecimals": decimals,
            "tradingCapabilities": {
                "market": {"whole": "TRADING_STATUS_TRADABLE",
                           "fractional": "TRADING_STATUS_TRADABLE"},
                "extended": {"whole": "TRADING_STATUS_NOT_TRADABLE",
                             "fractional": "TRADING_STATUS_NOT_TRADABLE"},
                "overnight": {"whole": "TRADING_STATUS_UNKNOWN",
                              "fractional": "TRADING_STATUS_UNKNOWN"}}}


def _v3_candidate():
    return {"pool": POOL, "factory": "0x1f7d7550b1b028f7571e69a784071f0205fd2efa"}


def _v4_candidate():
    return {"pool_id": POOL_ID,
            "pool_manager": "0x73991a25c818bf1f1128deaab1492d45638de0d3",
            "currency0": WETH, "currency1": USDG, "fee": 10000,
            "tick_spacing": 60, "hooks": "0x" + "0" * 64}


def _probe_record(address=POOL, status="ATTESTED_SAME_BLOCK"):
    return {"address": address, "block_hash": BLOCK_HASH,
            "attestation_status": status, "code_hash": "0x" + "11" * 32}


def _table_counts(conn):
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'rh_%'"
    ).fetchall()]
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in tables}


# --- write_assets -----------------------------------------------------------
def test_assets_row_count_and_pk():
    conn = _db()
    res = writer.write_assets(conn, [_asset(WETH), _asset(USDG, "USDG", 6)],
                              chain_id=CHAIN, metadata_version=1, source="s")
    assert res["written"] == 2 and res["skipped"] == 0
    rows = conn.execute(
        "SELECT chain_id, address, metadata_version FROM rh_assets ORDER BY address"
    ).fetchall()
    assert rows == [(4663, WETH.lower(), 1), (4663, USDG.lower(), 1)]


def test_assets_idempotent():
    conn = _db()
    writer.write_assets(conn, [_asset(WETH)], chain_id=CHAIN,
                        metadata_version=1, source="s")
    writer.write_assets(conn, [_asset(WETH)], chain_id=CHAIN,
                        metadata_version=1, source="s")
    assert conn.execute("SELECT COUNT(*) FROM rh_assets").fetchone()[0] == 1


def test_assets_missing_fields_nonempty():
    conn = _db()
    res = writer.write_assets(conn, [_asset(WETH)], chain_id=CHAIN,
                              metadata_version=1, source="s")
    assert res["missing_fields"], "expected gaps to be surfaced"
    # multiplier_raw / status / source_payload_hash are not produced by the
    # registry module, so each must be counted.
    for col in ("multiplier_raw", "status", "source_payload_hash"):
        assert res["missing_fields"].get(col, 0) >= 1, col


def test_assets_null_fields_in_db():
    conn = _db()
    writer.write_assets(conn, [_asset(WETH)], chain_id=CHAIN,
                        metadata_version=1, source="s")
    row = conn.execute(
        "SELECT multiplier_raw, status, source_payload_hash FROM rh_assets"
    ).fetchone()
    assert row == (None, None, None)


def test_assets_capability_json_valid():
    conn = _db()
    writer.write_assets(conn, [_asset(WETH)], chain_id=CHAIN,
                        metadata_version=1, source="s")
    cap = json.loads(conn.execute(
        "SELECT capability_json FROM rh_assets").fetchone()[0])
    assert cap["market"] == "TRADABLE"
    assert cap["extended"] == "NOT_TRADABLE"
    assert cap["overnight"] == "UNKNOWN"


def test_assets_chain_id_gate_skips():
    conn = _db()
    res = writer.write_assets(conn, [_asset(WETH)], chain_id=1,
                              metadata_version=1, source="s")
    assert res["written"] == 0 and res["skipped"] == 1
    assert conn.execute("SELECT COUNT(*) FROM rh_assets").fetchone()[0] == 0


def test_assets_written_skipped_counts():
    conn = _db()
    # One valid asset, one with an invalid address (asset_from_json raises).
    res = writer.write_assets(
        conn, [_asset(WETH), _asset("0x1234", "BAD", 18)],
        chain_id=CHAIN, metadata_version=1, source="s")
    assert res["written"] == 1 and res["skipped"] == 1


def test_assets_empty_input():
    conn = _db()
    res = writer.write_assets(conn, [], chain_id=CHAIN,
                              metadata_version=1, source="s")
    assert res["written"] == 0 and res["skipped"] == 0
    assert conn.execute("SELECT COUNT(*) FROM rh_assets").fetchone()[0] == 0


# --- write_pool_registry ------------------------------------------------------
# The first eight tests in this file all exercise write_assets; these cover the
# other two writers, which had no coverage at all.

def test_pool_registry_protocol_comes_from_dispatch_not_a_literal():
    """A 20-byte pool is v3, a 32-byte pool_id is v4, decided by dispatch_protocol."""
    conn = _db()
    writer.write_pool_registry(conn, [{"pool": POOL}, {"pool_id": POOL_ID}],
                            chain_id=4663)
    got = sorted(r[0] for r in conn.execute(
        "select protocol from rh_pool_registry"))
    assert got == ["v3", "v4"]


def test_pool_registry_never_attests():
    """This writer records discovery only; attesting is another module's job."""
    conn = _db()
    writer.write_pool_registry(conn, [{"pool": POOL}], chain_id=4663)
    status = conn.execute(
        "select attestation_status from rh_pool_registry").fetchone()[0]
    assert status == "DISCOVERED_NOT_ATTESTED"
    assert "ATTESTED" != status


def test_pool_registry_skips_candidates_dispatch_cannot_place():
    """Both pool and pool_id, or neither, is UNSUPPORTED_PROTOCOL and skipped."""
    conn = _db()
    res = writer.write_pool_registry(
        conn, [{"pool": POOL, "pool_id": POOL_ID}, {}], chain_id=4663)
    assert res["written"] == 0
    assert res["skipped"] == 2
    assert conn.execute("select count(*) from rh_pool_registry").fetchone()[0] == 0


def test_pool_registry_is_idempotent_on_its_primary_key():
    conn = _db()
    for _ in range(2):
        writer.write_pool_registry(conn, [{"pool": POOL}], chain_id=4663)
    assert conn.execute("select count(*) from rh_pool_registry").fetchone()[0] == 1


def test_pool_registry_identity_gate_cannot_be_bypassed_at_write_time():
    conn = _db()
    res = writer.write_pool_registry(conn, [{"pool": POOL}], chain_id=8453)
    assert res["written"] == 0 and res["skipped"] == 1
    assert conn.execute("select count(*) from rh_pool_registry").fetchone()[0] == 0


# --- write_attestations -------------------------------------------------------

def _attest(**over):
    rec = {"address": "0xAbC", "block_hash": BLOCK_HASH,
           "attestation_status": "ATTESTED_SAME_BLOCK", "code_hash": "0xcc"}
    rec.update(over)
    return rec


def test_attestations_written_and_address_lowercased():
    conn = _db()
    res = writer.write_attestations(conn, [_attest()], chain_id=4663,
                                 policy_version="v1")
    assert res["written"] == 1
    addr = conn.execute("select address from rh_contract_attestations").fetchone()[0]
    assert addr == addr.lower()


def test_attestations_raise_naming_the_missing_required_column():
    """A required column is never written as an empty string."""
    conn = _db()
    for col in ("address", "block_hash", "attestation_status"):
        with pytest.raises(ValueError) as exc:
            writer.write_attestations(conn, [_attest(**{col: None})],
                                   chain_id=4663, policy_version="v1")
        assert col in str(exc.value)


def test_attestations_are_idempotent_on_their_primary_key():
    conn = _db()
    for _ in range(2):
        writer.write_attestations(conn, [_attest()], chain_id=4663,
                               policy_version="v1")
    assert conn.execute(
        "select count(*) from rh_contract_attestations").fetchone()[0] == 1


def test_attestations_identity_gate_cannot_be_bypassed_at_write_time():
    conn = _db()
    res = writer.write_attestations(conn, [_attest()], chain_id=8453,
                                 policy_version="v1")
    assert res["written"] == 0 and res["skipped"] == 1


def test_no_writer_touches_an_unrelated_table():
    conn = _db()
    before = {t: conn.execute(f"select count(*) from {t}").fetchone()[0]
              for t in ("rh_market_states", "rh_rpc_health", "rh_gate_decisions")}
    writer.write_pool_registry(conn, [{"pool": POOL}], chain_id=4663)
    writer.write_attestations(conn, [_attest()], chain_id=4663, policy_version="v1")
    after = {t: conn.execute(f"select count(*) from {t}").fetchone()[0]
             for t in ("rh_market_states", "rh_rpc_health", "rh_gate_decisions")}
    assert before == after
