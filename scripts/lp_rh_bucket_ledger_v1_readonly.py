#!/usr/bin/env python3
"""RH-02b: atomic bucket reservations + capital policy conflict reporting.

Pure logic over the RH-02a store (``scripts.lp_rh_store_v1_readonly``).
Money is ``decimal.Decimal`` end to end; the database stores normalized
decimal TEXT.  ``try_reserve`` performs check-reserved / insert-reservation
inside one ``BEGIN IMMEDIATE`` transaction so two candidates can never each
read the same available room and both reserve it in full (PRD §16.3, T27).
No network, no collection, no writes to ``reports/lp_rh/``.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_store_v1_readonly import (  # noqa: E402
    assert_decimal_text,
    assert_utc_rfc3339,
    migrate,
)

BUCKETS = ("CORE", "STOCK", "MEME")
POLICY_ID = "rh_50_30_20_proposed_v1"
BUCKET_WEIGHTS = {
    "CORE": Decimal("0.50"),
    "STOCK": Decimal("0.30"),
    "MEME": Decimal("0.20"),
}
ACTIVE_FRACTION = {
    "CORE": Decimal("0.85"),
    "STOCK": Decimal("0.70"),
    "MEME": Decimal("0.40"),
}
RESERVED_STATUSES = ("PENDING", "CONFIRMED", "BROADCAST_UNKNOWN")
VALID_STATUSES = ("PENDING", "CONFIRMED", "BROADCAST_UNKNOWN", "RELEASED", "EXPIRED")


def _require_decimal(value: Any, field: str) -> Decimal:
    """Reject float/bool; money must be a Decimal (never floating-point)."""
    if isinstance(value, bool) or not isinstance(value, Decimal):
        raise TypeError(f"DECIMAL_REQUIRED: {field}")
    return value


def _to_decimal_text(value: Decimal) -> str:
    """Fixed-point text with trailing zeros stripped (no scientific notation)."""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def migrate_checked(conn: sqlite3.Connection) -> int:
    """Guard: refuse to migrate a connection that already holds a transaction."""
    if conn.in_transaction:
        raise RuntimeError("MIGRATE_INSIDE_TRANSACTION")
    return migrate(conn)


def bucket_budget(capital_usd: Decimal, bucket: str) -> Decimal:
    if bucket not in BUCKETS:
        raise ValueError("UNKNOWN_BUCKET")
    return _require_decimal(capital_usd, "capital_usd") * BUCKET_WEIGHTS[bucket]


def bucket_active_cap(capital_usd: Decimal, bucket: str) -> Decimal:
    return bucket_budget(capital_usd, bucket) * ACTIVE_FRACTION[bucket]


def reserved_total(conn: sqlite3.Connection, bucket: str, policy_version: str) -> Decimal:
    """Sum of active reservations for a bucket; BROADCAST_UNKNOWN counts (PRD §16.3)."""
    placeholders = ", ".join("?" for _ in RESERVED_STATUSES)
    rows = conn.execute(
        "SELECT amount_usd FROM rh_bucket_reservations "
        f"WHERE bucket = ? AND policy_version = ? AND status IN ({placeholders}) "
        "AND released_at IS NULL",
        (bucket, policy_version, *RESERVED_STATUSES),
    ).fetchall()
    total = Decimal("0")
    for (amount_text,) in rows:
        total += Decimal(amount_text)
    return total


def try_reserve(conn: sqlite3.Connection, *, intent_id: str, bucket: str,
                amount_usd: Decimal, capital_usd: Decimal,
                policy_version: str = POLICY_ID, now: str) -> dict:
    """Atomically reserve ``amount_usd`` from a bucket's active cap.

    Reads the reserved total and inserts the PENDING reservation inside one
    ``BEGIN IMMEDIATE`` transaction.  Returns a grant/deny dict; raises
    ``ValueError`` for bad bucket/amount and lets ``sqlite3.IntegrityError``
    (duplicate intent_id) propagate.
    """
    if bucket not in BUCKETS:
        raise ValueError("UNKNOWN_BUCKET")
    amount_usd = _require_decimal(amount_usd, "amount_usd")
    capital_usd = _require_decimal(capital_usd, "capital_usd")
    if amount_usd <= 0:
        raise ValueError("NON_POSITIVE_RESERVATION")
    now = assert_utc_rfc3339(now, "now")
    amount_text = assert_decimal_text(_to_decimal_text(amount_usd), "amount_usd")
    conn.execute("BEGIN IMMEDIATE")
    try:
        reserved = reserved_total(conn, bucket, policy_version)
        room = bucket_active_cap(capital_usd, bucket) - reserved
        if amount_usd > room:
            conn.execute("ROLLBACK")
            return {"granted": False, "reason": "BUCKET_ACTIVE_CAP_EXCEEDED",
                    "room": _to_decimal_text(room)}
        conn.execute(
            "INSERT INTO rh_bucket_reservations "
            "(intent_id, policy_version, bucket, amount_usd, status, created_at, "
            "released_at) VALUES (?, ?, ?, ?, 'PENDING', ?, NULL)",
            (intent_id, policy_version, bucket, amount_text, now),
        )
        conn.execute("COMMIT")
        return {"granted": True, "reservation_id": intent_id,
                "room_after": _to_decimal_text(room - amount_usd)}
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def release(conn: sqlite3.Connection, intent_id: str, *, now: str,
            reason: str) -> bool:
    """Mark a reservation RELEASED and stamp released_at.

    Refuses to release a BROADCAST_UNKNOWN reservation (PRD §16.3, T51).
    Returns False when the intent_id is unknown.
    """
    now = assert_utc_rfc3339(now, "now")
    row = conn.execute(
        "SELECT status FROM rh_bucket_reservations WHERE intent_id = ?",
        (intent_id,),
    ).fetchone()
    if row is None:
        return False
    if row[0] == "BROADCAST_UNKNOWN":
        raise ValueError("CANNOT_RELEASE_BROADCAST_UNKNOWN")
    conn.execute(
        "UPDATE rh_bucket_reservations SET status = 'RELEASED', released_at = ? "
        "WHERE intent_id = ?",
        (now, intent_id),
    )
    conn.commit()
    return True


def set_status(conn: sqlite3.Connection, intent_id: str, status: str, *,
               now: str) -> None:
    """Move a reservation to a whitelisted status; reject anything else."""
    if status not in VALID_STATUSES:
        raise ValueError(f"INVALID_STATUS: {status}")
    assert_utc_rfc3339(now, "now")
    conn.execute(
        "UPDATE rh_bucket_reservations SET status = ? WHERE intent_id = ?",
        (status, intent_id),
    )
    conn.commit()


def capital_policy_conflict(capital_usd: Decimal, *,
                            legacy_min_position: Decimal) -> dict:
    """Report (never auto-adjust) when the CORE active cap is below the legacy minimum."""
    capital_usd = _require_decimal(capital_usd, "capital_usd")
    legacy_min_position = _require_decimal(legacy_min_position, "legacy_min_position")
    core_cap = bucket_active_cap(capital_usd, "CORE")
    conflict = core_cap < legacy_min_position
    return {
        "conflict": conflict,
        "code": "CAPITAL_POLICY_CONFLICT" if conflict else None,
        "core_cap": _to_decimal_text(core_cap),
        "legacy_min": _to_decimal_text(legacy_min_position),
    }


def _self_test() -> None:
    capital = Decimal("100")
    caps = {b: _to_decimal_text(bucket_active_cap(capital, b)) for b in BUCKETS}
    print("bucket_active_cap(C=100):", json.dumps(caps, sort_keys=True))
    conflict = capital_policy_conflict(capital, legacy_min_position=Decimal("50"))
    print("capital_policy_conflict(C=100, legacy_min=50):",
          json.dumps(conflict, sort_keys=True))
    assert caps == {"CORE": "42.5", "STOCK": "21", "MEME": "8"}, caps
    assert conflict["conflict"] is True and conflict["core_cap"] == "42.5", conflict
    print("LEDGER_SELF_TEST_OK")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="RH-02b atomic bucket reservations (pure logic, read-only)")
    parser.add_argument("--self-test", action="store_true",
                        help="run built-in self-test and exit")
    args = parser.parse_args(argv)
    if args.self_test:
        _self_test()
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
