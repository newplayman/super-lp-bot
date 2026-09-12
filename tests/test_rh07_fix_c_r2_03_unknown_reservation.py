import sqlite3
import pytest

from scripts.lp_rh_shadow_daemon_v1_readonly import _copy_new_rows


def test_copy_new_rows_rejects_unknown_to_released_or_expired():
    """R2-03: Verify _copy_new_rows does not update BROADCAST_UNKNOWN to RELEASED or EXPIRED."""
    scratch = sqlite3.connect(":memory:")
    ledger = sqlite3.connect(":memory:")

    for c in (scratch, ledger):
        c.execute("""
            CREATE TABLE rh_bucket_reservations (
                intent_id TEXT PRIMARY KEY,
                status TEXT,
                released_at TEXT
            )
        """)

    # Ledger holds BROADCAST_UNKNOWN
    ledger.execute("INSERT INTO rh_bucket_reservations VALUES (?, ?, ?)",
                   ("intent-unknown", "BROADCAST_UNKNOWN", None))
    # Scratch tries to transition to RELEASED
    scratch.execute("INSERT INTO rh_bucket_reservations VALUES (?, ?, ?)",
                    ("intent-unknown", "RELEASED", "2026-09-11T15:00:00Z"))

    stats = _copy_new_rows(scratch, ledger)

    row = ledger.execute("SELECT status, released_at FROM rh_bucket_reservations WHERE intent_id = 'intent-unknown'").fetchone()
    # Must remain BROADCAST_UNKNOWN
    assert row[0] == "BROADCAST_UNKNOWN"
    assert row[1] is None

    # Scratch tries to transition to EXPIRED
    scratch.execute("UPDATE rh_bucket_reservations SET status = 'EXPIRED' WHERE intent_id = 'intent-unknown'")
    stats2 = _copy_new_rows(scratch, ledger)
    row2 = ledger.execute("SELECT status, released_at FROM rh_bucket_reservations WHERE intent_id = 'intent-unknown'").fetchone()
    assert row2[0] == "BROADCAST_UNKNOWN"
    assert row2[1] is None

    scratch.close()
    ledger.close()


def test_copy_new_rows_allows_pending_to_released_control():
    """R2-03 control: Verify _copy_new_rows allows PENDING to transition to RELEASED."""
    scratch = sqlite3.connect(":memory:")
    ledger = sqlite3.connect(":memory:")

    for c in (scratch, ledger):
        c.execute("""
            CREATE TABLE rh_bucket_reservations (
                intent_id TEXT PRIMARY KEY,
                status TEXT,
                released_at TEXT
            )
        """)

    ledger.execute("INSERT INTO rh_bucket_reservations VALUES (?, ?, ?)",
                   ("intent-pending", "PENDING", None))
    scratch.execute("INSERT INTO rh_bucket_reservations VALUES (?, ?, ?)",
                    ("intent-pending", "RELEASED", "2026-09-11T15:00:00Z"))

    stats = _copy_new_rows(scratch, ledger)
    row = ledger.execute("SELECT status, released_at FROM rh_bucket_reservations WHERE intent_id = 'intent-pending'").fetchone()
    assert row[0] == "RELEASED"
    assert row[1] == "2026-09-11T15:00:00Z"

    scratch.close()
    ledger.close()
