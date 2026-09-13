from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

STATE_PROPOSED = "PROPOSED"
STATE_SIMULATED_OK = "SIMULATED_OK"
# CA-03 (PAPER_ACCEPTANCE_REPAIR_V2): default research path (verify_calldata
# False) MUST NOT label an intent SIMULATED_OK -- no decoder ran, no simulator
# ran.  Callers that did not invoke verify_intent_or_reject (or whose wrapper
# call did not produce evidence) MUST write RESEARCH_ONLY_NOT_SIMULATED so
# downstream consumers can tell that no actual simulation occurred.
STATE_RESEARCH_ONLY_NOT_SIMULATED = "RESEARCH_ONLY_NOT_SIMULATED"
STATE_WHITELIST_REJECTED = "WHITELIST_REJECTED"
STATE_DECODER_REJECTED = "DECODER_REJECTED"
STATE_SIMULATED_FAIL = "SIMULATED_FAIL"
STATE_SUBMITTED = "SUBMITTED"
STATE_CONFIRMED = "CONFIRMED"

DRY_RUN_BLOCKED_STATES = frozenset({STATE_SUBMITTED, STATE_CONFIRMED})

RH_TX_INTENTS_COLUMNS = (
    "request_id",
    "idempotency_key",
    "chain_id",
    "wallet_id",
    "position_id",
    "nonce",
    "state",
    "calldata_hash",
    "policy_hash",
    "expires_at",
    "created_at",
    "intent_type",
    "target_address",
    "recipient_address",
    "selector",
    "value_wei",
    "reject_reason",
    "tx_hash",
    "submitted_at",
    "confirmed_at",
    "broadcaster_signature",
    "simulated_at",
    "live_block_number",
)


class DryRunViolation(Exception):
    """Raised when an action is prohibited in dry-run mode."""


def is_dry_run() -> bool:
    """Check if dry-run is active based on LPBOT_TX_DRY_RUN environment variable.

    Defaults to 'true'. Returns False only if LPBOT_TX_DRY_RUN == 'false' (literal).
    """
    return os.environ.get("LPBOT_TX_DRY_RUN", "true") != "false"


def _row_to_dict(cursor: sqlite3.Cursor, row: Any) -> Optional[dict[str, Any]]:
    if row is None:
        return None
    names = [col[0] for col in cursor.description]
    return {k: v for k, v in zip(names, row)}


def _is_unique_idempotency_conflict(exc: sqlite3.IntegrityError, *, idempotency_key: str) -> bool:
    """CA-04 (PAPER_ACCEPTANCE_REPAIR_V2): classify an IntegrityError.

    Only UNIQUE constraint violations against the ``idempotency_key`` column
    (or ``request_id`` -- the other candidate PK) are the recoverable
    "already-recorded" path.  Anything else (NOT NULL violation, FK
    violation, CHECK violation, UNIQUE on a different column) MUST propagate
    so the caller can decide between rollback and structural schema repair.

    The classifier inspects the error message string because SQLite's
    stdlib binding does not expose structured constraint info.  Pattern
    matches on the standard SQLite phrasing ``UNIQUE constraint failed:
    <column>``.
    """
    msg = str(exc).lower()
    if "unique constraint failed" not in msg:
        return False
    return idempotency_key.lower() in msg or "idempotency_key" in msg or "request_id" in msg


class TxIntentWriter:
    """Writer and state manager for the rh_tx_intents SQLite table."""

    def __init__(self, conn: sqlite3.Connection, dry_run: bool = True) -> None:
        self.conn = conn
        self.dry_run = dry_run

    def write_intent(
        self,
        *,
        request_id: str,
        idempotency_key: str,
        chain_id: int,
        wallet_id: Optional[str] = None,
        position_id: Optional[str] = None,
        intent_type: str,
        target_address: str,
        recipient_address: str,
        selector: str,
        calldata_hash: str,
        value_wei: str = "0",
        policy_hash: str,
        expires_at: str,
    ) -> dict[str, Any]:
        """Write an intent row or return existing on idempotency collision."""
        cur = self.conn.execute(
            "SELECT * FROM rh_tx_intents WHERE idempotency_key = ?",
            (idempotency_key,),
        )
        existing = cur.fetchone()
        if existing is not None:
            res = _row_to_dict(cur, existing)
            assert res is not None
            res["idempotent_hit"] = True
            return res

        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        val_wei = "0" if value_wei is None else str(value_wei)
        w_id = wallet_id.lower() if wallet_id is not None else None
        tgt_addr = target_address.lower() if target_address is not None else ""
        rcp_addr = recipient_address.lower() if recipient_address is not None else ""
        sel = selector.lower() if selector is not None else ""

        try:
            self.conn.execute(
                "INSERT INTO rh_tx_intents ("
                "  request_id, idempotency_key, chain_id, wallet_id, position_id,"
                "  nonce, state, calldata_hash, policy_hash, expires_at, created_at,"
                "  intent_type, target_address, recipient_address, selector, value_wei,"
                "  reject_reason, tx_hash, submitted_at, confirmed_at, broadcaster_signature,"
                "  simulated_at, live_block_number"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    request_id,
                    idempotency_key,
                    chain_id,
                    w_id,
                    position_id,
                    None,
                    STATE_PROPOSED,
                    calldata_hash,
                    policy_hash,
                    expires_at,
                    now_utc,
                    intent_type,
                    tgt_addr,
                    rcp_addr,
                    sel,
                    val_wei,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                ),
            )
            # CA-04 (PAPER_ACCEPTANCE_REPAIR_V2): do NOT auto-commit.
            # The caller owns the transaction boundary so it can roll back
            # the writer row together with the journal/position/reservation
            # rows from the same episode when admission decides to reject
            # after the fact.  Auto-commit here would silently terminate the
            # enclosing ``BEGIN IMMEDIATE`` transaction (SQLite has no nested
            # transactions), making the caller's rollback a no-op and the
            # subsequent writer.write_intent on the next step unable to
            # observe its predecessor's row inside the same atomic boundary.
        except sqlite3.IntegrityError as exc:
            # CA-04: only the idempotency_key UNIQUE constraint conflict is
            # the recoverable "already-recorded" path.  Other IntegrityError
            # subclasses (NOT NULL violations, FK violations, CHECK
            # violations) must propagate so the caller can decide between
            # rollback and structural schema repair -- silently returning an
            # idempotent_hit for those would mask real bugs (e.g. a caller
            # passing ``wallet_id=None`` against a NOT NULL wallet_id column).
            if not _is_unique_idempotency_conflict(exc, idempotency_key=idempotency_key):
                raise
            cur = self.conn.execute(
                "SELECT * FROM rh_tx_intents WHERE idempotency_key = ?",
                (idempotency_key,),
            )
            existing = cur.fetchone()
            if existing is not None:
                res = _row_to_dict(cur, existing)
                assert res is not None
                res["idempotent_hit"] = True
                return res
            raise

        cur = self.conn.execute(
            "SELECT * FROM rh_tx_intents WHERE request_id = ?",
            (request_id,),
        )
        row = cur.fetchone()
        res = _row_to_dict(cur, row)
        assert res is not None
        res["idempotent_hit"] = False
        return res

    def update_state(
        self,
        request_id: str,
        new_state: str,
        *,
        reject_reason: Optional[str] = None,
        tx_hash: Optional[str] = None,
        submitted_at: Optional[str] = None,
        confirmed_at: Optional[str] = None,
        broadcaster_signature: Optional[str] = None,
        simulated_at: Optional[str] = None,
        live_block_number: Optional[int] = None,
    ) -> None:
        """Update the state and optional fields of an intent row."""
        if new_state in DRY_RUN_BLOCKED_STATES:
            if self.dry_run or is_dry_run():
                raise DryRunViolation(
                    f"Refusing state transition to {new_state} in dry-run mode "
                    f"(writer.dry_run={self.dry_run}, is_dry_run={is_dry_run()})"
                )

        updates: list[str] = ["state = ?"]
        params: list[Any] = [new_state]

        if reject_reason is not None:
            updates.append("reject_reason = ?")
            params.append(reject_reason)
        if tx_hash is not None:
            updates.append("tx_hash = ?")
            params.append(tx_hash)
        if submitted_at is not None:
            updates.append("submitted_at = ?")
            params.append(submitted_at)
        if confirmed_at is not None:
            updates.append("confirmed_at = ?")
            params.append(confirmed_at)
        if broadcaster_signature is not None:
            updates.append("broadcaster_signature = ?")
            params.append(broadcaster_signature)
        if simulated_at is not None:
            updates.append("simulated_at = ?")
            params.append(simulated_at)
        if live_block_number is not None:
            updates.append("live_block_number = ?")
            params.append(live_block_number)

        params.append(request_id)
        sql = f"UPDATE rh_tx_intents SET {', '.join(updates)} WHERE request_id = ?"
        self.conn.execute(sql, params)
        # CA-04 (PAPER_ACCEPTANCE_REPAIR_V2): no auto-commit -- the caller
        # owns the transaction boundary so it can roll back the state
        # transition together with the journal / position / reservation
        # rows from the same episode when admission decides to reject after
        # the fact.

    def get_intent(self, request_id: str) -> Optional[dict[str, Any]]:
        """Retrieve full intent row by request_id."""
        cur = self.conn.execute(
            "SELECT * FROM rh_tx_intents WHERE request_id = ?",
            (request_id,),
        )
        return _row_to_dict(cur, cur.fetchone())


if __name__ == "__main__":
    if "--print-schema" in sys.argv:
        for col in RH_TX_INTENTS_COLUMNS:
            print(col)
