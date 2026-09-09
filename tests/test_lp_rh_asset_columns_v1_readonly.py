"""Paired tests for the RH-02n six empty rh_assets columns (offline only).

Locks the RH-02n defect: after RH-02m filled rh_assets to 194 rows, six
columns were still NULL because the writer read the wrong field names and
hard-coded three of them to None. In-memory SQLite (migrate() builds the
schema); no network.
"""
from __future__ import annotations

import copy
import re
import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

import sqlite3
from decimal import Decimal

from scripts import lp_rh_store_v1_readonly as store
from scripts import lp_rh_evidence_writer_v1_readonly as writer
from scripts import lp_rh_registry_v1_readonly as reg

CHAIN = 4663
MULT = "1.002210914971013375"

# Real /rhj/assets record shape (verbatim field names from the 2026-09-09
# capture). The address lives in deployments[] (RH-02m shape).
REAL = {
    "tokenSymbol": "CRM",
    "id": "0x000000000000000000000000000000000000000000000000000000000000000022015c295294037bfe416d3e45327b9",
    "isin": "US79466L3024",
    "status": "ASSET_STATUS_ACTIVE",
    "currentMultiplier": MULT,
    "pendingMultiplier": "",
    "tokenDecimals": 18,
    "tradingCapabilities": {
        "market": {"whole": "TRADING_STATUS_TRADABLE",
                   "fractional": "TRADING_STATUS_TRADABLE"},
        "extended": {"whole": "TRADING_STATUS_NOT_TRADABLE",
                     "fractional": "TRADING_STATUS_NOT_TRADABLE"},
        "overnight": {"whole": "TRADING_STATUS_UNKNOWN",
                      "fractional": "TRADING_STATUS_UNKNOWN"},
    },
    "deployments": [
        {"contractAddress": "0xd95B44124e475743a7589e68F3D74008A5536D44",
         "chainId": 4663, "networkName": "Robinhood Chain"},
    ],
}


def _db():
    conn = sqlite3.connect(":memory:")
    store.migrate(conn)
    return conn


def _rec(**over):
    """A deep copy of REAL with top-level keys overridden (safe)."""
    rec = copy.deepcopy(REAL)
    rec.update(over)
    return rec


def _row(conn):
    """The single rh_assets row as a dict (REAL writes exactly one row)."""
    cur = conn.execute("SELECT * FROM rh_assets")
    cols = [c[0] for c in cur.description]
    (vals,) = cur.fetchall()
    return dict(zip(cols, vals))


def _write_real_from(payload):
    conn = _db()
    writer.write_assets(conn, [payload], chain_id=CHAIN,
                        metadata_version=1, source="s")
    return conn


def _write_hash(payload):
    """Write one payload into a fresh DB and return its stored hash."""
    conn = _db()
    writer.write_assets(conn, [payload], chain_id=CHAIN,
                        metadata_version=1, source="s")
    return conn.execute(
        "SELECT source_payload_hash FROM rh_assets").fetchone()[0]


# --- asset_from_json: measured-key fallback -------------------------------
def test_real_shape_symbol_uid_underlying():
    ident = reg.asset_from_json(CHAIN, REAL, "1", "s")
    assert ident.symbol_display == "CRM"
    assert ident.uid == REAL["id"]
    assert ident.underlying == "US79466L3024"


def test_backward_compat_top_level_symbol_wins():
    rec = _rec(symbol="OLD_SYM")  # tokenSymbol still "CRM"
    assert reg.asset_from_json(CHAIN, rec, "1", "s").symbol_display == "OLD_SYM"


def test_backward_compat_top_level_uid_wins():
    rec = _rec(uid="OLD_UID")  # id still REAL["id"]
    assert reg.asset_from_json(CHAIN, rec, "1", "s").uid == "OLD_UID"


def test_backward_compat_top_level_underlying_wins():
    rec = _rec(underlying="OLD_ISIN")  # isin still US79466L3024
    assert reg.asset_from_json(CHAIN, rec, "1", "s").underlying == "OLD_ISIN"


# --- write_assets: multiplier_raw (never via float) -----------------------
def test_multiplier_raw_read_back_exact_string():
    row = _row(_write_real_from(REAL))
    assert row["multiplier_raw"] == MULT
    assert row["multiplier_raw"] == "1.002210914971013375"
    assert Decimal(row["multiplier_raw"]) == Decimal(MULT)


def test_multiplier_raw_is_str_type():
    row = _row(_write_real_from(REAL))
    assert isinstance(row["multiplier_raw"], str)


def test_multiplier_raw_empty_string_is_none():
    row = _row(_write_real_from(_rec(currentMultiplier="")))
    assert row["multiplier_raw"] is None


def test_multiplier_raw_missing_is_none():
    rec = copy.deepcopy(REAL)
    del rec["currentMultiplier"]
    row = _row(_write_real_from(rec))
    assert row["multiplier_raw"] is None


# --- write_assets: status -------------------------------------------------
def test_status_written_active():
    row = _row(_write_real_from(REAL))
    assert row["status"] == "ASSET_STATUS_ACTIVE"


def test_status_empty_string_is_none():
    row = _row(_write_real_from(_rec(status="")))
    assert row["status"] is None


# --- write_assets: source_payload_hash ------------------------------------
def test_source_payload_hash_is_64_hex():
    row = _row(_write_real_from(REAL))
    assert re.fullmatch(r"[0-9a-f]{64}", row["source_payload_hash"])


def test_source_payload_hash_reproducible():
    assert _write_hash(REAL) == _write_hash(copy.deepcopy(REAL))


def test_source_payload_hash_differs_for_different_payload():
    assert _write_hash(REAL) != _write_hash(_rec(status="ASSET_STATUS_INACTIVE"))


def test_source_payload_hash_key_order_invariant():
    reordered = {k: copy.deepcopy(REAL[k]) for k in reversed(list(REAL.keys()))}
    assert _write_hash(REAL) == _write_hash(reordered)


# --- write_assets: counts + six columns + no regression --------------------
def test_write_assets_three_written():
    res = writer.write_assets(_db(), [REAL] * 3, chain_id=CHAIN,
                              metadata_version=1, source="s")
    assert res["written"] == 3
    assert res["skipped"] == 0
    assert res["skip_reasons"] == {}


def test_six_columns_all_non_none():
    row = _row(_write_real_from(REAL))
    for col in ("symbol_display", "uid", "underlying", "multiplier_raw",
                "status", "source_payload_hash"):
        assert row[col] is not None, col


def test_decimals_and_capability_preserved():
    row = _row(_write_real_from(REAL))
    assert row["decimals"] == 18
    assert row["capability_json"]
