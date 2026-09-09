"""Tests for scripts/lp_rh_pool_attestation_backfill_v1.py (RH-02bc)."""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest

from scripts import lp_rh_evidence_collector_v1_readonly as col
from scripts import lp_rh_pool_attestation_backfill_v1 as bf
from scripts import lp_rh_registry_v1_readonly as reg
from scripts import lp_rh_store_v1_readonly as store

CORE_POOL = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
WETH = "0x0bd7d308f8e1639fab988df18a8011f41eacad73"
USDG = "0x5fc5360d0400a0fd4f2af552add042d716f1d168"
FAKE_BLOCK_HASH = "0x" + "aa" * 32
FAKE_CODE = "0x" + "11" * 32
FAKE_IMPL = "0x" + "22" * 20


def _fake_rpc(code_by_addr=None, block_hash=FAKE_BLOCK_HASH, impl=FAKE_IMPL):
    code_by_addr = code_by_addr or {}

    def rpc(method, params):
        if method == "eth_blockNumber":
            return {"result": "0x123456"}
        if method == "eth_getBlockByNumber":
            return {"result": {"hash": block_hash}}
        if method == "eth_getCode":
            addr = params[0].lower()
            code = code_by_addr.get(addr, FAKE_CODE)
            return {"result": code}
        if method == "eth_call":
            data = params[0].get("data", "")
            if data == col.SEL_IMPLEMENTATION:
                return {"result": "0x" + "0" * 24 + impl[2:]}
            if data == col.SEL_TOKEN0:
                return {"result": "0x" + "0" * 24 + WETH[2:]}
            if data == col.SEL_TOKEN1:
                return {"result": "0x" + "0" * 24 + USDG[2:]}
            return {"error": {"code": -1, "message": f"unknown selector {data}"}}
        return {"error": {"code": -32601, "message": f"unknown method {method}"}}
    return rpc


def _exploding_rpc(method, params):
    raise AssertionError(f"NETWORK_CALL_FORBIDDEN_IN_DRY_RUN: {method}({params})")


def _init_db_with_pool(db_path: str, *, token0: str = WETH, token1: str = USDG):
    conn = store.open_store(db_path)
    store.migrate(conn)
    conn.execute(
        "INSERT INTO rh_pool_registry (chain_id, protocol, pool_key, pool_address, token0, token1, fee, tick_spacing, attestation_status, discovered_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (reg.RH_CHAIN_ID, "v3", CORE_POOL, CORE_POOL, token0, token1, "100", 1, "DISCOVERED_NOT_ATTESTED", "2026-09-09T00:00:00Z"),
    )
    conn.commit()
    conn.close()


def test_dry_run_does_not_write_to_db_and_makes_no_network_calls():
    with tempfile.TemporaryDirectory() as tmpdir:
        db = str(Path(tmpdir) / "scanner.db")
        _init_db_with_pool(db)
        conn = store.open_store(db)
        before_count = conn.execute("SELECT COUNT(*) FROM rh_contract_attestations").fetchone()[0]
        conn.close()

        rc = bf.main(["--db", db, "--dry-run"], rpc_fn=_exploding_rpc)
        assert rc == 0

        conn = store.open_store(db)
        after_count = conn.execute("SELECT COUNT(*) FROM rh_contract_attestations").fetchone()[0]
        conn.close()
        assert before_count == after_count == 0


def test_default_flag_is_dry_run():
    with tempfile.TemporaryDirectory() as tmpdir:
        db = str(Path(tmpdir) / "scanner.db")
        _init_db_with_pool(db)
        rc = bf.main(["--db", db], rpc_fn=_exploding_rpc)
        assert rc == 0
        conn = store.open_store(db)
        assert conn.execute("SELECT COUNT(*) FROM rh_contract_attestations").fetchone()[0] == 0
        conn.close()


def test_missing_token0_token1_raises_error():
    conn = sqlite3.connect(":memory:")
    store.migrate(conn)

    # Empty DB and no pool_meta -> raises error
    with pytest.raises(ValueError, match="MISSING_OR_INVALID_TOKEN0"):
        bf.resolve_target_addresses(conn, pool_address=CORE_POOL, allow_network=False)

    # Pool present but token0 is NULL
    conn.execute(
        "INSERT INTO rh_pool_registry (chain_id, protocol, pool_key, pool_address, token0, token1, fee, tick_spacing, attestation_status, discovered_at) "
        "VALUES (?, ?, ?, ?, NULL, ?, '100', 1, 'DISCOVERED_NOT_ATTESTED', '2026-09-09T00:00:00Z')",
        (reg.RH_CHAIN_ID, "v3", CORE_POOL, CORE_POOL, USDG),
    )
    with pytest.raises(ValueError, match="MISSING_OR_INVALID_TOKEN0"):
        bf.resolve_target_addresses(conn, pool_address=CORE_POOL, allow_network=False)

    # Pool present with valid token0 but token1 is empty string
    conn.execute("DELETE FROM rh_pool_registry")
    conn.execute(
        "INSERT INTO rh_pool_registry (chain_id, protocol, pool_key, pool_address, token0, token1, fee, tick_spacing, attestation_status, discovered_at) "
        "VALUES (?, ?, ?, ?, ?, '', '100', 1, 'DISCOVERED_NOT_ATTESTED', '2026-09-09T00:00:00Z')",
        (reg.RH_CHAIN_ID, "v3", CORE_POOL, CORE_POOL, WETH),
    )
    with pytest.raises(ValueError, match="MISSING_OR_INVALID_TOKEN1"):
        bf.resolve_target_addresses(conn, pool_address=CORE_POOL, allow_network=False)

    conn.close()


def test_real_db_and_pool_meta_resolution():
    """Verify that resolution works on the real scanner.db and reports/lp_rh/pool_meta.json."""
    if not bf.DEFAULT_DB_PATH.exists():
        pytest.skip("scanner.db does not exist")

    conn = store.open_store(bf.DEFAULT_DB_PATH, read_only=True)
    try:
        res = bf.resolve_target_addresses(conn, pool_meta_path=bf.DEFAULT_POOL_META_PATH, allow_network=False)
        assert res["pool"]["address"].lower() == CORE_POOL.lower()
        assert res["token0"]["address"].lower() == WETH.lower()
        assert res["token1"]["address"].lower() == USDG.lower()
        assert res["pool"]["source"] == "rh_pool_registry"
        assert res["token0"]["source"] == "rh_pool_registry"
        assert res["token1"]["source"] == "rh_pool_registry"

        plan = bf.plan_backfill(conn, pool_meta_path=bf.DEFAULT_POOL_META_PATH)
        assert plan["mode"] == "dry-run"
        assert plan["status"] == "PLAN_READY"
        assert len(plan["target_addresses"]) == 3
        assert plan["expected_writes"]["rh_contract_attestations"] == 3
        assert plan["estimated_rpc_calls"]["total"] == 6
        assert plan["network_calls_made"] == 0
        assert plan["db_writes_made"] == 0
    finally:
        conn.close()


def test_apply_writes_same_block_attestations_and_is_idempotent():
    with tempfile.TemporaryDirectory() as tmpdir:
        db = str(Path(tmpdir) / "scanner.db")
        _init_db_with_pool(db)

        # Run with --apply using fake RPC
        rc = bf.main(["--db", db, "--apply"], rpc_fn=_fake_rpc())
        assert rc == 0

        conn = store.open_store(db)
        rows = conn.execute(
            "SELECT address, block_hash, attestation_status, code_hash FROM rh_contract_attestations"
        ).fetchall()
        assert len(rows) == 3

        # All 3 records must share the exact same block hash
        block_hashes = {r[1] for r in rows}
        assert len(block_hashes) == 1
        assert list(block_hashes)[0] == FAKE_BLOCK_HASH

        # All 3 records must have attestation_status == ATTESTED_SAME_BLOCK
        statuses = {r[2] for r in rows}
        assert statuses == {"ATTESTED_SAME_BLOCK"}

        # Target addresses must match pool, token0, token1
        addresses = {r[0].lower() for r in rows}
        assert addresses == {CORE_POOL.lower(), WETH.lower(), USDG.lower()}
        conn.close()

        # Idempotency check: running again with the same block hash must not duplicate rows
        rc2 = bf.main(["--db", db, "--apply"], rpc_fn=_fake_rpc())
        assert rc2 == 0
        conn = store.open_store(db)
        count_after = conn.execute("SELECT COUNT(*) FROM rh_contract_attestations").fetchone()[0]
        assert count_after == 3
        conn.close()


def test_fallback_to_pool_meta(tmp_path):
    conn = sqlite3.connect(":memory:")
    store.migrate(conn)
    # Register pool without token0/token1
    conn.execute(
        "INSERT INTO rh_pool_registry (chain_id, protocol, pool_key, pool_address, fee, tick_spacing, attestation_status, discovered_at) "
        "VALUES (?, ?, ?, ?, '100', 1, 'DISCOVERED_NOT_ATTESTED', '2026-09-09T00:00:00Z')",
        (reg.RH_CHAIN_ID, "v3", CORE_POOL, CORE_POOL),
    )

    meta_file = tmp_path / "custom_pool_meta.json"
    meta_file.write_text(json.dumps({"token0": WETH, "token1": USDG}), encoding="utf-8")

    res = bf.resolve_target_addresses(conn, pool_meta_path=meta_file, allow_network=False)
    assert res["token0"]["address"] == WETH.lower()
    assert res["token0"]["source"] == f"pool_meta:{meta_file.name}"
    assert res["token1"]["address"] == USDG.lower()
    assert res["token1"]["source"] == f"pool_meta:{meta_file.name}"
    conn.close()

