from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

STATE_PROPOSED = "PROPOSED"
STATE_SIMULATED_OK = "SIMULATED_OK"
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
            self.conn.commit()
        except sqlite3.IntegrityError:
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
        self.conn.commit()

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
