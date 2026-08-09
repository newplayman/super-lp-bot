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
table.  Each scan cycle writes the three operational tables plus reward
observations in one transaction so readers never observe a half-published
cycle.
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
from scripts.lp_rejection_reason_v1_readonly import explain_rejection  # noqa: E402
from scripts.lp_reward_persistence_v1_readonly import (  # noqa: E402
    MIN_REWARD_OBSERVATION_HOURS,
    reward_high_duration_from_observations,
)
from scripts.lp_capital_tiers_v1_readonly import (  # noqa: E402
    CAPITAL_TIERS,
    CAPITAL_TIER_CONFIGURED_MAX_USD,
    DEFAULT_CAPITAL_TIER,
    coarse_tvl_min_usd,
    normalize_capital_tier,
)

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

SOLANA_TACTICAL_PROJECTS = frozenset({"orca-dex", "raydium-amm"})
SOLANA_POOL_MAPPING_BLOCK_REASON = "authoritative_pool_mapping_missing"

BASE_USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
BASE_AERO = "0x940181a94a35a4569e4529a3cdfb74e38fd98631"
BASE_WETH = "0x4200000000000000000000000000000000000006"
BASE_CBBTC = "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf"
BASE_AERODROME_INITIAL_FACTORY = "0x5e7bb104d84c7cb9b682aac2f3d509f5f406809a"
BASE_AERODROME_GAUGE_CAPS_FACTORY = "0xade65c38cd4849adba595a4323a8c7ddfe89716a"
BASE_AERODROME_GAUGES_V3_FACTORY = "0xf8f2eb4940cfe7d13603dddd87f123820fc061ef"
# Fixed before evaluation from the official Initial Slipstream deployment.
# Each route had positive live liquidity during R1b's preregistration probe;
# runtime still validates factory membership, identity and every state word.
BASE_AERO_USDC_REWARD_ROUTES = (
    {"route_id": "aero_usdc_initial_tick50", "pool": "0x9ed0f0f21b83d1595147dc6b32b5607647bdcd56", "tick_spacing": 50, "factory": BASE_AERODROME_INITIAL_FACTORY},
    {"route_id": "aero_usdc_initial_tick100", "pool": "0xa4fdd479eda160671636e2ecf8f993cbf86258a8", "tick_spacing": 100, "factory": BASE_AERODROME_INITIAL_FACTORY},
    {"route_id": "aero_usdc_initial_tick200", "pool": "0xccd9cc53b63662088c738b8bc06e9078fb8d9ad4", "tick_spacing": 200, "factory": BASE_AERODROME_INITIAL_FACTORY},
    {"route_id": "aero_usdc_initial_tick2000", "pool": "0xbe00ff35af70e8415d0eb605a286d8a45466a4c1", "tick_spacing": 2000, "factory": BASE_AERODROME_INITIAL_FACTORY},
)
# These official pools were measured with zero active liquidity during R1b and
# are therefore not executable conversion routes.  They remain mandatory
# watchlist probes: a read/identity failure, or becoming executable, closes the
# whole evidence package until the frozen allowlist is reviewed.  This avoids
# silently ignoring a newly viable route that might have a higher cost.
BASE_AERO_USDC_ZERO_LIQUIDITY_WATCHLIST = (
    {"route_id": "aero_usdc_gauge_caps_tick1", "pool": "0x3b90dcfdb23b0a8484bf6a4767578861fbe1b21b", "tick_spacing": 1, "factory": BASE_AERODROME_GAUGE_CAPS_FACTORY},
    {"route_id": "aero_usdc_gauges_v3_tick10", "pool": "0x12619a0f9d0c7f58528a77e45dd315ec49b875ef", "tick_spacing": 10, "factory": BASE_AERODROME_GAUGES_V3_FACTORY},
)
BASE_USD_ANCHOR_ROUTES = (
    {"route_id": "weth_usdc_initial_tick50", "pool": "0xaad23a67f2ac693abbe543489aeb3f24f561d517", "tick_spacing": 50, "factory": BASE_AERODROME_INITIAL_FACTORY, "token_a": BASE_WETH, "token_b": BASE_USDC},
    {"route_id": "weth_cbbtc_initial_tick10", "pool": "0xffa192f04b1e5f9f5124fb40a96407564492ed20", "tick_spacing": 10, "factory": BASE_AERODROME_INITIAL_FACTORY, "token_a": BASE_WETH, "token_b": BASE_CBBTC},
)

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
REWARD_OBSERVATION_COLUMNS = (
    "as_of",
    "pool",
    "chain",
    "apy_reward",
    "apy_base",
    "tvl_usd",
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

CREATE TABLE IF NOT EXISTS reward_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    as_of TEXT NOT NULL,
    pool TEXT NOT NULL,
    chain TEXT NOT NULL,
    apy_reward REAL,
    apy_base REAL,
    tvl_usd REAL,
    source TEXT NOT NULL,
    UNIQUE(as_of, pool, chain, source)
);

CREATE INDEX IF NOT EXISTS idx_reward_observations_pool_chain_as_of
    ON reward_observations(pool, chain, as_of DESC);
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
    return explain_rejection(rec, accepted)


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


def _reward_observation_row(rec: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """Build one aggregator observation keyed by stable DefiLlama identity."""
    llama_pool_id = rec.get("llama_pool_id")
    chain = _first(rec, "chain", "network")
    if not llama_pool_id or not chain:
        return None
    return {
        "pool": str(llama_pool_id),
        "chain": str(chain),
        "apy_reward": _finite_float(_first(rec, "apyReward", "reward_apr")),
        "apy_base": _finite_float(_first(rec, "apyBase", "fee_apr_7d")),
        "tvl_usd": _finite_float(_first(rec, "tvlUsd", "tvl_usd", "tvl")),
        "source": "defillama:/pools",
    }


def _score_row(rec: Mapping[str, Any]) -> Dict[str, Any]:
    vetted = bool(rec.get("vetted", False))
    netcover_pass = bool(
        _first(rec, "netcover_pass", "net_cover_pass", "netcover_ok", "accepted")
    )
    # Defense in depth: a malicious/stale adapter cannot persist acceptance by
    # asserting both terminal booleans while carrying an explicit entry veto.
    entry_allowed = rec.get("entry_eligible") is not False
    position_cap_allowed = rec.get("position_cap_pass") is True
    accepted = vetted and netcover_pass and entry_allowed and position_cap_allowed
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

    def reward_observation_evidence(
        self,
        identities: Sequence[tuple[str, str]],
        *,
        cutoff: datetime | str,
    ) -> Dict[tuple[str, str], Dict[str, Any]]:
        """Return contiguous prior-cycle evidence for requested llama identities."""
        wanted = {(str(pool), str(chain).lower()) for pool, chain in identities if pool and chain}
        if not wanted:
            return {}
        self.initialize_schema()
        cutoff_text = _as_of_text(cutoff)
        pools = sorted({pool for pool, _ in wanted})
        placeholders = ",".join("?" for _ in pools)
        query = (
            "SELECT as_of,pool,chain,apy_reward FROM reward_observations "
            f"WHERE as_of < ? AND pool IN ({placeholders}) "
            "ORDER BY pool,chain,as_of"
        )
        with self._connect() as connection:
            rows = connection.execute(query, (cutoff_text, *pools)).fetchall()
        grouped: Dict[tuple[str, str], List[Dict[str, Any]]] = {}
        for as_of, pool, chain, apy_reward in rows:
            key = (str(pool), str(chain).lower())
            if key not in wanted:
                continue
            grouped.setdefault(key, []).append({
                "as_of": as_of,
                "apy_reward": apy_reward,
            })
        return {
            key: reward_high_duration_from_observations(values, cutoff=cutoff_text)
            for key, values in grouped.items()
        }

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
        reward_observations: Sequence[Mapping[str, Any]] = (),
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
                self._insert_rows(
                    connection,
                    "reward_observations",
                    REWARD_OBSERVATION_COLUMNS,
                    as_of_text,
                    reward_observations,
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
        top: int = 30,
        capital_tier: str = DEFAULT_CAPITAL_TIER,
        min_tvl: Optional[float] = None,
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
        self.capital_tier = normalize_capital_tier(capital_tier)
        self.min_tvl = coarse_tvl_min_usd(self.capital_tier, min_tvl)
        self.tier_configured_max_usd = CAPITAL_TIER_CONFIGURED_MAX_USD[
            self.capital_tier
        ]
        self.min_vol1d = float(min_vol1d)
        self.window_blocks = int(window_blocks)
        self.window_days = float(window_days)
        self.n_windows = int(n_windows)
        self.yc_min = float(yc_min)
        if rpc_pool is None:
            rpc_module = importlib.import_module("scripts.lp_rpc_pool_v1_readonly")
            rpc_pool = rpc_module.RpcPool(self.chain.strip().lower())
        self._rpc_pool = rpc_pool
        self._base_cross_pool_measurements: Optional[Dict[str, Any]] = None

    def _is_solana(self) -> bool:
        return self.chain.strip().lower() == "solana"

    @staticmethod
    def _solana_mapping_blocked_record(source: Mapping[str, Any]) -> Dict[str, Any]:
        """Preserve a Solana lead without guessing a DefiLlama UUID's account.

        DefiLlama's ``pool`` value is an aggregator identity, not an
        authoritative Orca/Raydium account address.  Until a protocol-owned
        mapping adapter exists, the only honest production result is a
        candidate-level fail-closed row.  In particular, no symbol matching,
        EVM resolver, prefilled horizon, or generic Solana account guess is
        allowed to cross this boundary.
        """
        record = dict(source)
        project = str(record.get("project") or "").lower()
        if project in SOLANA_TACTICAL_PROJECTS:
            record["profile"] = "TACTICAL"
            record["netcover_profile"] = "TACTICAL"
        record.update({
            "resolved_pool": None,
            "pool": None,
            "resolve_status": "BLOCKED",
            "status": "FAIL_CLOSED",
            "mapping_status": "BLOCKED_PENDING_AUTHORITATIVE_POOL_MAPPING",
            "blocked_reason": SOLANA_POOL_MAPPING_BLOCK_REASON,
            "root_cause": SOLANA_POOL_MAPPING_BLOCK_REASON,
            "rejection_reason": SOLANA_POOL_MAPPING_BLOCK_REASON,
            "entry_eligible": False,
            "entry_block_reasons": [SOLANA_POOL_MAPPING_BLOCK_REASON],
            "holding_horizon_er_policy_hours": None,
            "holding_horizon_hours": None,
            "holding_horizon_days": None,
            "holding_horizon_source": None,
            "vetted": False,
            "netcover_pass": False,
            "composite_score": 0.0,
        })
        return record

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
            screener.strip_untrusted_reward_evidence(pool)
            for pool in pools
            if pool.get("chain") == self.chain and pool.get("project") in self.projects
        ]
        gates = {
            "min_tvl": self.min_tvl,
            "min_vol1d": self.min_vol1d,
            "suspect_reward_apr": screener.DEFAULTS["suspect_reward_apr"],
            "suspect_vol_tvl": screener.DEFAULTS["suspect_vol_tvl"],
        }
        assessed = []
        for pool in selected:
            record = dict(screener.assess(pool, gates), chain=self.chain)
            record.update({
                "capital_tier": self.capital_tier,
                "coarse_tvl_min_usd": self.min_tvl,
                "tier_configured_max_usd": self.tier_configured_max_usd,
            })
            if (
                self._is_solana()
                and str(record.get("project") or "").lower()
                in SOLANA_TACTICAL_PROJECTS
            ):
                record["profile"] = "TACTICAL"
                record["netcover_profile"] = "TACTICAL"
            assessed.append(record)
        rerank = importlib.import_module("scripts.lp_funnel_rerank_v1_readonly")
        assessed = rerank.enrich_with_proxy(assessed)
        passed = [record for record in assessed if record.get("gate_ok")]
        ranked = rerank.rank_stage1(
            passed,
            correlation_evidence=rerank.PRODUCTION_EVIDENCE,
        )
        return ScreenBatch(all_records=assessed, candidates=ranked[: self.top])

    def resolve(self, candidates: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        if self._is_solana():
            return [
                self._solana_mapping_blocked_record(candidate)
                for candidate in candidates
            ]
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
        if self._is_solana():
            # No authoritative account means there is no pool on which to read
            # slots/swaps.  Returning no evidence is intentional and avoids all
            # EVM helpers as well as fabricated Solana stability windows.
            return []
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
        if self._is_solana():
            return [self._solana_mapping_blocked_record(record) for record in resolved]
        funnel = importlib.import_module("scripts.lp_funnel_vet_v1_readonly")
        # This is explicitly the intermediate four-gate result because the
        # task-package sequence puts the WP-04 NetCover calculation next.  The
        # public funnel API itself remains fail-closed by default; only this
        # orchestrated path opts into the intermediate state, and
        # ``_enforce_fifth_gate`` below produces the final vetted value.
        records = list(
            funnel.funnel_vet(
                resolved,
                stability,
                yc_min=self.yc_min,
                allow_legacy_without_netcover=True,
            )
        )
        # W6/R6: carry the already-measured latest pair sigma/ER into the input
        # assembler and translate its regime through the record's own profile.
        # Missing measurements/profile remain absent; no horizon is guessed.
        stability_by_pool = {
            _pool_identity(item): item for item in stability
            if item.get("pool") or item.get("resolved_pool")
        }
        policy_module = importlib.import_module("scripts.lp_tier_range_policy_v1_readonly")
        inputs_module = importlib.import_module("scripts.lp_netcover_inputs_v1_readonly")
        for record in records:
            # H/drag are scanner-internal policy outputs.  Clear every upstream
            # alias before reading measured sigma/ER so missing evidence or a
            # cross-profile policy cannot preserve a candidate-prefilled H.
            for key in (
                "holding_horizon_hours",
                "holding_horizon_days",
                "holding_horizon_source",
                "holding_horizon_er_policy_hours",
                "profile_horizon_hours",
                "profile_horizon_days",
                "er_horizon_hours",
                "er_horizon_days",
                "drag_apr_pct",
                "drag_apr_max_pct",
                "high_drag_flag",
            ):
                record.pop(key, None)
            evidence = stability_by_pool.get(_pool_identity(record), {})
            windows = evidence.get("windows") or ()
            latest = windows[0] if windows and isinstance(windows[0], Mapping) else {}
            sigma = _finite_float(latest.get("sigma_daily"))
            er = _finite_float(latest.get("er"))
            if sigma is None or er is None:
                continue
            policy = policy_module.build_policy(
                sigma, er, tier_hint=str(record.get("tier") or "")
            )
            record["sigma_pair"] = sigma
            record["er"] = er
            profile = inputs_module.profile_kind(record)
            er_hours = {
                "PASSIVE": {
                    "range-bound": 168.0,
                    "neutral": 336.0,
                    "trending": 720.0,
                },
                "TACTICAL": {
                    "range-bound": 6.0,
                    "neutral": 24.0,
                    "trending": 72.0,
                },
            }.get(profile, {}).get(policy.get("regime"))
            legal = inputs_module.PROFILE_HORIZONS_HOURS.get(profile, ())
            # 12h is intentionally not an ER base candidate; ADD-1 can select
            # it only by moving upward from the tactical 6h candidate.  The
            # same legal-set check fails closed on unknown/cross-profile H.
            if er_hours is None or er_hours not in legal:
                continue
            chain = str(record.get("chain") or record.get("network") or "").lower()
            selection = inputs_module.select_drag_adjusted_horizon(
                profile=profile,
                er_horizon_hours=er_hours,
                fee_tier=_finite_float(record.get("fee_tier")),
                gas_usd=inputs_module.HISTORICAL_GAS_USD.get(chain),
            )
            record["holding_horizon_er_policy_hours"] = er_hours
            record["holding_horizon_hours"] = selection["holding_horizon_hours"]
            record["holding_horizon_days"] = selection["holding_horizon_hours"] / 24.0
            record["holding_horizon_source"] = selection["holding_horizon_source"]
            record["drag_apr_pct"] = selection["drag_apr_pct"]
            record["drag_apr_max_pct"] = selection["drag_apr_max_pct"]
            record["high_drag_flag"] = selection["high_drag_flag"]
        return records

    def _attach_live_pool_state(self, source: Mapping[str, Any]) -> Dict[str, Any]:
        """Read slot0/liquidity through the shared read-only RPC pool for W6."""
        record = dict(source)
        if (
            _first(
                record,
                "l_active_raw",
                "active_liquidity_raw",
                "l_active_raw_historical",
                "last_swap_liquidity_raw",
            )
            is not None
            and _first(
                record,
                "sqrtPriceX96",
                "sqrt_price_x96",
                "price_usd",
                "last_swap_price_token1_per_token0",
            )
            is not None
        ):
            return record
        pool = _first(record, "resolved_pool", "pool")
        if not pool:
            return record
        try:
            slot0 = self._rpc_pool.call(
                "eth_call", [{"to": str(pool), "data": "0x3850c7bd"}, "latest"]
            )
            liquidity = self._rpc_pool.call(
                "eth_call", [{"to": str(pool), "data": "0x1a686502"}, "latest"]
            )
            slot0_text = str(slot0 or "")
            liquidity_text = str(liquidity or "")
            if slot0_text.startswith("0x") and len(slot0_text) >= 66:
                record["sqrt_price_x96"] = int(slot0_text[2:66], 16)
                record["sqrt_price_x96_source"] = "measured:pool.slot0_latest"
            if liquidity_text.startswith("0x") and len(liquidity_text) >= 66:
                record["l_active_raw"] = int(liquidity_text[2:66], 16)
                record["l_active_raw_source"] = "measured:pool.liquidity_latest"
        except Exception as exc:  # missing depth evidence must remain fail-closed
            record["netcover_depth_error"] = f"{type(exc).__name__}: {exc}"
        return record

    def _measure_preregistered_slipstream_route(
        self, spec: Mapping[str, Any], *, observed_block: int
    ) -> Dict[str, Any]:
        """Build one route exclusively from validated latest-chain state."""
        bridge = importlib.import_module("scripts.lp_pool_resolve_and_rank_v1_readonly")
        costs = importlib.import_module("scripts.lp_cost_sensitivity_v1_readonly")
        token_a = str(spec.get("token_a") or BASE_AERO).lower()
        token_b = str(spec.get("token_b") or BASE_USDC).lower()
        factory = str(spec["factory"]).lower()
        expected_pool = str(spec["pool"]).lower()
        tick_spacing = int(spec["tick_spacing"])
        block_tag = hex(int(observed_block))
        returned = set()
        for left, right in ((token_a, token_b), (token_b, token_a)):
            data = bridge.build_aerodrome_get_pool_calldata(left, right, tick_spacing)
            raw = self._rpc_pool.call(
                "eth_call", [{"to": factory, "data": data}, block_tag]
            )
            address = bridge.decode_address_word(str(raw))
            if address != bridge.ZERO_ADDRESS:
                returned.add(address)
        if returned != {expected_pool}:
            raise ValueError(
                f"factory route mismatch {spec['route_id']}: {sorted(returned)}"
            )
        code = self._rpc_pool.call("eth_getCode", [expected_pool, block_tag])
        if not isinstance(code, str) or code.lower() in {"0x", "0x0", "0x00"}:
            raise ValueError(f"route bytecode unavailable: {spec['route_id']}")

        def call_word(selector: str) -> str:
            raw = self._rpc_pool.call(
                "eth_call", [{"to": expected_pool, "data": selector}, block_tag]
            )
            text = str(raw or "")
            if not text.startswith("0x") or len(text) < 66:
                raise ValueError(f"short route state {spec['route_id']} {selector}")
            return text

        token0 = bridge.decode_address_word(call_word("0x0dfe1681"))
        token1 = bridge.decode_address_word(call_word("0xd21220a7"))
        if sorted((token0, token1)) != sorted((token_a, token_b)):
            raise ValueError(f"route token mismatch: {spec['route_id']}")
        tick = bridge.decode_uint_word(call_word("0xd0c93a7c"))
        if tick != tick_spacing:
            raise ValueError(f"route tick mismatch: {spec['route_id']}")
        decimals = []
        for token in (token0, token1):
            raw = self._rpc_pool.call(
                "eth_call", [{"to": token, "data": "0x313ce567"}, block_tag]
            )
            value = bridge.decode_uint_word(str(raw))
            if value < 0 or value > 36:
                raise ValueError(f"route decimals invalid: {spec['route_id']}")
            decimals.append(value)
        fee_raw = bridge.decode_uint_word(call_word("0xddca3f43"))
        sqrt_price_x96 = int(call_word("0x3850c7bd")[2:66], 16)
        liquidity_raw = int(call_word("0x1a686502")[2:66], 16)
        pair_price = costs.price_from_sqrt_x96(
            sqrt_price_x96, dec0=decimals[0], dec1=decimals[1]
        )
        if pair_price <= 0.0 or fee_raw < 0:
            raise ValueError(f"route price/fee invalid: {spec['route_id']}")
        return {
            "route_id": str(spec["route_id"]),
            "pool": expected_pool,
            "factory": factory,
            "factory_registry_source": (
                "official:https://github.com/aerodrome-finance/slipstream#deployments"
            ),
            "tick_spacing": tick,
            "token0": token0,
            "token1": token1,
            "dec0": decimals[0],
            "dec1": decimals[1],
            "fee_tier": fee_raw / 1_000_000.0,
            "sqrt_price_x96": sqrt_price_x96,
            "pair_price_token1_per_token0": pair_price,
            "l_active_raw": liquidity_raw,
            "executable": liquidity_raw > 0,
            "observed_block": observed_block,
            "measurement_source": "measured:scanner_internal_rpc:fixed_block_eth_call",
        }

    def _read_base_cross_pool_measurements(self) -> Dict[str, Any]:
        """Measure the fixed route registry once per scanner process/cycle set."""
        if self._base_cross_pool_measurements is not None:
            return self._base_cross_pool_measurements
        evidence: Dict[str, Any] = {
            "complete": False,
            "anchors": [],
            "aero_reward_routes": [],
            "aero_reward_route_watchlist": [],
            "errors": [],
        }
        try:
            tip_raw = self._rpc_pool.call("eth_blockNumber", [])
            tip = int(str(tip_raw), 16)
            for spec in BASE_USD_ANCHOR_ROUTES:
                route = self._measure_preregistered_slipstream_route(
                    spec, observed_block=tip
                )
                if route.get("executable") is not True:
                    raise ValueError(f"anchor route not executable: {route['route_id']}")
                evidence["anchors"].append(route)
            for spec in BASE_AERO_USDC_REWARD_ROUTES:
                route = self._measure_preregistered_slipstream_route(
                    spec, observed_block=tip
                )
                if route.get("executable") is not True:
                    raise ValueError(f"reward route not executable: {route['route_id']}")
                evidence["aero_reward_routes"].append(route)
            for spec in BASE_AERO_USDC_ZERO_LIQUIDITY_WATCHLIST:
                route = self._measure_preregistered_slipstream_route(
                    spec, observed_block=tip
                )
                if route.get("executable") is not False:
                    evidence["permanent_fail_closed_reason"] = (
                        "preregistered_watchlist_became_executable"
                    )
                    raise ValueError(
                        f"watched route became executable; allowlist review required: {route['route_id']}"
                    )
                evidence["aero_reward_route_watchlist"].append(route)
            evidence["observed_block"] = tip
            evidence["complete"] = True
        except Exception as exc:
            evidence["errors"].append(f"{type(exc).__name__}: {exc}")
        self._base_cross_pool_measurements = evidence
        return evidence

    def _scanner_cross_pool_evidence(self, record: Mapping[str, Any]) -> Dict[str, Any]:
        measured = self._read_base_cross_pool_measurements()
        output: Dict[str, Any] = {
            "complete": bool(measured.get("complete")),
            "errors": list(measured.get("errors") or ()),
            "observed_block": measured.get("observed_block"),
            "permanent_fail_closed_reason": measured.get(
                "permanent_fail_closed_reason"
            ),
        }
        if not output["complete"]:
            return output
        anchors = {item["route_id"]: item for item in measured["anchors"]}
        weth_route = anchors["weth_usdc_initial_tick50"]
        cbbtc_route = anchors["weth_cbbtc_initial_tick10"]

        def usd_per_token(route: Mapping[str, Any], token: str) -> float:
            pair = float(route["pair_price_token1_per_token0"])
            if route["token0"] == token and route["token1"] == BASE_USDC:
                return pair
            if route["token1"] == token and route["token0"] == BASE_USDC:
                return 1.0 / pair
            raise ValueError(f"route does not quote {token} in USDC")

        weth_usd = usd_per_token(weth_route, BASE_WETH)
        cbbtc_per_weth = float(cbbtc_route["pair_price_token1_per_token0"])
        if cbbtc_route["token0"] == BASE_CBBTC:
            cbbtc_per_weth = 1.0 / cbbtc_per_weth
        cbbtc_usd = weth_usd / cbbtc_per_weth
        token0 = str(record.get("token0") or "").lower()
        token1 = str(record.get("token1") or "").lower()
        pair = _finite_float(record.get("last_swap_price_token1_per_token0"))
        token1_usd = None
        quote_source = None
        if token1 == BASE_CBBTC:
            token1_usd = cbbtc_usd
            quote_source = "measured:weth_usdc_anchor_plus_weth_cbbtc_route"
        elif token1 == BASE_WETH:
            token1_usd = weth_usd
            quote_source = "measured:weth_usdc_anchor"
        elif token0 == BASE_WETH and pair is not None and pair > 0.0:
            token1_usd = weth_usd / pair
            quote_source = "measured:weth_usdc_anchor_div_main_pair_price"
        if token1_usd is not None and token1_usd > 0.0:
            output["token1_usd"] = token1_usd
            output["token1_usd_source"] = quote_source
            output["usd_anchor_routes"] = list(measured["anchors"])

        reward_tokens = record.get("rewardTokens") or record.get("reward_tokens") or ()
        if isinstance(reward_tokens, str):
            reward_tokens = (reward_tokens,)
        if {str(token).lower() for token in reward_tokens} == {BASE_AERO}:
            output["aero_reward_routes"] = list(measured["aero_reward_routes"])
            output["aero_reward_route_watchlist"] = list(
                measured["aero_reward_route_watchlist"]
            )
        return output

    @staticmethod
    def _enforce_fifth_gate(
        sources: Sequence[Mapping[str, Any]], assessed: Sequence[Mapping[str, Any]]
    ) -> List[Dict[str, Any]]:
        if len(sources) != len(assessed):
            raise ValueError("NetCover adapter changed the record count")
        output: List[Dict[str, Any]] = []
        for source, result in zip(sources, assessed):
            rec = dict(result)
            permanent_reason = rec.get("permanent_fail_closed_reason") or source.get(
                "permanent_fail_closed_reason"
            )
            netcover_passed = bool(rec.get("netcover_pass", False)) and not permanent_reason
            position_cap_passed = rec.get("position_cap_pass") is True
            passed = netcover_passed and position_cap_passed
            if permanent_reason:
                rec["permanent_fail_closed_reason"] = str(permanent_reason)
                rec["netcover_pass"] = False
                rec["netcover"] = None
                rec["netcover_ratio"] = None
                rec["rejection_reason"] = f"PERMANENT_FAIL_CLOSED:{permanent_reason}"
            gates = dict(source.get("gates") or {})
            gates.update(rec.get("gates") or {})
            gates["netcover_shadow"] = netcover_passed
            gates["position_cap"] = position_cap_passed
            rec["gates"] = gates
            reason = str(rec.get("rejection_reason") or "")
            if permanent_reason:
                status = "PERMANENT_FAIL_CLOSED"
            elif netcover_passed:
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
            rec["position_cap_gate_status"] = (
                "PASS" if position_cap_passed else str(
                    rec.get("position_cap_reason")
                    or "INV-TVLSHARE-01_INPUT_MISSING_OR_INVALID"
                )
            )
            prior_vetted = bool(source.get("vetted", False))
            rec["vetted_before_netcover"] = prior_vetted
            # Pre-NetCover entry eligibility is authoritative.  A terminal
            # adapter may enrich the record but cannot erase/flip that veto.
            entry_eligible = source.get(
                "entry_eligible", rec.get("entry_eligible")
            )
            if "entry_eligible" in source:
                rec["entry_eligible"] = source["entry_eligible"]
            if "entry_block_reasons" in source:
                rec["entry_block_reasons"] = list(
                    source.get("entry_block_reasons") or ()
                )
            rec["vetted"] = (
                prior_vetted and passed and entry_eligible is not False
            )
            if not rec["vetted"]:
                if netcover_passed and not position_cap_passed:
                    rec["rejection_reason"] = rec["position_cap_gate_status"]
                explanation_record = dict(source)
                explanation_record.update(rec)
                rec["rejection_reason"] = _explain_rejection(
                    explanation_record, False
                )
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
        """Assemble horizon-USD inputs, then invoke WP-04 without duplicating math.

        During independent Wave-2 development the module may not exist yet.
        Missing/unknown interfaces are an explicit rejection, never a silent
        fee-cover fallback.  WP-04 may expose either of the documented record
        adapter names below without creating an import cycle.
        """
        if self._is_solana():
            # A whole Solana batch produced by ``resolve`` is already blocked at
            # the authoritative identity boundary.  Short-circuit before the
            # Base/EVM live-state and Q96 input assemblers are imported or used.
            return [self._solana_mapping_blocked_record(record) for record in records]

        # Public route state is one fixed-block snapshot shared only within this
        # batch.  The next daemon cycle must remeasure rather than reuse stale L.
        self._base_cross_pool_measurements = None
        try:
            inputs_module = importlib.import_module("scripts.lp_netcover_inputs_v1_readonly")
            assembler = getattr(inputs_module, "assemble_netcover_inputs")
            assembled = []
            for source in records:
                # Route claims from the upstream screen are not raw chain
                # evidence.  M0F keeps conversion fail-closed until the scanner
                # can construct every preregistered route from validated calls.
                record = dict(source)
                for key in tuple(record):
                    if (
                        key.startswith("reward_conversion_")
                        or key.startswith("usd_quote_route")
                        or key.startswith("scanner_measured_")
                    ):
                        record.pop(key, None)
                token0 = str(record.get("token0") or "").lower()
                token1 = str(record.get("token1") or "").lower()
                reward_tokens = record.get("rewardTokens") or record.get("reward_tokens") or ()
                if isinstance(reward_tokens, str):
                    reward_tokens = (reward_tokens,)
                needs_quote = bool(
                    token0 and token1 and BASE_USDC not in {token0, token1}
                )
                needs_reward = {str(token).lower() for token in reward_tokens} == {BASE_AERO}
                measured_evidence = (
                    self._scanner_cross_pool_evidence(record)
                    if needs_quote or needs_reward else None
                )
                assembled.append(
                    assembler(
                        self._attach_live_pool_state(record),
                        scanner_measured_evidence=measured_evidence,
                    )
                )
        except Exception as exc:
            return self._fail_closed_netcover(records, f"netcover input assembly error: {exc}")

        try:
            module = importlib.import_module("scripts.lp_netcover_engine_v1_readonly")
        except ImportError:
            return self._fail_closed_netcover(records, "netcover unavailable (WP-04 not installed)")

        for name in ("apply_netcover_gate", "apply_netcover_to_records"):
            adapter = getattr(module, name, None)
            if callable(adapter):
                try:
                    result = adapter(assembled)
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


def export_latest_vetted_menu(
    db_path: str | os.PathLike[str], out_path: str | os.PathLike[str]
) -> Dict[str, Any]:
    """Export the latest *live-scanned* accepted score records for allocator.

    Malformed or semantically inconsistent score_json rows are rejected rather
    than repaired.  A zero-record output is valid evidence that the live funnel
    found no enterable opportunity; callers must not substitute a fixture and
    call it live-vetted.
    """
    db = Path(db_path)
    uri = f"file:{db.resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5.0) as connection:
        latest_row = connection.execute(
            "SELECT max(as_of) FROM opportunity_scores"
        ).fetchone()
        latest = latest_row[0] if latest_row else None
        rows = [] if latest is None else connection.execute(
            "SELECT score_json FROM opportunity_scores WHERE as_of=? AND accepted=1 ORDER BY pool",
            (latest,),
        ).fetchall()
    records: List[Dict[str, Any]] = []
    invalid = 0
    for (raw,) in rows:
        try:
            record = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            invalid += 1
            continue
        if (
            not isinstance(record, dict)
            or not record.get("vetted")
            or not record.get("netcover_pass")
            or record.get("position_cap_pass") is not True
            or record.get("position_cap_usd") is None
        ):
            invalid += 1
            continue
        record["scanner_as_of"] = latest
        record["scanner_evidence_origin"] = "live_opportunity_scores"
        records.append(record)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(records, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return {
        "as_of": latest,
        "accepted_rows": len(rows),
        "exported_records": len(records),
        "invalid_records": invalid,
        "out": str(out),
    }


def _apply_prior_reward_observations(
    batch: ScreenBatch,
    store: ScannerStore,
    *,
    cutoff: datetime | str,
) -> ScreenBatch:
    """Apply only pre-cycle measured history, otherwise recompute B-track."""
    screener = importlib.import_module("scripts.lp_universe_screener_v1_readonly")
    identities = [
        (str(record.get("llama_pool_id") or ""), str(record.get("chain") or ""))
        for record in batch.candidates
    ]
    evidence = store.reward_observation_evidence(identities, cutoff=cutoff)
    updated_candidates: List[Dict[str, Any]] = []
    for source in batch.candidates:
        rec = screener.strip_untrusted_reward_evidence(source)
        key = (
            str(rec.get("llama_pool_id") or ""),
            str(rec.get("chain") or "").lower(),
        )
        observed = evidence.get(key)
        if observed is not None:
            rec.update({
                "reward_observation_history_status": observed["status"],
                "reward_observation_history_duration_hours": observed["duration_hours"],
                "reward_observation_history_sample_count": observed["sample_count"],
                "reward_observation_history_first_as_of": observed["first_as_of"],
                "reward_observation_history_last_as_of": observed["last_as_of"],
            })
            duration = observed.get("duration_hours")
            if duration is not None and float(duration) >= MIN_REWARD_OBSERVATION_HOURS:
                rec.update({
                    "reward_high_duration": float(duration),
                    "reward_persistence_evidence_source": "measured_observation",
                    "reward_measured_observation_count": observed["sample_count"],
                    "reward_measured_observation_first_as_of": observed["first_as_of"],
                    "reward_measured_observation_last_as_of": observed["last_as_of"],
                })
        updated_candidates.append(screener.apply_reward_persistence_assessment(rec))

    by_identity = {
        (
            str(record.get("llama_pool_id") or ""),
            str(record.get("chain") or "").lower(),
        ): record
        for record in updated_candidates
    }
    updated_all = []
    for source in batch.all_records:
        key = (
            str(source.get("llama_pool_id") or ""),
            str(source.get("chain") or "").lower(),
        )
        updated_all.append(dict(by_identity.get(key, source)))
    return ScreenBatch(all_records=updated_all, candidates=updated_candidates)


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
        # Freeze the cutoff before screening.  The current snapshot is written
        # only after all decisions, so one cycle can never certify itself.
        stamp = _as_of_text(as_of)
        if refresh_coarse or self._screen_batch is None:
            batch = self.stages.screen()
            if not isinstance(batch, ScreenBatch):
                raise TypeError("screen stage must return ScreenBatch")
            self._screen_batch = batch
        batch = self._screen_batch
        assert batch is not None
        batch = _apply_prior_reward_observations(batch, self.store, cutoff=stamp)
        self._screen_batch = batch

        resolved = list(self.stages.resolve(batch.candidates))
        stability = list(self.stages.multiwindow(resolved))
        vetted = list(self.stages.funnel(resolved, stability))
        scored = list(self.stages.netcover(vetted))

        snapshot_records = _merge_snapshot_records(batch.all_records, resolved)
        snapshot_rows = [_snapshot_row(record) for record in snapshot_records]
        score_rows = [_score_row(record) for record in scored]
        sessions = _unique_sessions([*batch.all_records, *resolved, *scored])
        observation_rows = [
            row for row in (_reward_observation_row(record) for record in batch.candidates)
            if row is not None
        ]
        self.store.write_cycle(
            stamp,
            pool_snapshots=snapshot_rows,
            opportunity_scores=score_rows,
            market_sessions=sessions,
            reward_observations=observation_rows,
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
        rpc_health_recorder: Optional[Callable[[str], None]] = None,
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
        self.rpc_health_recorder = rpc_health_recorder
        self.monotonic = monotonic
        self._stop = threading.Event()

    def _notify_cycle(self, result: Any) -> None:
        if self.rpc_health_recorder is not None:
            health = result.get("rpc_health") if isinstance(result, Mapping) else getattr(result, "rpc_health", None)
            if health is not None:
                try:
                    self.rpc_health_recorder(str(health))
                except Exception as exc:  # noqa: BLE001 - scanner evidence remains committed
                    print(
                        f"[scanner] gate evidence write failed: {type(exc).__name__}",
                        file=sys.stderr,
                        flush=True,
                    )
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
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument(
        "--capital-tier", choices=CAPITAL_TIERS, default=DEFAULT_CAPITAL_TIER,
        help="PRD v2.1 capital tier used for coarse TVL and runtime sizing",
    )
    parser.add_argument(
        "--min-tvl", type=float, default=None,
        help="optional tightening-only override; cannot lower the tier floor",
    )
    parser.add_argument("--min-vol1d", type=float, default=50_000.0)
    parser.add_argument("--window-blocks", type=int, default=86_400)
    parser.add_argument("--window-days", type=float, default=1.0)
    parser.add_argument("--n-windows", type=int, default=6)
    parser.add_argument("--yc-min", type=float, default=1.0)
    parser.add_argument(
        "--vetted-menu-out", default=None,
        help="after exit, export latest live accepted score_json rows for allocator",
    )
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
        capital_tier=args.capital_tier,
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
    from scripts.lp_shadow_gate_v1_readonly import GateStore

    gate_store = GateStore(args.db)

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
        rpc_health_recorder=lambda health: gate_store.record_rpc_health(
            health, as_of=now(), source="scanner"
        ),
    )
    try:
        rc = daemon.run(once=args.once)
        if args.vetted_menu_out:
            result = export_latest_vetted_menu(args.db, args.vetted_menu_out)
            print(
                f"[scanner] vetted_menu exported={result['exported_records']} "
                f"invalid={result['invalid_records']} out={result['out']}",
                flush=True,
            )
        return rc
    except Exception as exc:
        print(f"[scanner] fatal: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
