"""Tests for RH-02bx2 backfill registry synchronization and drift detection.

Covers detect_registry_attestation_drift, sync_registry_attestation_status,
and plan_backfill registry_drift integration against memory/tmp stores.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest

from scripts import lp_rh_pool_attestation_backfill_v1 as bf
from scripts import lp_rh_registry_v1_readonly as reg
from scripts import lp_rh_store_v1_readonly as store

CORE_POOL = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
WETH = "0x0bd7d308f8e1639fab988df18a8011f41eacad73"
USDG = "0x5fc5360d0400a0fd4f2af552add042d716f1d168"
CHAIN_ID = reg.RH_CHAIN_ID


@pytest.fixture
def memory_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    store.migrate(conn)
    yield conn
    conn.close()


def _insert_pool(
    conn: sqlite3.Connection,
    pool_address: str = CORE_POOL,
    *,
    attestation_status: str = "DISCOVERED_NOT_ATTESTED",
    token0: str = WETH,
    token1: str = USDG,
    chain_id: int = CHAIN_ID,
    protocol: str = "v3",
    pool_key: str | None = None,
    discovered_at: str = "2026-09-09T00:00:00Z",
) -> None:
    conn.execute(
        "INSERT INTO rh_pool_registry ("
        "chain_id, protocol, pool_key, pool_address, pool_id, "
        "token0, token1, fee, tick_spacing, hooks, "
        "attestation_status, discovered_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            chain_id,
            protocol,
            pool_key or pool_address.lower(),
            pool_address.lower(),
            pool_address.lower(),
            token0.lower(),
            token1.lower(),
            "100",
            1,
            None,
            attestation_status,
            discovered_at,
        ),
    )
    conn.commit()


def _insert_attestation(
    conn: sqlite3.Connection,
    address: str = CORE_POOL,
    *,
    attestation_status: str = "ATTESTED_SAME_BLOCK",
    chain_id: int = CHAIN_ID,
    block_hash: str = "0x" + "11" * 32,
    policy_version: str = "v1",
    code_hash: str = "0x" + "22" * 32,
    implementation: str | None = None,
    abi_version: str = "v3",
    evidence_json: str = "{}",
    expires_at: str | None = None,
    created_at: str = "2026-09-10T00:00:00Z",
) -> None:
    conn.execute(
        "INSERT INTO rh_contract_attestations ("
        "chain_id, address, block_hash, policy_version, code_hash, "
        "implementation, abi_version, attestation_status, evidence_json, "
        "expires_at, created_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            chain_id,
            address.lower(),
            block_hash,
            policy_version,
            code_hash,
            implementation,
            abi_version,
            attestation_status,
            evidence_json,
            expires_at,
            created_at,
        ),
    )
    conn.commit()


def test_sync_updates_attested_same_block(memory_conn: sqlite3.Connection) -> None:
    """防回归：attestation 认证成功后，registry 状态必须被正确回写更新为 ATTESTED_SAME_BLOCK。"""
    _insert_pool(memory_conn, pool_address=CORE_POOL, attestation_status="DISCOVERED_NOT_ATTESTED")
    _insert_attestation(memory_conn, address=CORE_POOL, attestation_status="ATTESTED_SAME_BLOCK")

    res = bf.sync_registry_attestation_status(
        memory_conn, records=[{"address": CORE_POOL}], chain_id=CHAIN_ID,
    )

    assert res["updated"] == 1
    assert res["unchanged"] == 0
    assert res["skipped_not_in_registry"] == 0
    assert res["skipped_no_attestation"] == 0
    row = memory_conn.execute(
        "SELECT attestation_status FROM rh_pool_registry WHERE LOWER(pool_address) = LOWER(?)",
        (CORE_POOL,),
    ).fetchone()
    assert row is not None
    assert row[0] == "ATTESTED_SAME_BLOCK"


def test_sync_updates_failed_status(memory_conn: sqlite3.Connection) -> None:
    """防回归：同步职责是对账一致而非单向放行，遇到 FAILED 必须忠实回写为 FAILED，严禁吞没失败。"""
    _insert_pool(memory_conn, pool_address=CORE_POOL, attestation_status="DISCOVERED_NOT_ATTESTED")
    _insert_attestation(memory_conn, address=CORE_POOL, attestation_status="FAILED")

    res = bf.sync_registry_attestation_status(
        memory_conn, records=[{"address": CORE_POOL}], chain_id=CHAIN_ID,
    )

    assert res["updated"] == 1
    assert res["unchanged"] == 0
    row = memory_conn.execute(
        "SELECT attestation_status FROM rh_pool_registry WHERE LOWER(pool_address) = LOWER(?)",
        (CORE_POOL,),
    ).fetchone()
    assert row is not None
    assert row[0] == "FAILED"


def test_sync_picks_latest_created_at(memory_conn: sqlite3.Connection) -> None:
    """防回归：同一地址有多条认证记录时，必须取 created_at DESC 最新行的状态，防止旧结论覆盖新结论。"""
    _insert_pool(memory_conn, pool_address=CORE_POOL, attestation_status="DISCOVERED_NOT_ATTESTED")
    # 旧记录：通过
    _insert_attestation(
        memory_conn,
        address=CORE_POOL,
        block_hash="0x" + "11" * 32,
        attestation_status="ATTESTED_SAME_BLOCK",
        created_at="2026-09-09T10:00:00Z",
    )
    # 新记录：失败
    _insert_attestation(
        memory_conn,
        address=CORE_POOL,
        block_hash="0x" + "22" * 32,
        attestation_status="FAILED",
        created_at="2026-09-10T15:00:00Z",
    )

    res = bf.sync_registry_attestation_status(
        memory_conn, records=[{"address": CORE_POOL}], chain_id=CHAIN_ID,
    )

    assert res["updated"] == 1
    row = memory_conn.execute(
        "SELECT attestation_status FROM rh_pool_registry WHERE LOWER(pool_address) = LOWER(?)",
        (CORE_POOL,),
    ).fetchone()
    assert row is not None
    assert row[0] == "FAILED"


def test_sync_skips_address_not_in_registry_and_no_insert(memory_conn: sqlite3.Connection) -> None:
    """防回归：对于非池合约（如 token0/beacon）的认证记录，当其不在 registry 时跳过计数且严禁 INSERT 新行。"""
    _insert_pool(memory_conn, pool_address=CORE_POOL)
    unregistered_addr = "0x9999999999999999999999999999999999999999"
    _insert_attestation(memory_conn, address=unregistered_addr, attestation_status="ATTESTED_SAME_BLOCK")

    count_before = memory_conn.execute("SELECT COUNT(*) FROM rh_pool_registry").fetchone()[0]
    res = bf.sync_registry_attestation_status(
        memory_conn, records=[{"address": unregistered_addr}], chain_id=CHAIN_ID,
    )

    assert res["skipped_not_in_registry"] >= 1
    assert res["updated"] == 0
    count_after = memory_conn.execute("SELECT COUNT(*) FROM rh_pool_registry").fetchone()[0]
    assert count_before == count_after
    inserted = memory_conn.execute(
        "SELECT 1 FROM rh_pool_registry WHERE LOWER(pool_address) = LOWER(?)",
        (unregistered_addr,),
    ).fetchone()
    assert inserted is None


def test_sync_skips_pool_with_no_attestations(memory_conn: sqlite3.Connection) -> None:
    """防回归：registry 中有池但 attestations 无该池记录时，registry 状态原样不变并计入 skipped_no_attestation。"""
    _insert_pool(memory_conn, pool_address=CORE_POOL, attestation_status="DISCOVERED_NOT_ATTESTED")

    res = bf.sync_registry_attestation_status(
        memory_conn, records=[{"address": CORE_POOL}], chain_id=CHAIN_ID,
    )

    assert res["skipped_no_attestation"] >= 1
    assert res["updated"] == 0
    row = memory_conn.execute(
        "SELECT attestation_status FROM rh_pool_registry WHERE LOWER(pool_address) = LOWER(?)",
        (CORE_POOL,),
    ).fetchone()
    assert row is not None
    assert row[0] == "DISCOVERED_NOT_ATTESTED"


def test_sync_eip55_checksum_case_insensitive(memory_conn: sqlite3.Connection) -> None:
    """防回归：records 传入 EIP-55 混合大小写地址时，仍能正确匹配小写存储的 registry 与 attestation 行并更新。"""
    _insert_pool(memory_conn, pool_address=CORE_POOL.lower(), attestation_status="DISCOVERED_NOT_ATTESTED")
    _insert_attestation(memory_conn, address=CORE_POOL.lower(), attestation_status="ATTESTED_SAME_BLOCK")

    # 构造混合大小写的 EIP-55 地址
    eip55_addr = "0x52E65b17fb6E5bA00ed806f37AfCD2Daa50271Ca"
    assert eip55_addr.lower() == CORE_POOL.lower()

    res = bf.sync_registry_attestation_status(
        memory_conn, records=[{"address": eip55_addr}], chain_id=CHAIN_ID,
    )

    assert res["updated"] == 1
    row = memory_conn.execute(
        "SELECT attestation_status FROM rh_pool_registry WHERE LOWER(pool_address) = LOWER(?)",
        (CORE_POOL.lower(),),
    ).fetchone()
    assert row is not None
    assert row[0] == "ATTESTED_SAME_BLOCK"


def test_detect_registry_attestation_drift(memory_conn: sqlite3.Connection) -> None:
    """防回归：精确比对 registry 与 attestations 状态，一致时 drift_count=0；不一致时返回包含 4 个必要键的完整行。"""
    # 状态一致场景
    _insert_pool(memory_conn, pool_address=CORE_POOL, attestation_status="ATTESTED_SAME_BLOCK")
    _insert_attestation(
        memory_conn,
        address=CORE_POOL,
        attestation_status="ATTESTED_SAME_BLOCK",
        created_at="2026-09-10T02:00:14Z",
    )

    drift_clean = bf.detect_registry_attestation_drift(memory_conn)
    assert drift_clean["drift_count"] == 0
    assert drift_clean["rows"] == []

    # 状态不一致场景：registry 为未认证，attestation 为通过
    memory_conn.execute(
        "UPDATE rh_pool_registry SET attestation_status = 'DISCOVERED_NOT_ATTESTED' WHERE LOWER(pool_address) = LOWER(?)",
        (CORE_POOL,),
    )
    memory_conn.commit()

    drift_dirty = bf.detect_registry_attestation_drift(memory_conn)
    assert drift_dirty["drift_count"] == 1
    assert len(drift_dirty["rows"]) == 1
    drift_row = drift_dirty["rows"][0]
    assert drift_row["pool_address"] == CORE_POOL.lower()
    assert drift_row["registry_status"] == "DISCOVERED_NOT_ATTESTED"
    assert drift_row["attestation_status"] == "ATTESTED_SAME_BLOCK"
    assert drift_row["attestation_created_at"] == "2026-09-10T02:00:14Z"
    for k in ("pool_address", "registry_status", "attestation_status", "attestation_created_at"):
        assert drift_row[k], f"Key {k} must not be empty"

    # 边界情况：池在 registry 中但 attestations 无记录不算 drift
    second_pool = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    _insert_pool(memory_conn, pool_address=second_pool, attestation_status="DISCOVERED_NOT_ATTESTED")
    drift_still_one = bf.detect_registry_attestation_drift(memory_conn)
    assert drift_still_one["drift_count"] == 1


def test_plan_backfill_includes_drift_and_zero_db_writes(
    memory_conn: sqlite3.Connection, tmp_path: Path
) -> None:
    """防回归：plan_backfill 必须包含 registry_drift 键且作为 dry-run 规划绝不对数据库产生任何写入。"""
    _insert_pool(
        memory_conn,
        pool_address=CORE_POOL,
        token0=WETH,
        token1=USDG,
        attestation_status="DISCOVERED_NOT_ATTESTED",
    )
    _insert_attestation(
        memory_conn,
        address=CORE_POOL,
        attestation_status="ATTESTED_SAME_BLOCK",
        created_at="2026-09-10T02:00:14Z",
    )

    before_rows = memory_conn.execute(
        "SELECT pool_address, attestation_status FROM rh_pool_registry ORDER BY pool_address"
    ).fetchall()

    dummy_meta = tmp_path / "dummy_meta.json"
    dummy_meta.write_text("{}", encoding="utf-8")

    plan = bf.plan_backfill(
        memory_conn,
        pool_address=CORE_POOL,
        pool_meta_path=dummy_meta,
        chain_id=CHAIN_ID,
    )

    assert "registry_drift" in plan
    assert plan["registry_drift"]["drift_count"] == 1
    assert plan["network_calls_made"] == 0
    assert plan["db_writes_made"] == 0

    after_rows = memory_conn.execute(
        "SELECT pool_address, attestation_status FROM rh_pool_registry ORDER BY pool_address"
    ).fetchall()
    assert before_rows == after_rows, "plan_backfill 违反零写入安全不变式，修改了数据库状态"

    # 测试传 pool_meta_path=None 的情况，同样保证零写入
    plan_none = bf.plan_backfill(
        memory_conn,
        pool_address=CORE_POOL,
        pool_meta_path=None,
        chain_id=CHAIN_ID,
    )
    assert "registry_drift" in plan_none
    after_rows_none = memory_conn.execute(
        "SELECT pool_address, attestation_status FROM rh_pool_registry ORDER BY pool_address"
    ).fetchall()
    assert before_rows == after_rows_none

