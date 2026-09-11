from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import pytest

from scripts import lp_rh_bucket_ledger_v1_readonly as ledger
from scripts import lp_rh_reservation_cleanup_v1 as cleanup
from scripts import lp_rh_store_v1_readonly as store

NOW = "2026-09-10T12:00:00Z"
NOW_DT = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)
POLICY_ID = ledger.POLICY_ID


@pytest.fixture
def test_db(tmp_path):
    db_path = tmp_path / "test_scanner.db"
    conn = store.open_store(db_path)
    store.migrate(conn)
    conn.close()
    return db_path


def _add_res(db_path, intent_id, amount="1000", created_at=NOW, status="PENDING", released_at=None):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO rh_bucket_reservations (intent_id, policy_version, bucket, amount_usd, status, created_at, released_at) "
        "VALUES (?, ?, 'CORE', ?, ?, ?, ?)",
        (intent_id, POLICY_ID, amount, status, created_at, released_at),
    )
    conn.commit()
    conn.close()


def _add_pos(db_path, episode, closed_at=None, opened_at=NOW):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO rh_shadow_positions (strategy_episode, position_id, pool_key, profile, bucket, opened_at, closed_at) "
        "VALUES (?, ?, '0xpool', 'CORE', 'CORE', ?, ?)",
        (episode, f"rh-shadow-{episode}", opened_at, closed_at),
    )
    conn.commit()
    conn.close()


def test_1_dry_run_does_not_modify_database(test_db):
    for i in range(3):
        _add_res(test_db, f"rh-shadow-orphan-{i}-0", created_at="2026-09-10T08:00:00Z")
    c_before = sqlite3.connect(test_db).execute(
        "SELECT COUNT(*) FROM rh_bucket_reservations WHERE released_at IS NULL"
    ).fetchone()[0]
    assert c_before == 3

    res = cleanup.run_cleanup(test_db, apply=False, now_dt=NOW_DT)
    assert res["scan"]["orphan_count"] == 3

    c_after = sqlite3.connect(test_db).execute(
        "SELECT COUNT(*) FROM rh_bucket_reservations WHERE released_at IS NULL"
    ).fetchone()[0]
    assert c_after == c_before

    pending_rows = sqlite3.connect(test_db).execute(
        "SELECT status, released_at FROM rh_bucket_reservations"
    ).fetchall()
    assert len(pending_rows) == 3
    assert all(r[0] == "PENDING" and r[1] is None for r in pending_rows)


def test_2_apply_releases_with_reason_and_rows_remain(test_db, monkeypatch):
    calls = []
    orig_release = cleanup.release

    def spy_release(conn, intent_id, *, now, reason):
        calls.append((intent_id, now, reason))
        return orig_release(conn, intent_id, now=now, reason=reason)

    monkeypatch.setattr(cleanup, "release", spy_release)

    for i in range(3):
        _add_res(test_db, f"rh-shadow-orphan-{i}-0", created_at="2026-09-10T08:00:00Z")

    res = cleanup.run_cleanup(test_db, apply=True, now_dt=NOW_DT)
    assert res["released"] == 3
    assert len(calls) == 3
    assert all(c[2] == "ORPHANED_PRE_CAP_FIX" for c in calls)

    rows = sqlite3.connect(test_db).execute(
        "SELECT intent_id, status, released_at FROM rh_bucket_reservations"
    ).fetchall()
    assert len(rows) == 3
    assert all(r[1] == "RELEASED" and r[2] is not None for r in rows)


def test_3_reservation_with_active_position_is_not_orphan(test_db):
    _add_res(test_db, "rh-shadow-active_ep-0", created_at="2026-09-10T11:00:00Z")
    _add_pos(test_db, "active_ep", closed_at=None)

    res = cleanup.run_cleanup(test_db, apply=False, now_dt=NOW_DT)
    assert res["scan"]["orphan_count"] == 0
    assert res["scan"]["total_pending_count"] == 1

    res_apply = cleanup.run_cleanup(test_db, apply=True, now_dt=NOW_DT)
    assert res_apply["released"] == 0

    row = sqlite3.connect(test_db).execute(
        "SELECT status, released_at FROM rh_bucket_reservations WHERE intent_id = 'rh-shadow-active_ep-0'"
    ).fetchone()
    assert row[0] == "PENDING" and row[1] is None


def test_4_semantic_criterion_precedes_time_criterion(test_db):
    _add_res(test_db, "rh-shadow-old_active-0", created_at="2026-09-09T00:00:00Z")
    _add_pos(test_db, "old_active", closed_at=None)

    res = cleanup.run_cleanup(test_db, older_than_hours=1.0, apply=False, now_dt=NOW_DT)
    assert res["scan"]["time_count"] == 1
    assert res["scan"]["semantic_count"] == 0
    assert res["scan"]["orphan_count"] == 0

    res_apply = cleanup.run_cleanup(test_db, older_than_hours=1.0, apply=True, now_dt=NOW_DT)
    assert res_apply["released"] == 0
    row = sqlite3.connect(test_db).execute(
        "SELECT status, released_at FROM rh_bucket_reservations WHERE intent_id = 'rh-shadow-old_active-0'"
    ).fetchone()
    assert row[0] == "PENDING" and row[1] is None


def test_5_idempotent_multiple_apply_runs(test_db):
    for i in range(3):
        _add_res(test_db, f"rh-shadow-idempotent-{i}-0", created_at="2026-09-10T08:00:00Z")

    res1 = cleanup.run_cleanup(test_db, apply=True, now_dt=NOW_DT)
    assert res1["released"] == 3
    assert res1["scan"]["orphan_count"] == 3

    before_run2 = sqlite3.connect(test_db).execute(
        "SELECT intent_id, status, released_at FROM rh_bucket_reservations ORDER BY intent_id"
    ).fetchall()

    res2 = cleanup.run_cleanup(test_db, apply=True, now_dt=NOW_DT)
    assert res2["released"] == 0
    assert res2["scan"]["orphan_count"] == 0
    assert res2["scan"]["total_pending_count"] == 0

    after_run2 = sqlite3.connect(test_db).execute(
        "SELECT intent_id, status, released_at FROM rh_bucket_reservations ORDER BY intent_id"
    ).fetchall()
    assert before_run2 == after_run2


def test_6_reserved_total_decreases_and_room_becomes_positive(test_db):
    capital = Decimal("10000")
    cap = ledger.bucket_active_cap(capital, "CORE")
    assert cap == Decimal("4250.0")

    # 5 * 1000 = 5000 USD > 4250 USD cap (room = -750 USD)
    for i in range(5):
        _add_res(test_db, f"rh-shadow-deadlock-{i}-0", amount="1000", created_at="2026-09-10T08:00:00Z")

    conn = sqlite3.connect(test_db)
    init_reserved = ledger.reserved_total(conn, "CORE", POLICY_ID)
    init_room = cap - init_reserved
    conn.close()

    assert init_reserved == Decimal("5000")
    assert init_room == Decimal("-750.0")
    assert init_room < 0

    res = cleanup.run_cleanup(test_db, capital_usd=capital, apply=True, now_dt=NOW_DT)
    assert res["released"] == 5

    post_reserved = res["post_reserved"]
    post_room = res["post_room"]

    # Mathematical assertions
    released_sum = Decimal("5000")
    assert post_reserved == init_reserved - released_sum
    assert post_reserved == Decimal("0")
    assert post_room == cap - post_reserved
    assert post_room == Decimal("4250.0")
    assert post_room > 0


def test_7_release_failure_continues_batch(test_db, monkeypatch):
    for i in range(3):
        _add_res(test_db, f"rh-shadow-fault-{i}-0", created_at="2026-09-10T08:00:00Z")

    orig_release = cleanup.release

    def mock_release(conn, intent_id, *, now, reason):
        if intent_id == "rh-shadow-fault-1-0":
            return False  # Simulate intent not found
        return orig_release(conn, intent_id, now=now, reason=reason)

    monkeypatch.setattr(cleanup, "release", mock_release)

    res = cleanup.run_cleanup(test_db, apply=True, now_dt=NOW_DT)
    assert res["released"] == 2
    assert res["failed"] == 1

    # Remaining two should be released
    rows = dict(sqlite3.connect(test_db).execute(
        "SELECT intent_id, status FROM rh_bucket_reservations"
    ).fetchall())
    assert rows["rh-shadow-fault-0-0"] == "RELEASED"
    assert rows["rh-shadow-fault-1-0"] == "PENDING"
    assert rows["rh-shadow-fault-2-0"] == "RELEASED"


def test_8_closed_position_reservation_is_orphan(test_db):
    _add_res(test_db, "rh-shadow-closed_ep-0", created_at="2026-09-10T08:00:00Z")
    _add_pos(test_db, "closed_ep", closed_at="2026-09-10T09:00:00Z")

    res = cleanup.run_cleanup(test_db, apply=False, now_dt=NOW_DT)
    assert res["scan"]["orphan_count"] == 1

    res_apply = cleanup.run_cleanup(test_db, apply=True, now_dt=NOW_DT)
    assert res_apply["released"] == 1



def test_criterion_is_episode_ended_not_unclosed_position(tmp_path):
    """The orphan test must be "episode ended", not "position still open".

    The original spec said an orphan is a reservation whose episode has no
    unclosed position. That criterion is vacuous here: Shadow has no close path,
    so rh_shadow_positions.closed_at is NULL on every row ever written, every
    episode looks open, and the scan identified zero orphans while the bucket sat
    at 23000 against a 4250 cap.

    Shadow holds one virtual position at a time and, since RH-02ce, releases its
    own reservation when the episode ends. So a still-PENDING reservation belongs
    to a finished episode unless it is the one currently running -- the most
    recent by opened_at.
    """
    from scripts.lp_rh_reservation_cleanup_v1 import scan_reservations
    from scripts.lp_rh_store_v1_readonly import migrate, open_store

    conn = open_store(tmp_path / "c.db"); migrate(conn)
    for ep, opened in (("ep-old", "2026-09-10T10:00:00Z"),
                       ("ep-mid", "2026-09-10T11:00:00Z"),
                       ("ep-new", "2026-09-10T12:00:00Z")):
        conn.execute(
            "INSERT INTO rh_shadow_positions (strategy_episode, position_id, pool_key,"
            " profile, bucket, opened_at, closed_at) VALUES (?, ?, '0xp', 'CORE', 'CORE', ?, NULL)",
            (ep, f"rh-shadow-{ep}", opened))
        conn.execute(
            "INSERT INTO rh_bucket_reservations (intent_id, policy_version, bucket,"
            " amount_usd, status, created_at, released_at)"
            " VALUES (?, 'rh_50_30_20_proposed_v1', 'CORE', '1000', 'PENDING', ?, NULL)",
            (f"rh-shadow-{ep}-0", opened))
    conn.commit()

    scan = scan_reservations(conn, older_than_hours=0.0)
    orphan_ids = {o["intent_id"] for o in scan["orphans"]}
    assert orphan_ids == {"rh-shadow-ep-old-0", "rh-shadow-ep-mid-0"}, orphan_ids
    assert "rh-shadow-ep-new-0" not in orphan_ids, "the running episode must be spared"
    assert scan["semantic_count"] == 2
    conn.close()
