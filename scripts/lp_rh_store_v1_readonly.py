#!/usr/bin/env python3
"""RH-02a: independent SQLite storage layer for the RH read-only pipeline.

Owns ``reports/lp_rh/scanner.db`` (separate from legacy lp_scanner).  Storage
skeleton only: DDL, open/migrate, decimal/UTC type guards, soft size budget.
No collection, no network, no business data.  Money/raw/price/multiplier are
decimal TEXT (never floating-point); timestamps are UTC RFC3339.  DDL runs in one
transaction; schema version is recorded in ``PRAGMA user_version``.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SCHEMA_VERSION = 1
DEFAULT_DB_PATH = REPO_ROOT / "reports/lp_rh/scanner.db"
SOFT_BUDGET_BYTES = 2 * 1024 ** 3
WARN_FRACTION = 0.80

_DECIMAL_RE = re.compile(r"^-?\d+(\.\d+)?$")
_UTC_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$"
)

# (table, primary_key, [column specs]) -- single source of truth for the DDL.
_TABLES = [
    ("rh_source_snapshots", ("source", "payload_hash"), [
        "source TEXT NOT NULL", "payload_hash TEXT NOT NULL",
        "source_event_time TEXT", "fetch_time TEXT NOT NULL",
        "schema_kind TEXT", "raw_ref TEXT", "quality TEXT"]),
    ("rh_assets", ("chain_id", "address", "metadata_version"), [
        "chain_id INTEGER NOT NULL", "address TEXT NOT NULL",
        "metadata_version INTEGER NOT NULL", "symbol_display TEXT",
        "uid TEXT", "underlying TEXT", "decimals INTEGER",
        "multiplier_raw TEXT", "status TEXT", "capability_json TEXT",
        "source_payload_hash TEXT", "updated_at TEXT NOT NULL"]),
    ("rh_contract_attestations",
     ("chain_id", "address", "block_hash", "policy_version"), [
        "chain_id INTEGER NOT NULL", "address TEXT NOT NULL",
        "block_hash TEXT NOT NULL", "policy_version TEXT NOT NULL",
        "code_hash TEXT", "implementation TEXT", "abi_version TEXT",
        "attestation_status TEXT NOT NULL", "evidence_json TEXT",
        "expires_at TEXT", "created_at TEXT NOT NULL"]),
    ("rh_pool_registry", ("chain_id", "protocol", "pool_key"), [
        "chain_id INTEGER NOT NULL", "protocol TEXT NOT NULL",
        "pool_key TEXT NOT NULL", "pool_address TEXT", "pool_id TEXT",
        "token0 TEXT", "token1 TEXT", "fee TEXT",
        "tick_spacing INTEGER", "hooks TEXT",
        "attestation_status TEXT NOT NULL", "discovered_at TEXT NOT NULL"]),
    ("rh_pool_events", ("chain_id", "block_hash", "tx_hash", "log_index"), [
        "chain_id INTEGER NOT NULL", "block_hash TEXT NOT NULL",
        "tx_hash TEXT NOT NULL", "log_index INTEGER NOT NULL",
        "block_number INTEGER NOT NULL", "pool_key TEXT NOT NULL",
        "event_type TEXT NOT NULL", "amount0_raw TEXT",
        "amount1_raw TEXT", "liquidity_raw TEXT", "tick INTEGER",
        "observed_at TEXT NOT NULL"]),
    ("rh_market_states", ("asset_address", "sample_time"), [
        "asset_address TEXT NOT NULL", "sample_time TEXT NOT NULL",
        "chain_id INTEGER NOT NULL", "source_payload_hash TEXT",
        "session TEXT NOT NULL", "health_flags_json TEXT NOT NULL",
        "reference_bid TEXT", "reference_ask TEXT", "reference_mid TEXT",
        "reference_age_secs INTEGER", "multiplier_human TEXT",
        "oracle_paused INTEGER"]),
    ("rh_rpc_health", ("provider", "method", "sample_time"), [
        "provider TEXT NOT NULL", "method TEXT NOT NULL",
        "sample_time TEXT NOT NULL", "latency_ms INTEGER",
        "error TEXT", "last_good_block INTEGER", "state TEXT NOT NULL"]),
    ("rh_economic_evaluations",
     ("candidate_key", "snapshot_id", "model_version", "policy_version",
      "horizon_hours", "position_usd"), [
        "candidate_key TEXT NOT NULL", "snapshot_id TEXT NOT NULL",
        "model_version TEXT NOT NULL", "policy_version TEXT NOT NULL",
        "horizon_hours INTEGER NOT NULL", "position_usd TEXT NOT NULL",
        "fee_ev TEXT", "reward_ev TEXT", "cost_components_json TEXT",
        "netcover TEXT", "abs_profit TEXT", "q_min TEXT", "q_max TEXT",
        "missing_inputs_json TEXT", "evaluated_at TEXT NOT NULL"]),
    ("rh_gate_decisions", ("decision_id",), [
        "decision_id TEXT NOT NULL", "candidate_key TEXT NOT NULL",
        "target_mode TEXT NOT NULL", "primary_status TEXT NOT NULL",
        "terminal_bits_json TEXT NOT NULL", "dominant_blocker TEXT",
        "reasons_json TEXT", "snapshot_ids_json TEXT", "decided_at TEXT NOT NULL"]),
    ("rh_shadow_positions", ("strategy_episode", "position_id"), [
        "strategy_episode TEXT NOT NULL", "position_id TEXT NOT NULL",
        "pool_key TEXT NOT NULL", "profile TEXT NOT NULL",
        "bucket TEXT NOT NULL", "initial_token0_raw TEXT",
        "initial_token1_raw TEXT", "tick_lower INTEGER",
        "tick_upper INTEGER", "virtual_liquidity_raw TEXT",
        "opened_at TEXT NOT NULL", "closed_at TEXT"]),
    ("rh_journal", ("event_id",), [
        "event_id TEXT NOT NULL", "idempotency_key TEXT UNIQUE",
        "account_debit TEXT NOT NULL", "account_credit TEXT NOT NULL",
        "asset TEXT NOT NULL", "amount_raw TEXT NOT NULL",
        "is_external_flow INTEGER NOT NULL", "ref_json TEXT",
        "booked_at TEXT NOT NULL"]),
    ("rh_position_marks", ("position_id", "mark_time"), [
        "position_id TEXT NOT NULL", "mark_time TEXT NOT NULL",
        "price_snapshot_id TEXT", "reference_nav TEXT",
        "liquidation_nav TEXT", "accrued_fee TEXT", "unvalued_risk_json TEXT"]),
    ("rh_bucket_reservations", ("intent_id",), [
        "intent_id TEXT NOT NULL", "policy_version TEXT NOT NULL",
        "bucket TEXT NOT NULL", "amount_usd TEXT NOT NULL",
        "status TEXT NOT NULL", "created_at TEXT NOT NULL", "released_at TEXT"]),
    ("rh_tx_intents", ("request_id",), [
        "request_id TEXT NOT NULL", "idempotency_key TEXT UNIQUE",
        "chain_id INTEGER NOT NULL", "wallet_id TEXT",
        "position_id TEXT", "nonce INTEGER", "state TEXT NOT NULL",
        "calldata_hash TEXT", "policy_hash TEXT", "expires_at TEXT",
        "created_at TEXT NOT NULL"]),
    ("rh_tx_receipts", ("request_id", "tx_hash"), [
        "request_id TEXT NOT NULL", "tx_hash TEXT NOT NULL",
        "block_hash TEXT", "block_number INTEGER",
        "status TEXT NOT NULL", "gas_used TEXT",
        "reorg_detected INTEGER NOT NULL DEFAULT 0", "observed_at TEXT NOT NULL"]),
    ("rh_reconciliation_runs", ("run_id",), [
        "run_id TEXT NOT NULL", "started_at TEXT NOT NULL",
        "finished_at TEXT", "evidence_json TEXT",
        "delta_json TEXT", "verdict TEXT NOT NULL"]),
]

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_rh_pool_events_pool_block ON rh_pool_events(pool_key, block_number);",
    "CREATE INDEX IF NOT EXISTS idx_rh_market_states_asset_time ON rh_market_states(asset_address, sample_time DESC);",
    "CREATE INDEX IF NOT EXISTS idx_rh_rpc_health_provider_time ON rh_rpc_health(provider, sample_time DESC);",
    "CREATE INDEX IF NOT EXISTS idx_rh_gate_decisions_candidate_time ON rh_gate_decisions(candidate_key, decided_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_rh_journal_booked ON rh_journal(booked_at);",
]

# Columns that must be decimal TEXT (money / raw amount / price / multiplier).
MONEY_COLUMNS = {
    "rh_assets": frozenset({"multiplier_raw"}),
    "rh_pool_events": frozenset({"amount0_raw", "amount1_raw", "liquidity_raw"}),
    "rh_market_states": frozenset({"reference_bid", "reference_ask", "reference_mid", "multiplier_human"}),
    "rh_economic_evaluations": frozenset({"position_usd", "fee_ev", "reward_ev", "netcover", "abs_profit", "q_min", "q_max"}),
    "rh_shadow_positions": frozenset({"initial_token0_raw", "initial_token1_raw", "virtual_liquidity_raw"}),
    "rh_journal": frozenset({"amount_raw"}),
    "rh_position_marks": frozenset({"reference_nav", "liquidation_nav", "accrued_fee"}),
    "rh_bucket_reservations": frozenset({"amount_usd"}),
    "rh_tx_receipts": frozenset({"gas_used"}),
}

# Columns that must be UTC RFC3339 strings.
TIME_COLUMNS = {
    "rh_source_snapshots": frozenset({"source_event_time", "fetch_time"}),
    "rh_assets": frozenset({"updated_at"}),
    "rh_contract_attestations": frozenset({"expires_at", "created_at"}),
    "rh_pool_registry": frozenset({"discovered_at"}),
    "rh_pool_events": frozenset({"observed_at"}),
    "rh_market_states": frozenset({"sample_time"}),
    "rh_rpc_health": frozenset({"sample_time"}),
    "rh_economic_evaluations": frozenset({"evaluated_at"}),
    "rh_gate_decisions": frozenset({"decided_at"}),
    "rh_shadow_positions": frozenset({"opened_at", "closed_at"}),
    "rh_journal": frozenset({"booked_at"}),
    "rh_position_marks": frozenset({"mark_time"}),
    "rh_bucket_reservations": frozenset({"created_at", "released_at"}),
    "rh_tx_intents": frozenset({"expires_at", "created_at"}),
    "rh_tx_receipts": frozenset({"observed_at"}),
    "rh_reconciliation_runs": frozenset({"started_at", "finished_at"}),
}

TABLES = frozenset(name for name, _, _ in _TABLES)


def _build_schema() -> str:
    parts = []
    for name, pk, columns in _TABLES:
        defs = list(columns) + ["PRIMARY KEY (" + ", ".join(pk) + ")"]
        parts.append("CREATE TABLE IF NOT EXISTS " + name + " (\n    "
                     + ",\n    ".join(defs) + "\n);")
    parts.extend(_INDEXES)
    return "\n\n".join(parts)


_SCHEMA = _build_schema()


def open_store(path: Any = DEFAULT_DB_PATH, *, read_only: bool = False) -> sqlite3.Connection:
    """Open the RH store; create the parent directory in write mode."""
    path = Path(path)
    if read_only:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30.0)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def migrate(conn: sqlite3.Connection) -> int:
    """Create all tables/indexes in one transaction; idempotent per version."""
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current == SCHEMA_VERSION:
        return SCHEMA_VERSION
    script = (
        "BEGIN;\n"
        + _SCHEMA
        + "\nPRAGMA user_version = "
        + str(SCHEMA_VERSION)
        + ";\nCOMMIT;"
    )
    conn.executescript(script)
    return SCHEMA_VERSION


def assert_decimal_text(value: Any, field: str) -> Optional[str]:
    """Coerce a money/raw/price/multiplier value to a validated decimal string."""
    if value is None:
        return None
    if isinstance(value, float):
        raise TypeError(f"REAL_NOT_ALLOWED_FOR_MONEY: {field}")
    if isinstance(value, bool):
        raise TypeError(f"REAL_NOT_ALLOWED_FOR_MONEY: {field}")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        if not _DECIMAL_RE.match(value):
            raise ValueError(f"INVALID_DECIMAL_TEXT: {field}")
        return value
    raise TypeError(f"REAL_NOT_ALLOWED_FOR_MONEY: {field}")


def assert_utc_rfc3339(value: Any, field: str) -> Optional[str]:
    """Validate a UTC RFC3339 timestamp string; None passes through."""
    if value is None:
        return None
    if not isinstance(value, str) or not _UTC_RE.match(value):
        raise ValueError(f"NON_UTC_TIMESTAMP: {field}")
    return value


def insert_row(conn: sqlite3.Connection, table: str, row: Mapping[str, Any]) -> None:
    """Insert one row using parameterized placeholders after type guards."""
    if table not in TABLES:
        raise ValueError("UNKNOWN_TABLE")
    info = conn.execute(f"PRAGMA table_info({table})").fetchall()
    if not info:
        raise ValueError("UNKNOWN_TABLE")
    money_cols = MONEY_COLUMNS.get(table, frozenset())
    time_cols = TIME_COLUMNS.get(table, frozenset())
    cols: list[str] = []
    values: list[Any] = []
    for record in info:
        col = record[1]
        if col not in row:
            continue
        value = row[col]
        if col in money_cols:
            value = assert_decimal_text(value, col)
        elif col in time_cols:
            value = assert_utc_rfc3339(value, col)
        cols.append(col)
        values.append(value)
    if not cols:
        raise ValueError("EMPTY_ROW")
    placeholders = ",".join("?" for _ in cols)
    conn.execute(
        f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})",
        values,
    )


def budget_status(path: Any = DEFAULT_DB_PATH) -> dict:
    """Report the on-disk size of the store against the soft byte budget."""
    path = Path(path)
    size = 0
    for suffix in ("", "-wal", "-shm"):
        candidate = path if not suffix else path.with_name(path.name + suffix)
        if candidate.exists():
            size += candidate.stat().st_size
    fraction = size / SOFT_BUDGET_BYTES if SOFT_BUDGET_BYTES > 0 else 0.0
    if fraction >= 1.0:
        state = "OVER"
    elif fraction >= WARN_FRACTION:
        state = "WARN"
    else:
        state = "OK"
    return {
        "bytes": size,
        "soft_budget_bytes": SOFT_BUDGET_BYTES,
        "fraction": fraction,
        "state": state,
    }


def _table_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name LIKE 'rh_%' ORDER BY name"
    ).fetchall()
    return [row[0] for row in rows]


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="RH independent SQLite store (read-only pipeline local writes)"
    )
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--init", action="store_true",
                        help="create/migrate the store and print a schema summary")
    parser.add_argument("--status", action="store_true",
                        help="print a read-only schema summary")
    args = parser.parse_args(argv)
    db_path = Path(args.db)
    if args.init:
        conn = open_store(db_path)
        try:
            version = migrate(conn)
            tables = _table_names(conn)
        finally:
            conn.close()
    elif args.status:
        conn = open_store(db_path, read_only=True)
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            tables = _table_names(conn)
        finally:
            conn.close()
    else:
        parser.print_help()
        return 2
    result = {
        "schema_version": version,
        "tables": tables,
        "budget": budget_status(db_path),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
