from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import lp_rh_reorg_detector_v1_readonly as detector
from scripts import lp_rh_store_v1_readonly as store


def _create_test_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    store.migrate(conn)
    return conn


def _insert_sample(
    conn: sqlite3.Connection,
    sample_time: str,
    block_number: int | None,
    block_hash: str | None,
    asset_address: str = "0xPOOL",
) -> None:
    store.insert_row(
        conn,
        "rh_market_states",
        {
            "asset_address": asset_address,
            "sample_time": sample_time,
            "chain_id": 1,
            "session": "UNKNOWN",
            "health_flags_json": "[]",
            "reference_mid": "100.5",
            "derived_block_number": block_number,
            "derived_block_hash": block_hash,
        },
    )
    # insert_row does not commit, and sqlite3 rolls back an open transaction on
    # close() without a word -- the rows vanish and the detector reads an empty
    # table. Six of these tests were asserting against zero rows for that reason.
    conn.commit()


def test_reorg_detected_multiple_hashes_same_block_number(tmp_path: Path):
    """1. 造 3 个样本，同 block_number=100，两个不同 hash -> 检出 1 组分歧，

    报告里列出两个 hash 及各自的观测次数。
    """
    db_file = tmp_path / "test.db"
    conn = _create_test_db(db_file)
    _insert_sample(conn, "2026-09-11T10:00:00Z", 100, "0xhashA")
    _insert_sample(conn, "2026-09-11T10:01:00Z", 100, "0xhashA")
    _insert_sample(conn, "2026-09-11T10:02:00Z", 100, "0xhashB")
    conn.close()

    out_file = tmp_path / "report.md"
    exit_code = detector.main(["--db", str(db_file), "--out", str(out_file)])
    assert exit_code == 1

    content = out_file.read_text(encoding="utf-8")
    assert "发现 1 组分歧" in content
    assert "0xhashA" in content
    assert "2次" in content or "2" in content
    assert "0xhashB" in content
    assert "1次" in content or "1" in content


def test_no_reorg_unique_hashes_says_not_found(tmp_path: Path):
    """2. 全部 block_number 各自唯一 hash -> 检出 0 组，退出码 0，

    报告里出现「未发现分歧」而不是「通过」字样。
    """
    db_file = tmp_path / "test.db"
    conn = _create_test_db(db_file)
    _insert_sample(conn, "2026-09-11T10:00:00Z", 100, "0xhash100")
    _insert_sample(conn, "2026-09-11T10:01:00Z", 101, "0xhash101")
    _insert_sample(conn, "2026-09-11T10:02:00Z", 102, "0xhash102")
    conn.close()

    out_file = tmp_path / "report.md"
    exit_code = detector.main(["--db", str(db_file), "--out", str(out_file)])
    assert exit_code == 0

    content = out_file.read_text(encoding="utf-8")
    assert "未发现分歧" in content
    assert "通过" not in content


def test_data_corruption_same_hash_multiple_numbers(tmp_path: Path):
    """3. 同一 hash 对应两个 block_number -> 归入数据损坏一节，不计入 reorg 分歧。"""
    db_file = tmp_path / "test.db"
    conn = _create_test_db(db_file)
    _insert_sample(conn, "2026-09-11T10:00:00Z", 100, "0xsamehash")
    _insert_sample(conn, "2026-09-11T10:01:00Z", 101, "0xsamehash")
    conn.close()

    out_file = tmp_path / "report.md"
    exit_code = detector.main(["--db", str(db_file), "--out", str(out_file)])
    assert exit_code == 0

    content = out_file.read_text(encoding="utf-8")
    assert "未发现分歧" in content
    assert "数据损坏检查" in content
    assert "发现数据损坏" in content
    assert "0xsamehash" in content
    assert "Block 100" in content
    assert "Block 101" in content


def test_null_rows_skipped_not_divergence(tmp_path: Path):
    """4. derived_block_number 或 derived_block_hash 为 NULL 的行被跳过，

    不计入任何一类（不要当成分歧）。
    """
    db_file = tmp_path / "test.db"
    conn = _create_test_db(db_file)
    _insert_sample(conn, "2026-09-11T10:00:00Z", None, None)
    _insert_sample(conn, "2026-09-11T10:01:00Z", 100, None)
    _insert_sample(conn, "2026-09-11T10:02:00Z", None, "0xsomehash")
    _insert_sample(conn, "2026-09-11T10:03:00Z", 100, "0xvalidhash")
    conn.close()

    out_file = tmp_path / "report.md"
    exit_code = detector.main(["--db", str(db_file), "--out", str(out_file)])
    assert exit_code == 0

    content = out_file.read_text(encoding="utf-8")
    assert "未发现分歧" in content
    assert "未发现数据损坏" in content
    assert "跳过 NULL 样本行数: `3`" in content
    assert "有效样本行数: `1`" in content


def test_without_record_db_table_not_created(tmp_path: Path):
    """5. 不给 --record-db -> rh_reorg_contested 表不被创建。"""
    db_file = tmp_path / "test.db"
    conn = _create_test_db(db_file)
    _insert_sample(conn, "2026-09-11T10:00:00Z", 100, "0xhashA")
    _insert_sample(conn, "2026-09-11T10:01:00Z", 100, "0xhashB")
    conn.close()

    exit_code = detector.main(["--db", str(db_file)])
    assert exit_code == 1

    check_conn = sqlite3.connect(str(db_file))
    tbls = [
        r[0]
        for r in check_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='rh_reorg_contested'"
        ).fetchall()
    ]
    check_conn.close()
    assert tbls == []


def test_with_record_db_records_divergence(tmp_path: Path):
    """6. 给了 --record-db -> 表被创建且分歧被写入，条数与检出组数一致。"""
    source_db = tmp_path / "source.db"
    record_db = tmp_path / "record.db"

    conn = _create_test_db(source_db)
    _insert_sample(conn, "2026-09-11T10:00:00Z", 100, "0xhashA")
    _insert_sample(conn, "2026-09-11T10:01:00Z", 100, "0xhashB")
    conn.close()

    exit_code = detector.main([
        "--db", str(source_db),
        "--record-db", str(record_db),
    ])
    assert exit_code == 1

    rec_conn = sqlite3.connect(str(record_db))
    rows = rec_conn.execute(
        "SELECT block_number, hash_a, hash_b, status FROM rh_reorg_contested"
    ).fetchall()
    rec_conn.close()

    assert len(rows) == 1
    bn, ha, hb, status = rows[0]
    assert bn == 100
    assert {ha, hb} == {"0xhashA", "0xhashB"}
    assert status == "CONTESTED"


def test_record_db_idempotent(tmp_path: Path):
    """7. 重复跑 --record-db 幂等（record_contested 用的是 INSERT OR IGNORE，第二次不新增行）。"""
    source_db = tmp_path / "source.db"
    record_db = tmp_path / "record.db"

    conn = _create_test_db(source_db)
    _insert_sample(conn, "2026-09-11T10:00:00Z", 100, "0xhashA")
    _insert_sample(conn, "2026-09-11T10:01:00Z", 100, "0xhashB")
    conn.close()

    # First run
    code1 = detector.main([
        "--db", str(source_db),
        "--record-db", str(record_db),
    ])
    assert code1 == 1

    # Second run
    code2 = detector.main([
        "--db", str(source_db),
        "--record-db", str(record_db),
    ])
    assert code2 == 1

    rec_conn = sqlite3.connect(str(record_db))
    cnt = rec_conn.execute("SELECT COUNT(*) FROM rh_reorg_contested").fetchone()[0]
    rec_conn.close()
    assert cnt == 1
