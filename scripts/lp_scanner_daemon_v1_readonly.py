#!/usr/bin/env python3
"""Persistent read-only LP opportunity scanner with SQLite snapshots.

The daemon composes the existing research funnel without changing any of its
standalone CLIs:

    DefiLlama screen -> on-chain resolve -> rolling-window stability
    -> funnel vet -> NetCover gate

Only public HTTP/RPC reads are performed.  This module has no wallet, signing,
transaction construction, or broadcast capability.  A coarse universe screen
is refreshed every 15 minutes; the cached top candidates are re-evaluated every
60 seconds.  ``--once`` runs the complete funnel once for smoke tests/cron.

SQLite follows PRD v1 section 30 and adds an explicit UTC ``as_of`` to every
table.  Each scan cycle writes all three tables in one transaction so readers
never observe a half-published cycle.
"""
from __future__ import annotations

import argparse
import dataclasses
import importlib
import json
import math
import os
import signal
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_tg_alerter_v1_readonly import (  # noqa: E402
    ScannerAlertBridge,
    TelegramAlerter,
)
from scripts.lp_rpc_pool_v1_readonly import RpcPoolExhaustedError  # noqa: E402

DEFAULT_DB_PATH = REPO_ROOT / "reports/lp_scanner/scanner.db"
DEFAULT_COARSE_INTERVAL_SECS = 15 * 60
DEFAULT_TOP_INTERVAL_SECS = 60
VALID_MARKET_SESSIONS = {
    "REGULAR",
    "EXTENDED",
    "OVERNIGHT",
    "PRIMARY_CLOSED",
    "HALTED",
}

# Public column contracts. ``id`` is deliberately omitted: it is an internal
# SQLite surrogate and not part of the PRD snapshot payload.
POOL_SNAPSHOT_COLUMNS = (
    "as_of",
    "chain",
    "project",
    "pool",
    "symbol",
    "tvl_usd",
    "volume_usd_1d",
    "fee_apr_pct",
    "reward_apr_pct",
    "price",
    "liquidity",
    "active_liquidity",
    "range_pct",
    "reference_price",
    "basis_bps",
    "source",
)
OPPORTUNITY_SCORE_COLUMNS = (
    "as_of",
    "pool",
    "symbol",
    "fee_ev_usd",
    "reward_ev_usd",
    "il_ev_usd",
    "lvr_ev_usd",
    "risk_usd",
    "expected_net_yield_usd",
    "expected_net_yield_pct",
    "netcover_ratio",
    "accepted",
    "rejection_reason",
    "score_json",
    "source",
)
MARKET_SESSION_COLUMNS = (
    "as_of",
    "instrument_id",
    "pool",
    "market_session",
    "source_timestamp",
    "reference_price",
    "basis_bps",
    "redemption_status",
    "source",
)


_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS pool_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    as_of TEXT NOT NULL,
    chain TEXT,
    project TEXT,
    pool TEXT NOT NULL,
    symbol TEXT,
    tvl_usd REAL,
    volume_usd_1d REAL,
    fee_apr_pct REAL,
    reward_apr_pct REAL,
    price REAL,
    liquidity REAL,
    active_liquidity REAL,
    range_pct REAL,
    reference_price REAL,
    basis_bps REAL,
    source TEXT NOT NULL,
    UNIQUE(as_of, pool)
);

CREATE INDEX IF NOT EXISTS idx_pool_snapshots_pool_as_of
    ON pool_snapshots(pool, as_of DESC);

CREATE TABLE IF NOT EXISTS opportunity_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    as_of TEXT NOT NULL,
    pool TEXT NOT NULL,
    symbol TEXT,
    fee_ev_usd REAL,
    reward_ev_usd REAL,
    il_ev_usd REAL,
    lvr_ev_usd REAL,
    risk_usd REAL,
    expected_net_yield_usd REAL,
    expected_net_yield_pct REAL,
    netcover_ratio REAL,
    accepted INTEGER NOT NULL CHECK (accepted IN (0, 1)),
    rejection_reason TEXT,
    score_json TEXT NOT NULL,
    source TEXT NOT NULL,
    UNIQUE(as_of, pool)
);

CREATE INDEX IF NOT EXISTS idx_opportunity_scores_as_of_accepted
    ON opportunity_scores(as_of DESC, accepted);

CREATE TABLE IF NOT EXISTS market_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    as_of TEXT NOT NULL,
    instrument_id TEXT NOT NULL,
    pool TEXT NOT NULL DEFAULT '',
    market_session TEXT NOT NULL CHECK (
        market_session IN ('REGULAR', 'EXTENDED', 'OVERNIGHT',
                           'PRIMARY_CLOSED', 'HALTED')
    ),
    source_timestamp TEXT,
    reference_price REAL,
    basis_bps REAL,
    redemption_status TEXT,
    source TEXT NOT NULL,
    UNIQUE(as_of, instrument_id, pool)
);

CREATE INDEX IF NOT EXISTS idx_market_sessions_instrument_as_of
    ON market_sessions(instrument_id, as_of DESC);
"""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_of_text(value: datetime | str | None) -> str:
    if value is None:
        value = _utc_now()
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        parsed = value
    if parsed.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat()


def _finite_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _first(rec: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in rec and rec[key] is not None:
            return rec[key]
    return None


def _pool_identity(rec: Mapping[str, Any]) -> str:
    value = _first(rec, "resolved_pool", "pool", "pool_address")
    if value:
        return str(value).lower()
    llama_id = rec.get("llama_pool_id")
    if llama_id:
        return "llama:" + str(llama_id)
    instrument = rec.get("instrument_id")
    if instrument:
        return "instrument:" + str(instrument)
    symbol = rec.get("symbol")
    if symbol:
        return "unresolved:" + str(symbol)
    raise ValueError("scanner record has no pool, llama_pool_id, instrument_id, or symbol")


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return value


def _explain_rejection(rec: Mapping[str, Any], accepted: bool) -> Optional[str]:
    if accepted:
        return None
    explicit = _first(rec, "rejection_reason", "gate_reason", "error")
    if explicit:
        return str(explicit)
    gates = rec.get("gates")
    if isinstance(gates, Mapping):
        failed = sorted(str(key) for key, passed in gates.items() if not bool(passed))
        if failed:
            return "failed gates: " + ", ".join(failed)
    if not rec.get("vetted", False):
        return "funnel vet rejected"
    return "NetCover gate rejected"


def _snapshot_row(rec: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "chain": _first(rec, "chain", "network"),
        "project": _first(rec, "project", "dex"),
        "pool": _pool_identity(rec),
        "symbol": rec.get("symbol"),
        "tvl_usd": _finite_float(_first(rec, "tvl_usd", "tvlUsd", "tvl")),
        "volume_usd_1d": _finite_float(
            _first(rec, "volume_usd_1d", "volumeUsd1d", "volume_24h_usd")
        ),
        "fee_apr_pct": _finite_float(
            _first(rec, "fee_apr_pct", "fee_apr_onchain", "apyBase")
        ),
        "reward_apr_pct": _finite_float(
            _first(rec, "reward_apr_pct", "reward_apr", "apyReward")
        ),
        "price": _finite_float(_first(rec, "price", "current_price", "pool_price")),
        "liquidity": _finite_float(_first(rec, "liquidity", "liquidity_usd")),
        "active_liquidity": _finite_float(
            _first(rec, "active_liquidity", "active_liquidity_usd")
        ),
        "range_pct": _finite_float(_first(rec, "range_pct", "range")),
        "reference_price": _finite_float(_first(rec, "reference_price", "anchor_price")),
        "basis_bps": _finite_float(_first(rec, "basis_bps", "basis")),
        "source": str(_first(rec, "source", "project") or "lp_scanner_v1"),
    }


def _score_row(rec: Mapping[str, Any]) -> Dict[str, Any]:
    vetted = bool(rec.get("vetted", False))
    netcover_pass = bool(
        _first(rec, "netcover_pass", "net_cover_pass", "netcover_ok", "accepted")
    )
    accepted = vetted and netcover_pass
    return {
        "pool": _pool_identity(rec),
        "symbol": rec.get("symbol"),
        "fee_ev_usd": _finite_float(_first(rec, "fee_ev_usd", "fee_ev", "FeeEV")),
        "reward_ev_usd": _finite_float(
            _first(rec, "reward_ev_usd", "reward_ev", "RewardEV")
        ),
        "il_ev_usd": _finite_float(_first(rec, "il_ev_usd", "il_ev", "IL_EV")),
        "lvr_ev_usd": _finite_float(_first(rec, "lvr_ev_usd", "lvr_ev", "LVR_EV")),
        "risk_usd": _finite_float(_first(rec, "risk_usd", "risk", "Risk")),
        "expected_net_yield_usd": _finite_float(
            _first(rec, "expected_net_yield_usd", "expected_net_yield", "ExpectedNetYield")
        ),
        "expected_net_yield_pct": _finite_float(rec.get("expected_net_yield_pct")),
        "netcover_ratio": _finite_float(
            _first(rec, "netcover_ratio", "net_cover_ratio", "NetCover")
        ),
        "accepted": accepted,
        "rejection_reason": _explain_rejection(rec, accepted),
        "score_json": json.dumps(_json_safe(dict(rec)), sort_keys=True, separators=(",", ":")),
        "source": str(_first(rec, "source", "project") or "lp_scanner_v1"),
    }


def _session_row(rec: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    session = rec.get("market_session")
    if session is None:
        return None
    session = str(session).upper()
    if session not in VALID_MARKET_SESSIONS:
        raise ValueError(f"invalid market_session: {session}")
    instrument = _first(rec, "instrument_id", "symbol")
    if not instrument:
        raise ValueError("market_session record requires instrument_id or symbol")
    return {
        "instrument_id": str(instrument),
        "pool": _pool_identity(rec),
        "market_session": session,
        "source_timestamp": _first(rec, "source_timestamp", "timestamp"),
        "reference_price": _finite_float(_first(rec, "reference_price", "anchor_price")),
        "basis_bps": _finite_float(_first(rec, "basis_bps", "basis")),
        "redemption_status": rec.get("redemption_status"),
        "source": str(_first(rec, "source", "project") or "lp_scanner_v1"),
    }


class ScannerStore:
    """Small, process-safe SQLite publisher for scanner cycles."""

    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def initialize_schema(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    @staticmethod
    def _insert_rows(
        connection: sqlite3.Connection,
        table: str,
        columns: Sequence[str],
        as_of: str,
        rows: Sequence[Mapping[str, Any]],
    ) -> None:
        if not rows:
            return
        payload_columns = [column for column in columns if column != "as_of"]
        sql_columns = ["as_of", *payload_columns]
        placeholders = ",".join("?" for _ in sql_columns)
        sql = (
            f"INSERT OR REPLACE INTO {table} ({','.join(sql_columns)}) "
            f"VALUES ({placeholders})"
        )
        values = []
        for row in rows:
            value_row = [as_of]
            for column in payload_columns:
                value = row.get(column)
                if column == "accepted":
                    value = int(bool(value))
                elif table == "opportunity_scores" and column == "score_json" and value is None:
                    value = json.dumps(
                        _json_safe(dict(row)), sort_keys=True, separators=(",", ":")
                    )
                value_row.append(value)
            values.append(value_row)
        connection.executemany(sql, values)

    def write_cycle(
        self,
        as_of: datetime | str,
        *,
        pool_snapshots: Sequence[Mapping[str, Any]],
        opportunity_scores: Sequence[Mapping[str, Any]],
        market_sessions: Sequence[Mapping[str, Any]],
    ) -> None:
        as_of_text = _as_of_text(as_of)
        self.initialize_schema()
        # Validate before INSERT.  The transaction below still protects against
        # constraint/IO failures after validation.
        for row in market_sessions:
            session = str(row.get("market_session") or "").upper()
            if session not in VALID_MARKET_SESSIONS:
                raise ValueError(f"invalid market_session: {session}")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._insert_rows(
                    connection,
                    "pool_snapshots",
                    POOL_SNAPSHOT_COLUMNS,
                    as_of_text,
                    pool_snapshots,
                )
                self._insert_rows(
                    connection,
                    "opportunity_scores",
                    OPPORTUNITY_SCORE_COLUMNS,
                    as_of_text,
                    opportunity_scores,
                )
                self._insert_rows(
                    connection,
                    "market_sessions",
                    MARKET_SESSION_COLUMNS,
                    as_of_text,
                    market_sessions,
                )
            except Exception:
                connection.rollback()
                raise
            else:
                connection.commit()


@dataclasses.dataclass
class ScreenBatch:
    all_records: List[Dict[str, Any]]
    candidates: List[Dict[str, Any]]


@dataclasses.dataclass
class CycleResult:
    as_of: str
    screened: int
    candidates: int
    resolved: int
    scored: int
    accepted: int
    market_sessions: int
    rpc_health: str = "NORMAL"


class DefaultStages:
    """Adapters around existing standalone funnel modules.

    Imports happen only when a stage runs.  That keeps pure schema/digest tools
    usable without loading RPC code and lets WP-04 arrive independently.
    """

    def __init__(
        self,
        *,
        chain: str = "Base",
        projects: Sequence[str] = ("aerodrome-slipstream", "uniswap-v3"),
        top: int = 10,
        min_tvl: float = 500_000.0,
        min_vol1d: float = 50_000.0,
        window_blocks: int = 86_400,
        window_days: float = 1.0,
        n_windows: int = 6,
        yc_min: float = 1.0,
        rpc_pool: Any = None,
    ):
        self.chain = chain
        self.projects = tuple(projects)
        self.top = int(top)
        self.min_tvl = float(min_tvl)
        self.min_vol1d = float(min_vol1d)
        self.window_blocks = int(window_blocks)
        self.window_days = float(window_days)
        self.n_windows = int(n_windows)
        self.yc_min = float(yc_min)
        if rpc_pool is None:
            rpc_module = importlib.import_module("scripts.lp_rpc_pool_v1_readonly")
            rpc_pool = rpc_module.RpcPool(self.chain.strip().lower())
        self._rpc_pool = rpc_pool

    @property
    def rpc_health(self) -> str:
        """Current health from the persistent read-only RPC pool."""
        try:
            snapshot = self._rpc_pool.health_snapshot()
            state = str(snapshot.get("state", "DEGRADED")).upper()
        except Exception:  # noqa: BLE001 - missing health evidence is degraded
            return "DEGRADED"
        return state if state in {"NORMAL", "DEGRADED"} else "DEGRADED"

    def _live_with_rotating_rpc(self, live: Mapping[str, Any]) -> Dict[str, Any]:
        """Replace legacy single-URL helpers with the verified shared RpcPool."""
        pool = self._rpc_pool
        injected = dict(live)
        raw_fetch = injected["fetch_pool_swaps"]

        def fetch_with_pool(
            address: str, from_block: int, to_block: int, dec0: int, dec1: int
        ) -> Any:
            return raw_fetch(
                address,
                from_block,
                to_block,
                dec0,
                dec1,
                rpc_call=pool.call,
            )

        injected["_rpc_with_retry"] = pool.call
        injected["fetch_pool_swaps"] = fetch_with_pool
        return injected

    def screen(self) -> ScreenBatch:
        screener = importlib.import_module("scripts.lp_universe_screener_v1_readonly")
        pools = screener.fetch_pools()
        selected = [
            pool
            for pool in pools
            if pool.get("chain") == self.chain and pool.get("project") in self.projects
        ]
        gates = {
            "min_tvl": self.min_tvl,
            "min_vol1d": self.min_vol1d,
            "suspect_reward_apr": screener.DEFAULTS["suspect_reward_apr"],
            "suspect_vol_tvl": screener.DEFAULTS["suspect_vol_tvl"],
        }
        assessed = [dict(screener.assess(pool, gates), chain=self.chain) for pool in selected]
        passed = [record for record in assessed if record.get("gate_ok")]
        ranked = sorted(
            passed,
            key=lambda record: (bool(record.get("suspect")), -float(record.get("score") or 0.0)),
        )
        return ScreenBatch(all_records=assessed, candidates=ranked[: self.top])

    def resolve(self, candidates: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        bridge = importlib.import_module("scripts.lp_pool_resolve_and_rank_v1_readonly")
        live = self._live_with_rotating_rpc(bridge._load_live_helpers())
        current_block = bridge._eth_block_number(live["_rpc_with_retry"])
        caches: Dict[str, Dict[Any, Any]] = {"pool": {}, "decimals": {}}
        records = [
            bridge.process_candidate(candidate, self.window_blocks, current_block, caches, live)
            for candidate in candidates
        ]
        return sorted(records, key=lambda record: record.get("composite_score", 0.0), reverse=True)

    def multiwindow(self, resolved: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        bridge = importlib.import_module("scripts.lp_pool_resolve_and_rank_v1_readonly")
        stability = importlib.import_module("scripts.lp_multiwindow_stability_v1_readonly")
        configs = bridge.build_policy_config(resolved)
        if not configs:
            return []
        live = self._live_with_rotating_rpc(stability._live())
        tip = int(live["_rpc_with_retry"]("eth_blockNumber", []), 16)
        results: List[Dict[str, Any]] = []
        for config in configs:
            try:
                result = stability.assess_pool(
                    live, config, self.window_days, self.n_windows, tip
                )
            except Exception as exc:
                result = {
                    "label": config.get("label", config.get("pool")),
                    "pool": config.get("pool"),
                    "tier_hint": config.get("tier_hint"),
                    "n_windows": 0,
                    "fee_cover_stability": {"enter_frac": 0.0, "stable": False},
                    "fee_cover_summary": stability.stability_summary([]),
                    "sigma_summary": stability.stability_summary([]),
                    "error": str(exc),
                    "windows": [],
                }
            results.append(result)
        return results

    def funnel(
        self,
        resolved: Sequence[Mapping[str, Any]],
        stability: Sequence[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        funnel = importlib.import_module("scripts.lp_funnel_vet_v1_readonly")
        # This is explicitly the intermediate four-gate result because the
        # task-package sequence puts the WP-04 NetCover calculation next.  The
        # public funnel API itself remains fail-closed by default; only this
        # orchestrated path opts into the intermediate state, and
        # ``_enforce_fifth_gate`` below produces the final vetted value.
        return list(
            funnel.funnel_vet(
                resolved,
                stability,
                yc_min=self.yc_min,
                allow_legacy_without_netcover=True,
            )
        )

    @staticmethod
    def _enforce_fifth_gate(
        sources: Sequence[Mapping[str, Any]], assessed: Sequence[Mapping[str, Any]]
    ) -> List[Dict[str, Any]]:
        if len(sources) != len(assessed):
            raise ValueError("NetCover adapter changed the record count")
        output: List[Dict[str, Any]] = []
        for source, result in zip(sources, assessed):
            rec = dict(result)
            passed = bool(rec.get("netcover_pass", False))
            gates = dict(source.get("gates") or {})
            gates.update(rec.get("gates") or {})
            gates["netcover_shadow"] = passed
            rec["gates"] = gates
            reason = str(rec.get("rejection_reason") or "")
            if passed:
                status = "PASS"
            elif reason.startswith("NETCOVER_INPUT_MISSING:"):
                status = "MISSING_FAIL_CLOSED"
            elif reason.startswith("NETCOVER_INPUT_INVALID:"):
                status = "INVALID_FAIL_CLOSED"
            elif rec.get("netcover_ratio") is None:
                status = "UNAVAILABLE_FAIL_CLOSED"
            else:
                status = "BELOW_SHADOW"
            rec["netcover_gate_status"] = status
            prior_vetted = bool(source.get("vetted", False))
            rec["vetted_before_netcover"] = prior_vetted
            rec["vetted"] = prior_vetted and passed
            if not rec["vetted"] and not rec.get("rejection_reason"):
                rec["rejection_reason"] = _explain_rejection(source, False)
            output.append(rec)
        return output

    @classmethod
    def _fail_closed_netcover(
        cls, records: Sequence[Mapping[str, Any]], reason: str
    ) -> List[Dict[str, Any]]:
        rejected = [
            dict(
                record,
                netcover_pass=False,
                rejection_reason=(record.get("rejection_reason") or reason),
            )
            for record in records
        ]
        return cls._enforce_fifth_gate(records, rejected)

    def netcover(self, records: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        """Invoke WP-04 through its record adapter, never duplicate its math.

        During independent Wave-2 development the module may not exist yet.
        Missing/unknown interfaces are an explicit rejection, never a silent
        fee-cover fallback.  WP-04 may expose either of the documented record
        adapter names below without creating an import cycle.
        """
        try:
            module = importlib.import_module("scripts.lp_netcover_engine_v1_readonly")
        except ImportError:
            return self._fail_closed_netcover(records, "netcover unavailable (WP-04 not installed)")

        for name in ("apply_netcover_gate", "apply_netcover_to_records"):
            adapter = getattr(module, name, None)
            if callable(adapter):
                try:
                    result = adapter(list(records))
                except Exception as exc:
                    return self._fail_closed_netcover(records, f"netcover error: {exc}")
                try:
                    return self._enforce_fifth_gate(records, [dict(record) for record in result])
                except Exception as exc:
                    return self._fail_closed_netcover(records, f"netcover adapter error: {exc}")
        return self._fail_closed_netcover(records, "netcover unavailable (record adapter missing)")


def _merge_snapshot_records(
    screened: Sequence[Mapping[str, Any]], resolved: Sequence[Mapping[str, Any]]
) -> List[Dict[str, Any]]:
    """Prefer richer resolved rows while retaining non-top coarse snapshots."""
    merged: Dict[str, Dict[str, Any]] = {}
    aliases: Dict[str, str] = {}
    for record in screened:
        rec = dict(record)
        key = str(rec.get("llama_pool_id") or _pool_identity(rec))
        merged[key] = rec
        aliases[_pool_identity(rec)] = key
    for record in resolved:
        rec = dict(record)
        key = str(rec.get("llama_pool_id") or _pool_identity(rec))
        existing = merged.get(key, {})
        merged[key] = {**existing, **rec}
        aliases[_pool_identity(merged[key])] = key
    return list(merged.values())


def _unique_sessions(records: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    unique: Dict[tuple[str, str], Dict[str, Any]] = {}
    for record in records:
        row = _session_row(record)
        if row is None:
            continue
        unique[(row["instrument_id"], row["pool"])] = row
    return list(unique.values())


class FunnelOrchestrator:
    """Owns the coarse-screen cache and publishes complete scan cycles."""

    def __init__(self, stages: Any, store: ScannerStore):
        self.stages = stages
        self.store = store
        # Establish the reader-visible contract before the first network cycle.
        # A failed first scan therefore leaves an empty, queryable database
        # rather than a path whose schema depends on network success.
        self.store.initialize_schema()
        self._screen_batch: Optional[ScreenBatch] = None

    def run_once(
        self, *, refresh_coarse: bool, as_of: datetime | str | None = None
    ) -> CycleResult:
        if refresh_coarse or self._screen_batch is None:
            batch = self.stages.screen()
            if not isinstance(batch, ScreenBatch):
                raise TypeError("screen stage must return ScreenBatch")
            self._screen_batch = batch
        batch = self._screen_batch
        assert batch is not None

        resolved = list(self.stages.resolve(batch.candidates))
        stability = list(self.stages.multiwindow(resolved))
        vetted = list(self.stages.funnel(resolved, stability))
        scored = list(self.stages.netcover(vetted))
        stamp = _as_of_text(as_of)

        snapshot_records = _merge_snapshot_records(batch.all_records, resolved)
        snapshot_rows = [_snapshot_row(record) for record in snapshot_records]
        score_rows = [_score_row(record) for record in scored]
        sessions = _unique_sessions([*batch.all_records, *resolved, *scored])
        self.store.write_cycle(
            stamp,
            pool_snapshots=snapshot_rows,
            opportunity_scores=score_rows,
            market_sessions=sessions,
        )
        return CycleResult(
            as_of=stamp,
            screened=len(batch.all_records),
            candidates=len(batch.candidates),
            resolved=len(resolved),
            scored=len(scored),
            accepted=sum(1 for row in score_rows if row["accepted"]),
            market_sessions=len(sessions),
            rpc_health=str(getattr(self.stages, "rpc_health", "NORMAL")).upper(),
        )


class ScannerDaemon:
    """Signal-aware scheduler. SIGINT/SIGTERM never interrupt a DB transaction."""

    def __init__(
        self,
        cycle: Callable[[bool], Any],
        *,
        coarse_interval_secs: float = DEFAULT_COARSE_INTERVAL_SECS,
        top_interval_secs: float = DEFAULT_TOP_INTERVAL_SECS,
        pid_file: str | os.PathLike[str] | None = None,
        on_shutdown: Optional[Callable[[], None]] = None,
        event_hook: Any = None,
        monotonic: Callable[[], float] = time.monotonic,
    ):
        if coarse_interval_secs <= 0 or top_interval_secs <= 0:
            raise ValueError("scanner intervals must be positive")
        self.cycle = cycle
        self.coarse_interval_secs = float(coarse_interval_secs)
        self.top_interval_secs = float(top_interval_secs)
        self.pid_file = Path(pid_file) if pid_file else None
        self.on_shutdown = on_shutdown
        self.event_hook = event_hook
        self.monotonic = monotonic
        self._stop = threading.Event()

    def _notify_cycle(self, result: Any) -> None:
        if self.event_hook is None:
            return
        try:
            self.event_hook.after_cycle(result)
        except Exception as exc:  # noqa: BLE001 - alerts cannot stop persistence loop
            print(
                f"[scanner] alert hook failed: {type(exc).__name__}",
                file=sys.stderr,
                flush=True,
            )

    def _notify_cycle_failure(self, exc: Exception) -> None:
        if isinstance(exc, RpcPoolExhaustedError):
            # Only endpoint exhaustion is RPC evidence strong enough to claim
            # EXIT_ONLY. The exit policy remains the sole action authority.
            self._notify_cycle(
                {"rpc_health": "EXIT_ONLY", "cycle_error": type(exc).__name__}
            )
            return
        if self.event_hook is None or not hasattr(self.event_hook, "after_cycle_error"):
            return
        try:
            self.event_hook.after_cycle_error(type(exc).__name__)
        except Exception as hook_exc:  # noqa: BLE001 - diagnostics stay best-effort
            print(
                f"[scanner] alert hook failed: {type(hook_exc).__name__}",
                file=sys.stderr,
                flush=True,
            )

    def request_stop(self, signum: int | None = None, frame: Any = None) -> None:
        del signum, frame
        self._stop.set()

    def _write_pid(self) -> None:
        if self.pid_file is None:
            return
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file.write_text(str(os.getpid()) + "\n")

    def _remove_own_pid(self) -> None:
        if self.pid_file is None or not self.pid_file.exists():
            return
        try:
            if self.pid_file.read_text().strip() == str(os.getpid()):
                self.pid_file.unlink()
        except OSError:
            pass

    def run(self, *, once: bool = False) -> int:
        previous: Dict[int, Any] = {}
        if threading.current_thread() is threading.main_thread():
            for signum in (signal.SIGINT, signal.SIGTERM):
                previous[signum] = signal.getsignal(signum)
                signal.signal(signum, self.request_stop)
        self._write_pid()
        last_coarse = self.monotonic()
        try:
            if not self._stop.is_set():
                try:
                    result = self.cycle(True)
                except Exception as exc:
                    self._notify_cycle_failure(exc)
                    raise
                self._notify_cycle(result)
                last_coarse = self.monotonic()
            if once:
                return 0
            while not self._stop.wait(self.top_interval_secs):
                now = self.monotonic()
                refresh_coarse = now - last_coarse >= self.coarse_interval_secs
                try:
                    result = self.cycle(refresh_coarse)
                    self._notify_cycle(result)
                except Exception as exc:
                    self._notify_cycle_failure(exc)
                    print(f"[scanner] cycle failed: {exc}", file=sys.stderr, flush=True)
                if refresh_coarse:
                    last_coarse = now
            return 0
        finally:
            if self.on_shutdown is not None:
                self.on_shutdown()
            self._remove_own_pid()
            for signum, handler in previous.items():
                signal.signal(signum, handler)


def _positive(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Persistent read-only LP scanner (screen->resolve->stability->vet->NetCover)"
    )
    parser.add_argument("--once", action="store_true", help="run one full funnel then exit")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--pid-file", default=None)
    parser.add_argument("--coarse-interval-secs", type=_positive, default=DEFAULT_COARSE_INTERVAL_SECS)
    parser.add_argument("--top-interval-secs", type=_positive, default=DEFAULT_TOP_INTERVAL_SECS)
    parser.add_argument("--chain", default="Base")
    parser.add_argument(
        "--projects", nargs="+", default=["aerodrome-slipstream", "uniswap-v3"]
    )
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--min-tvl", type=float, default=500_000.0)
    parser.add_argument("--min-vol1d", type=float, default=50_000.0)
    parser.add_argument("--window-blocks", type=int, default=86_400)
    parser.add_argument("--window-days", type=float, default=1.0)
    parser.add_argument("--n-windows", type=int, default=6)
    parser.add_argument("--yc-min", type=float, default=1.0)
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    stages: Any = None,
    now: Callable[[], datetime] = _utc_now,
    alerter: Any = None,
    digest_provider: Optional[Callable[[str], str]] = None,
) -> int:
    args = _parser().parse_args(argv)
    if args.top <= 0 or args.window_blocks <= 0 or args.window_days <= 0 or args.n_windows <= 0:
        _parser().error("top/window parameters must be positive")
    store = ScannerStore(args.db)
    selected_stages = stages or DefaultStages(
        chain=args.chain,
        projects=args.projects,
        top=args.top,
        min_tvl=args.min_tvl,
        min_vol1d=args.min_vol1d,
        window_blocks=args.window_blocks,
        window_days=args.window_days,
        n_windows=args.n_windows,
        yc_min=args.yc_min,
    )
    orchestrator = FunnelOrchestrator(selected_stages, store)

    selected_alerter = TelegramAlerter.from_env() if alerter is None else alerter
    if digest_provider is None:
        def digest_provider(day: str) -> str:
            from scripts.lp_report_digest_v1_readonly import (
                DEFAULT_HEARTBEAT,
                build_digest_markdown,
                summarize_heartbeat,
                summarize_scanner_db,
            )

            return build_digest_markdown(
                summarize_heartbeat(DEFAULT_HEARTBEAT, day=day),
                summarize_scanner_db(args.db),
                generated_at=now().isoformat(),
            )
    event_hook = ScannerAlertBridge(
        selected_alerter,
        digest_provider=digest_provider,
        utc_now=now,
    )

    def cycle(refresh_coarse: bool) -> CycleResult:
        result = orchestrator.run_once(refresh_coarse=refresh_coarse, as_of=now())
        print(
            f"[scanner] as_of={result.as_of} screened={result.screened} "
            f"top={result.candidates} resolved={result.resolved} scored={result.scored} "
            f"accepted={result.accepted} sessions={result.market_sessions}",
            flush=True,
        )
        return result

    pid_file = args.pid_file or str(Path(args.db).with_name("scanner.pid"))
    daemon = ScannerDaemon(
        cycle,
        coarse_interval_secs=args.coarse_interval_secs,
        top_interval_secs=args.top_interval_secs,
        pid_file=pid_file,
        event_hook=event_hook,
    )
    try:
        return daemon.run(once=args.once)
    except Exception as exc:
        print(f"[scanner] fatal: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
