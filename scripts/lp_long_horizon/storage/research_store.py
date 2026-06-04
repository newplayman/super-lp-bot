"""Research-only storage: SQLite primary + JSONL fallback.

The store writes to both:
- an SQLite database (research.sqlite) for relational queries
- a JSONL file per category for streaming / git diff

If SQLite is unavailable (e.g. permission issue), the store falls back to
JSONL-only and records a warning. The runner decides whether to abort based
on the AbortController.

Safety:
- Read-only callers (the runner). The store itself writes, but only into
  the research.sqlite file and adjacent JSONL files.
- Write path is constrained to ``data/lp_long_horizon/<run_id>/``.
- No production / shadow / live / dryrun paths.
- No wallet / signer / tx / mutation.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


# DDL aligned with the schema from RESEARCH_ONLY_SCHEMA_CN.md (R0 phase).
SQLITE_DDL: dict[str, str] = {
    "pool_snapshots": """
        CREATE TABLE IF NOT EXISTS pool_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pool_address TEXT NOT NULL,
            chain TEXT NOT NULL,
            protocol TEXT NOT NULL,
            program_id TEXT NOT NULL,
            token_mint_a TEXT,
            token_mint_b TEXT,
            token_symbol_a TEXT,
            token_symbol_b TEXT,
            fee_tier_bps INTEGER,
            reserve_a_raw INTEGER,
            reserve_b_raw INTEGER,
            liquidity INTEGER,
            active_tick INTEGER,
            active_bin INTEGER,
            tvl_usd REAL,
            snapshot_at TEXT NOT NULL,
            real_data INTEGER DEFAULT 0,
            data_source TEXT,
            best_net_ev_proxy_usd REAL,
            best_scenario TEXT,
            best_hold_window TEXT,
            best_notional_usd INTEGER
        );
    """,
    "quote_snapshots": """
        CREATE TABLE IF NOT EXISTS quote_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pool_address TEXT NOT NULL,
            notional_usd REAL NOT NULL,
            quote_success INTEGER NOT NULL,
            amount_in_raw INTEGER,
            amount_out_raw INTEGER,
            price_impact_pct REAL,
            slippage_pct REAL,
            fee_raw INTEGER,
            fee_usd REAL,
            error_code TEXT,
            quote_at TEXT NOT NULL,
            real_data INTEGER DEFAULT 0,
            data_source TEXT
        );
    """,
    "fee_velocity": """
        CREATE TABLE IF NOT EXISTS fee_velocity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pool_address TEXT NOT NULL,
            window TEXT NOT NULL,
            volume_proxy_usd REAL,
            fee_capture_proxy_usd REAL,
            volume_to_tvl_pct REAL,
            sample_count INTEGER,
            window_end_at TEXT NOT NULL,
            real_data INTEGER DEFAULT 0,
            data_source TEXT,
            r0_phase_status TEXT
        );
    """,
    "liquidity_distribution": """
        CREATE TABLE IF NOT EXISTS liquidity_distribution (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pool_address TEXT NOT NULL,
            active_range_liquidity REAL,
            near_active_liquidity REAL,
            sparse_liquidity_warning INTEGER,
            out_of_range_risk REAL,
            tick_spacing INTEGER,
            bin_step INTEGER,
            snapshot_at TEXT NOT NULL,
            real_data INTEGER DEFAULT 0,
            data_source TEXT
        );
    """,
    "market_regime": """
        CREATE TABLE IF NOT EXISTS market_regime (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            regime TEXT NOT NULL,
            lookback_days INTEGER NOT NULL,
            price_change_pct REAL,
            realized_vol_pct REAL,
            volume_to_tvl_pct REAL,
            incentive_active INTEGER,
            regime_at TEXT NOT NULL,
            real_data INTEGER DEFAULT 0,
            data_source TEXT
        );
    """,
    "future_actual_fee_accrual": """
        CREATE TABLE IF NOT EXISTS future_actual_fee_accrual (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_id TEXT,
            pool_address TEXT,
            entry_fee_growth_global INTEGER,
            entry_fee_growth_a INTEGER,
            entry_fee_growth_b INTEGER,
            entry_tick_lower INTEGER,
            entry_tick_upper INTEGER,
            entry_at TEXT,
            exit_fee_growth_global INTEGER,
            exit_fee_growth_a INTEGER,
            exit_fee_growth_b INTEGER,
            exit_tick_lower INTEGER,
            exit_tick_upper INTEGER,
            exit_at TEXT,
            tokens_owed_a_raw INTEGER,
            tokens_owed_b_raw INTEGER,
            actual_collected_a_raw INTEGER,
            actual_collected_b_raw INTEGER,
            actual_collected_at TEXT,
            actual_pnl_usd REAL,
            il_realized_pct REAL,
            il_actual_pct REAL,
            r0_phase_status TEXT,
            real_data INTEGER DEFAULT 0
        );
    """,
}


SQLITE_INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_pool_snapshots_pool ON pool_snapshots(pool_address, snapshot_at);",
    "CREATE INDEX IF NOT EXISTS idx_quote_snapshots_pool ON quote_snapshots(pool_address, quote_at);",
    "CREATE INDEX IF NOT EXISTS idx_fee_velocity_pool ON fee_velocity(pool_address, window_end_at);",
    "CREATE INDEX IF NOT EXISTS idx_liquidity_dist_pool ON liquidity_distribution(pool_address, snapshot_at);",
    "CREATE INDEX IF NOT EXISTS idx_market_regime_at ON market_regime(regime_at);",
    "CREATE INDEX IF NOT EXISTS idx_actual_fee_token ON future_actual_fee_accrual(token_id);",
]


# Column lists for sqlite insert. Real_data is stored as 0/1.
_COLUMNS_BY_TABLE: dict[str, list[str]] = {
    "pool_snapshots": [
        "pool_address", "chain", "protocol", "program_id",
        "token_mint_a", "token_mint_b", "token_symbol_a", "token_symbol_b",
        "fee_tier_bps", "reserve_a_raw", "reserve_b_raw", "liquidity",
        "active_tick", "active_bin", "tvl_usd", "snapshot_at",
        "real_data", "data_source",
        "best_net_ev_proxy_usd", "best_scenario", "best_hold_window", "best_notional_usd",
    ],
    "quote_snapshots": [
        "pool_address", "notional_usd", "quote_success",
        "amount_in_raw", "amount_out_raw", "price_impact_pct", "slippage_pct",
        "fee_raw", "fee_usd", "error_code", "quote_at",
        "real_data", "data_source",
    ],
    "fee_velocity": [
        "pool_address", "window", "volume_proxy_usd", "fee_capture_proxy_usd",
        "volume_to_tvl_pct", "sample_count", "window_end_at",
        "real_data", "data_source", "r0_phase_status",
    ],
    "liquidity_distribution": [
        "pool_address", "active_range_liquidity", "near_active_liquidity",
        "sparse_liquidity_warning", "out_of_range_risk", "tick_spacing", "bin_step",
        "snapshot_at", "real_data", "data_source",
    ],
    "market_regime": [
        "regime", "lookback_days", "price_change_pct", "realized_vol_pct",
        "volume_to_tvl_pct", "incentive_active", "regime_at",
        "real_data", "data_source",
    ],
    "future_actual_fee_accrual": [
        "token_id", "pool_address",
        "entry_fee_growth_global", "entry_fee_growth_a", "entry_fee_growth_b",
        "entry_tick_lower", "entry_tick_upper", "entry_at",
        "exit_fee_growth_global", "exit_fee_growth_a", "exit_fee_growth_b",
        "exit_tick_lower", "exit_tick_upper", "exit_at",
        "tokens_owed_a_raw", "tokens_owed_b_raw",
        "actual_collected_a_raw", "actual_collected_b_raw", "actual_collected_at",
        "actual_pnl_usd", "il_realized_pct", "il_actual_pct",
        "r0_phase_status", "real_data",
    ],
}


class ResearchStore:
    """SQLite primary + JSONL fallback research-only storage.

    Usage:
        store = ResearchStore(out_dir)
        store.write_pool_snapshot({...})  # both sqlite + jsonl
        ...
        store.close()

    If SQLite is unavailable, write_* methods fall back to JSONL-only and
    record a warning. The caller (runner) inspects ``store.sqlite_available``
    and ``store.jsonl_only`` to decide what to log.
    """

    def __init__(self, out_dir: Path, *, abort_controller=None):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.sqlite_path = self.out_dir / "research.sqlite"
        self.abort_controller = abort_controller

        self._conn: sqlite3.Connection | None = None
        self._sqlite_available = False
        self._sqlite_warnings: list[str] = []
        try:
            self._conn = sqlite3.connect(str(self.sqlite_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")
            for ddl in SQLITE_DDL.values():
                self._conn.execute(ddl)
            for idx in SQLITE_INDEXES:
                self._conn.execute(idx)
            self._conn.commit()
            self._sqlite_available = True
        except sqlite3.Error as exc:
            self._sqlite_warnings.append(f"sqlite init failed: {exc}")
            if self._conn is not None:
                try:
                    self._conn.close()
                except sqlite3.Error:
                    pass
                self._conn = None

        # jsonl file handles
        self._jsonl_files: dict[str, Any] = {}
        for table in SQLITE_DDL:
            p = self.out_dir / f"{table}.jsonl"
            self._jsonl_files[table] = p.open("a", encoding="utf-8")

        # counters
        self._counts: dict[str, int] = {t: 0 for t in SQLITE_DDL}

    @property
    def sqlite_available(self) -> bool:
        return self._sqlite_available

    @property
    def jsonl_only(self) -> bool:
        return not self._sqlite_available

    @property
    def counts(self) -> dict[str, int]:
        return dict(self._counts)

    @property
    def sqlite_warnings(self) -> list[str]:
        return list(self._sqlite_warnings)

    def write_pool_snapshot(self, record: dict) -> None:
        self._write("pool_snapshots", record)

    def write_quote_snapshot(self, record: dict) -> None:
        self._write("quote_snapshots", record)

    def write_fee_velocity(self, record: dict) -> None:
        self._write("fee_velocity", record)

    def write_liquidity_distribution(self, record: dict) -> None:
        self._write("liquidity_distribution", record)

    def write_market_regime(self, record: dict) -> None:
        self._write("market_regime", record)

    def write_actual_fee_placeholder(self, record: dict) -> None:
        self._write("future_actual_fee_accrual", record)

    def _write(self, table: str, record: dict) -> None:
        # JSONL first (always)
        line = json.dumps(record, ensure_ascii=False)
        fh = self._jsonl_files[table]
        try:
            fh.write(line + "\n")
            fh.flush()
        except OSError as exc:
            if self.abort_controller is not None:
                self.abort_controller.record_write_failure(f"jsonl {table}: {exc}")
            raise

        if self._sqlite_available and self._conn is not None:
            try:
                cols = _COLUMNS_BY_TABLE[table]
                values = [self._coerce_for_sqlite(table, c, record.get(c)) for c in cols]
                placeholders = ",".join(["?"] * len(cols))
                col_list = ",".join(cols)
                self._conn.execute(
                    f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
                    values,
                )
                self._conn.commit()
            except sqlite3.Error as exc:
                self._sqlite_warnings.append(f"sqlite insert {table} failed: {exc}; falling back to jsonl-only for subsequent writes")
                # Disable sqlite for subsequent writes
                try:
                    self._conn.close()
                except sqlite3.Error:
                    pass
                self._conn = None
                self._sqlite_available = False
                if self.abort_controller is not None:
                    # Don't abort on a single insert fail; runner decides
                    self.abort_controller.record_error()

        self._counts[table] += 1

    @staticmethod
    def _coerce_for_sqlite(table: str, col: str, value: Any) -> Any:
        if col == "real_data":
            return 1 if bool(value) else 0
        if col in ("sparse_liquidity_warning", "incentive_active"):
            return 1 if value else 0
        if value is None:
            return None
        return value

    def close(self) -> None:
        for fh in self._jsonl_files.values():
            try:
                fh.close()
            except OSError:
                pass
        if self._conn is not None:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass
            self._conn = None

    def summary(self) -> dict:
        return {
            "sqlite_available": self._sqlite_available,
            "jsonl_only": self.jsonl_only,
            "sqlite_path": str(self.sqlite_path) if self._sqlite_available else None,
            "sqlite_warnings": self._sqlite_warnings,
            "counts": self._counts,
        }


# Static self-check: same pattern as other adapters.
_BANNED_TOKENS_HERE = (
    "private_key", "mnemonic", "seed_phrase", "keypair.from_secret_key",
    "fromSecretKey", "SecretKey", "keystore.json", "encrypted_json",
    "new Signer(", "new Wallet(",
    "sendTransaction", "eth_sendRawTransaction", "eth_sendTransaction",
    "signTransaction(", "signAndSendTransaction(",
    "add_liquidity(", "remove_liquidity(", "collect_fee(", "collect(",
    "mint(", "approve(", "burn(", "transfer(",
    "wormhole.core", "wormhole.bridge", "mayan.forward", "portal.bridge",
)


def _self_check() -> None:
    import ast
    import io as _io
    import tokenize
    from pathlib import Path
    src = Path(__file__).read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        raise SystemExit(f"research_store parse error: {exc}")
    target = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "_BANNED_TOKENS_HERE":
                    target = node
                    break
            if target is not None:
                break
    if target is None:
        raise SystemExit("BANNED_TOKENS_HERE assignment missing")
    lines = src.splitlines(keepends=True)
    s_l, s_c = target.lineno - 1, target.col_offset
    e_l, e_c = target.end_lineno - 1, target.end_col_offset
    if e_l >= len(lines):
        e_l = len(lines) - 1
        e_c = len(lines[e_l])
    pre = "".join(lines[:s_l]) + lines[s_l][:s_c]
    post = lines[e_l][e_c:] + "".join(lines[e_l + 1:])
    blanked = " " * (len(src) - len(pre) - len(post))
    text_minus_tuple = pre + blanked + post
    lines2 = text_minus_tuple.splitlines(keepends=True)
    try:
        tokens = list(tokenize.generate_tokens(_io.StringIO(text_minus_tuple).readline))
    except tokenize.TokenizeError as exc:
        raise SystemExit(f"research_store tokenize error: {exc}")
    for tok in tokens:
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            s_r, s_c2 = tok.start
            e_r, e_c2 = tok.end
            if s_r - 1 >= len(lines2):
                continue
            if e_r - 1 >= len(lines2):
                e_r = len(lines2)
            if s_r == e_r:
                line = lines2[s_r - 1]
                lines2[s_r - 1] = line[:s_c2] + " " * (e_c2 - s_c2) + line[e_c2:]
            else:
                first = lines2[s_r - 1]
                lines2[s_r - 1] = first[:s_c2]
                for mid in range(s_r, e_r - 1):
                    lines2[mid] = " " * len(lines2[mid])
                last = lines2[e_r - 1]
                lines2[e_r - 1] = " " * e_c2 + last[e_c2:]
    text_scannable = "".join(lines2)
    for token in _BANNED_TOKENS_HERE:
        if token in text_scannable:
            raise SystemExit(f"research_store banned token: {token!r}")


_self_check()
