"""
Paper daemon entry point (W5 deploy package — NOT for live execution).

Provides four pure-import functions that perform no I/O at module load time:

  preflight(cfg_path)   — validate config, paths, PID lock, execution guards,
                          AND source adapter identity/schema/binding.
  status(cfg_path)      — return current operational state (no daemon required),
                          including source health and cursor.
  run_once(cfg_path)    — execute ONE episode against the configured read-only
                          source.  Real events only; NO synthetic fallback in
                          production path.  NO_TRADE/NO_NEW_DATA/BLOCKED_DATA
                          distinguished by exit code.
  run_daemon(cfg_path)  — single-shot wrapper around run_once (long-running
                          loops are out of scope per OBSERVE_ONLY_DECISION_RULES_CN).

No side effects occur at import time.  All functions are safe to call from
tests or review tooling without starting any daemon.

Source contract (per NEXT_AGENT_TASK_CN.md §1):
  * Production source is `[source] db_path / events_table / pool_address /
    chain_id / expected_interval_secs / lookback_hours` from the config.
  * Source missing / structured wrong / identity unknown → EXIT_BLOCKED_DATA.
  * Source normal but no events since cursor → EXIT_NO_NEW_DATA (still 0).
  * Real data with no qualified candidates → EXIT_NO_TRADE.
  * Synthetic fixture (`_build_paper_sample_fixture`) is for explicit demo
    entry only; the production `run_once` path MUST NOT use it.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
import tomllib

# Local dependency — no network, no signing, no broadcasting.
from scripts.lp_rh_paper_pid_lock_v1 import acquire, is_alive, read_pid
from scripts.lp_rh_paper_source_adapter_v1 import (
    EXIT_BLOCKED_DATA,
    EXIT_NO_NEW_DATA,
    PaperSourceAdapter,
    SourceConfigError,
    SourceFreshnessError,
    SourceIdentityError,
    SourceSchemaError,
)
from scripts.lp_rh_shadow_daemon_v1_readonly import (
    _run_episode_persisted,
)
from scripts.lp_rh_shadow_runner_v1_readonly import episode_summary
from scripts.lp_rh_store_v1_readonly import migrate, open_store

# Exit codes (re-export from adapter for clarity)
EXIT_NO_TRADE = 0          # episode ran end-to-end or NO_NEW_DATA
EXIT_TECH_ERROR = 1        # preflight/IO/exception
EXIT_BLOCKED_DATA = 2      # source missing/structured wrong/identity unknown

# Sentinel values for status dict
MODE_PAPER_ONLY = "paper_only"
PROFILE_PAPER = "rh-core-paper-v1"


# ---------------------------------------------------------------------------
# Demo fixture — used by D1 positive control tests, NEVER by run_once()
# ---------------------------------------------------------------------------

PAPER_SAMPLE_BASE: dict[str, Any] = {
    "chain_id": 4663,
    "attestation_status": "ATTESTED_SAME_BLOCK",
    "protocol": "v3",
    "fee_apr_pct": 100.0,
    "sigma_daily": 0.0,
    "liquidity_raw": 1e20,
    "sqrt_price_x96": 4_340_000_000_000_000_000_000_000_000_000,
    "fee": 500,
    "dec0": 18,
    "dec1": 6,
    "gas_usd_estimate": 0.01,
    "reference_mid": "2000",
    "fee_growth_global_0": "0",
    "fee_growth_global_1": "0",
    "legacy_required_conjunction": True,
    "identity_verified": True,
    "protocol_capabilities_sufficient": True,
    "data_complete_and_fresh": True,
    "profile_policy_pass": True,
    "market_and_chain_risk_pass": True,
    "absolute_profit_pass": True,
    "position_and_exit_depth_pass": True,
    "capital_policy_pass": True,
}

PAPER_POOL_META_FRESH: dict[str, Any] = {
    "as_of": "2025-12-31T23:00:00Z",
    "tick_data": [{"tick_lower": -100, "tick_upper": 100, "liquidity_net": 10 ** 18}],
    "max_impact_bps": 50,
    "attestation_status": "ATTESTED_SAME_BLOCK",
    "protocol": "v3",
    "dec0": 18,
    "dec1": 6,
    "range_pct": 10.0,
    "pool_address": "0xpool-paper-core",
    "input_price_usd": "2000",
    "token0": "0xtoken0paper",
    "token1": "0xtoken1paper",
}


def build_demo_sample_fixture(*, n_steps: int = 3) -> list[dict[str, Any]]:
    """EXPLICIT DEMO fixture — only for tests / docs; NOT for run_once().

    Renamed from `_build_paper_sample_fixture` to make the demo-only status
    visible.  Any call from production code is a contract violation; tests
    use this function directly.  Same shape as D1 positive control:
    cost_entry=5, last sample cost_exit=5 → NAV 1000→990, NetPnL=-10.
    """
    samples: list[dict[str, Any]] = []
    for i in range(n_steps):
        t = f"2026-01-01T00:{i:02d}:00Z"
        samples.append({
            **PAPER_SAMPLE_BASE,
            "candidate_key": f"pool-paper-core-{i}",
            "sample_time": t,
            "quote_usd_per_token1": {
                "value": "1.0",
                "source": "demo_fixture",
                "observed_at": t,
                "ttl_secs": 3600,
            },
            "entry_cost_usd": "5",
            "exit_cost_usd": "5" if i == n_steps - 1 else "0",
            "gas_usd": "0",
        })
    return samples


# Back-compat alias — old tests import this name.
_build_paper_sample_fixture = build_demo_sample_fixture


# ---------------------------------------------------------------------------
# Config + path helpers
# ---------------------------------------------------------------------------

def _load_config(cfg_path: str) -> dict[str, Any]:
    if not os.path.isfile(cfg_path):
        raise FileNotFoundError(f"config not found: {cfg_path}")
    with open(cfg_path, "rb") as fh:
        return tomllib.load(fh)


def _build_source_adapter(cfg: dict[str, Any]) -> PaperSourceAdapter:
    try:
        return PaperSourceAdapter.from_config(cfg)
    except (SourceConfigError, SourceSchemaError) as exc:
        raise SourceConfigError(str(exc)) from exc


def _count_episodes_in_ledger(ledger_db_path: str) -> tuple[int, str | None]:
    """Read episode rows from the ledger's rh_episode_summary table."""
    if not os.path.isfile(ledger_db_path):
        return 0, None
    try:
        conn = sqlite3.connect(f"file:{ledger_db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return 0, None
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='rh_episode_summary'"
        )
        if cur.fetchone() is None:
            return 0, None
        row = conn.execute(
            "SELECT COUNT(*), MAX(ended_at) FROM rh_episode_summary"
        ).fetchone()
        count = int(row[0]) if row and row[0] is not None else 0
        last_iso = str(row[1]) if row and row[1] is not None else None
        return count, last_iso
    except sqlite3.Error:
        return 0, None
    finally:
        conn.close()


def _read_cursor(conn: sqlite3.Connection, *, chain_id: int, pool_address: str) -> str | None:
    """Read last processed sample_time from rh_paper_cursor.

    Returns None if no cursor row exists.  The cursor binds (chain_id,
    pool_address) so a single ledger can serve multiple sources.
    """
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='rh_paper_cursor'"
    )
    if cur.fetchone() is None:
        return None
    row = conn.execute(
        "SELECT last_event_time FROM rh_paper_cursor WHERE chain_id=? AND pool_address=?",
        (chain_id, pool_address),
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return str(row[0])


def _write_cursor(
    conn: sqlite3.Connection,
    *,
    chain_id: int,
    pool_address: str,
    last_event_time: str,
    episode_id: str,
) -> None:
    """Upsert cursor atomically — one row per (chain_id, pool_address)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rh_paper_cursor (
            chain_id INTEGER NOT NULL,
            pool_address TEXT NOT NULL,
            last_event_time TEXT NOT NULL,
            episode_id TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (chain_id, pool_address)
        )
        """
    )
    conn.execute(
        """
        INSERT INTO rh_paper_cursor (chain_id, pool_address, last_event_time, episode_id, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(chain_id, pool_address) DO UPDATE SET
            last_event_time = excluded.last_event_time,
            episode_id = excluded.episode_id,
            updated_at = excluded.updated_at
        """,
        (
            int(chain_id),
            str(pool_address),
            str(last_event_time),
            str(episode_id),
            datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        ),
    )


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

def preflight(cfg_path: str) -> tuple[bool, list[str]]:
    """Validate config, paths, PID lock, execution guards, AND source.

    Checks:
      1. File exists + parses as valid TOML with all required sections.
      2. Ledger DB parent dir exists or can be created.
      3. PID file parent dir exists.
      4. PID file is not currently held by another process.
      5. execution.signing_enabled == False.
      6. execution.broadcasting_enabled == False.
      7. [source] section exists with all required keys, schema and identity
         checks pass against the configured read-only DB.

    Returns (True, []) on success or (False, [reason, ...]) on any failure.
    """
    errors: list[str] = []

    if not os.path.isfile(cfg_path):
        return False, [f"config file not found: {cfg_path}"]

    try:
        with open(cfg_path, "rb") as fh:
            cfg = tomllib.load(fh)
    except Exception as exc:
        return False, [f"failed to parse TOML: {exc}"]

    required_sections = [
        "meta", "chain", "pool", "capital", "economics",
        "execution", "paths", "resources", "safety", "source", "profile",
    ]
    for section in required_sections:
        if section not in cfg:
            errors.append(f"missing required TOML section: [{section}]")

    if errors:
        return False, errors

    ledger_db: str = cfg.get("paths", {}).get("ledger_db", "")
    if ledger_db:
        db_dir = os.path.dirname(ledger_db)
        if db_dir and not os.path.isdir(db_dir):
            try:
                os.makedirs(db_dir, exist_ok=True)
            except OSError as exc:
                errors.append(f"cannot create ledger_db parent dir {db_dir}: {exc}")

    pid_file: str = cfg.get("paths", {}).get("pid_file", "")
    if pid_file:
        pid_dir = os.path.dirname(pid_file)
        if pid_dir and not os.path.isdir(pid_dir):
            errors.append(f"PID file parent dir does not exist and cannot be created: {pid_dir}")

    if pid_file:
        alive = is_alive(pid_file)
        if alive:
            pid = read_pid(pid_file)
            errors.append(f"PID file {pid_file} already held by alive process {pid}")

        if not acquire(pid_file):
            pass  # race-tolerant; preflight does not require sole lock
        else:
            from scripts.lp_rh_paper_pid_lock_v1 import release as _release
            _release(pid_file)

    signing: bool = cfg.get("execution", {}).get("signing_enabled", True)
    if signing:
        errors.append("execution.signing_enabled must be False for paper mode; found True")

    broadcasting: bool = cfg.get("execution", {}).get("broadcasting_enabled", True)
    if broadcasting:
        errors.append("execution.broadcasting_enabled must be False for paper mode; found True")

    # 7. Source adapter validation (open + schema + identity)
    try:
        adapter = PaperSourceAdapter.from_config(cfg)
        adapter.validate()
    except (SourceConfigError, SourceSchemaError, SourceIdentityError) as exc:
        errors.append(f"[source] adapter rejected: {exc}")

    if errors:
        return False, errors
    return True, []


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def status(cfg_path: str) -> dict[str, Any]:
    """Return current operational state of the paper daemon.

    Reads config + ledger DB (read-only) + source DB (read-only).
    Does NOT start a daemon.

    Returns dict with keys:
      mode, profile, capital_usd, position_size_usd,
      episodes_run (real count from rh_episode_summary),
      last_tick_at (real MAX(ended_at) or None),
      ledger_db (resolved path),
      source (read-only health of the configured source DB),
      cursor (last_event_time from rh_paper_cursor or None).
    """
    default = {
        "mode": MODE_PAPER_ONLY,
        "profile": PROFILE_PAPER,
        "capital_usd": 1000.0,
        "position_size_usd": 100.0,
        "episodes_run": 0,
        "last_tick_at": None,
        "ledger_db": "",
        "source": None,
        "cursor": None,
    }

    if not os.path.isfile(cfg_path):
        return default

    try:
        cfg = _load_config(cfg_path)
    except Exception:
        return default

    capital_cfg = cfg.get("capital") or {}
    exec_cfg = cfg.get("execution") or {}
    meta_cfg = cfg.get("meta") or {}
    paths_cfg = cfg.get("paths") or {}

    capital_value = capital_cfg.get("virtual_capital_usd")
    capital_usd = float(capital_value) if isinstance(capital_value, (int, float)) and capital_value > 0 else 1000.0

    position_value = capital_cfg.get("position_size_usd")
    position_size = float(position_value) if isinstance(position_value, (int, float)) and position_value > 0 else 100.0

    ledger_db = str(paths_cfg.get("ledger_db") or "")
    episodes_run, last_tick_at = _count_episodes_in_ledger(ledger_db)

    out = {
        "mode": exec_cfg.get("mode") or MODE_PAPER_ONLY,
        "profile": meta_cfg.get("profile") or PROFILE_PAPER,
        "capital_usd": capital_usd,
        "position_size_usd": position_size,
        "episodes_run": episodes_run,
        "last_tick_at": last_tick_at,
        "ledger_db": ledger_db,
        "source": None,
        "cursor": None,
    }

    # Source health (read-only, may fail without breaking status)
    try:
        adapter = PaperSourceAdapter.from_config(cfg)
        out["source"] = adapter.read_source_health()
    except Exception as exc:
        out["source"] = {"error": str(exc), "db_path": None}

    # Cursor (read from ledger if available)
    if ledger_db and os.path.isfile(ledger_db):
        try:
            conn = sqlite3.connect(f"file:{ledger_db}?mode=ro", uri=True)
            try:
                src_cfg = cfg.get("source") or {}
                out["cursor"] = _read_cursor(
                    conn,
                    chain_id=int(src_cfg.get("chain_id", 0)),
                    pool_address=str(src_cfg.get("pool_address", "")),
                )
            finally:
                conn.close()
        except sqlite3.Error:
            pass

    return out


# ---------------------------------------------------------------------------
# Episode schema persistence
# ---------------------------------------------------------------------------

def _persist_episode_summary(
    conn,
    *,
    episode_id: str,
    started_at: str,
    ended_at: str,
    pool: str,
    position_usd: Decimal,
    capital_usd: Decimal,
    summary: dict[str, Any],
) -> None:
    """Upsert one row into rh_episode_summary so status() can read it."""
    _ensure_rh_episode_summary_table(conn)
    nav_start = summary.get("nav_start")
    nav_end = summary.get("nav_end")
    net_pnl = summary.get("net_pnl")
    conn.execute(
        """
        INSERT OR REPLACE INTO rh_episode_summary (
            episode_id, started_at, ended_at, pool,
            position_usd, capital_usd,
            nav_start, nav_end, net_pnl,
            eligible_steps, ledger_duplicate_rows, copied,
            event_count, first_event_time, last_event_time
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            episode_id,
            started_at,
            ended_at,
            pool,
            str(position_usd),
            str(capital_usd),
            str(nav_start) if nav_start is not None else None,
            str(nav_end) if nav_end is not None else None,
            str(net_pnl) if net_pnl is not None else None,
            int(summary.get("eligible_steps") or 0),
            int(summary.get("ledger_duplicate_rows") or 0),
            _json_dumps(summary.get("copied")),
            int(summary.get("event_count") or 0),
            str(summary.get("first_event_time")) if summary.get("first_event_time") else None,
            str(summary.get("last_event_time")) if summary.get("last_event_time") else None,
        ),
    )


def _ensure_rh_episode_summary_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rh_episode_summary (
            episode_id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            pool TEXT NOT NULL,
            position_usd TEXT NOT NULL,
            capital_usd TEXT NOT NULL,
            nav_start TEXT,
            nav_end TEXT,
            net_pnl TEXT,
            eligible_steps INTEGER NOT NULL DEFAULT 0,
            ledger_duplicate_rows INTEGER NOT NULL DEFAULT 0,
            copied TEXT,
            event_count INTEGER NOT NULL DEFAULT 0,
            first_event_time TEXT,
            last_event_time TEXT
        )
        """
    )


def _json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    import json
    try:
        return json.dumps(value, separators=(",", ":"), default=str)
    except Exception:
        return None


def _events_to_samples(
    events: list[dict[str, Any]],
    *,
    pool: str,
    expected_interval_secs: int,
    chain_id: int,
    asset_address: str,
    engine_params: dict[str, Any],
    cost_source: dict[str, str],
) -> list[dict[str, Any]]:
    """Translate raw adapter events into the paper sample shape consumed by
    `_run_episode_persisted`.  PURE SOURCE-DRIVEN — no demo fixture, no
    PAPER_SAMPLE_BASE, no zeroed costs.

    Each sample is built from:
      * market state (sample_time, reference_mid, fee_growth_global_0/1)
        — read DIRECTLY from the event row, with NULL → KeyError raised
        by the adapter's NOT NULL filter before this point.
      * identity (chain_id, asset_address, source_event_time) — embedded
        so it propagates into rh_gate_decisions / rh_position_marks.
      * engine params (attestation_status, protocol, fee_apr_pct,
        sigma_daily, *_pass flags, legacy_required_conjunction, etc.)
        — supplied from cfg via `engine_params`.  These are engine
        policy inputs, not market data; if cfg omits them, run_once()
        raises SourceConfigError BEFORE reaching this function.
      * costs (entry_cost_usd, exit_cost_usd, gas_usd) — supplied per-event
        via `cost_source` (an `entry_cost_usd`, `exit_cost_usd`, `gas_usd`
        callable taking an event index) OR via cfg-level defaults.  If
        BOTH are missing, the event row MUST carry them — and missing
        per-event cost → KeyError raises SourceIdentityError.

    Forbidden: PAPER_SAMPLE_BASE, hardcoded zero costs, time anchored to
    any fixture clock.  The literal `0` may appear as fee_growth's neutral
    starting point but only because the real source has zero starting fee
    growth at session start; that is observable, not synthetic.
    """
    if not events:
        return []
    samples: list[dict[str, Any]] = []
    for idx, evt in enumerate(events):
        ref_mid = evt["reference_mid"]
        src_event_time = evt.get("source_event_time") or evt["sample_time"]
        sample_time = evt["sample_time"]
        ref_age = evt.get("reference_age_secs")
        if ref_age is None:
            raise SourceIdentityError(
                f"event {idx} (sample_time={sample_time}) missing "
                f"reference_age_secs — required for evaluate_health"
            )
        samples.append({
            **engine_params,
            "candidate_key": f"{pool}-{idx}",
            "sample_time": sample_time,
            "source_event_time": src_event_time,
            "chain_id": int(chain_id),
            "asset_address": str(asset_address),
            "reference_mid": ref_mid,
            "fee_growth_global_0": evt["fee_growth_global_0"],
            "fee_growth_global_1": evt["fee_growth_global_1"],
            "reference_age_secs": int(ref_age),
            "quote_usd_per_token1": {
                "value": ref_mid,
                "source": "rh_market_states",
                "observed_at": src_event_time,
                "ttl_secs": max(60, expected_interval_secs * 2),
            },
            "entry_cost_usd": cost_source["entry_cost_usd"](idx, evt),
            "exit_cost_usd": cost_source["exit_cost_usd"](idx, evt),
            "gas_usd": cost_source["gas_usd"](idx, evt),
        })
    return samples


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _resolve_pool_meta_fresh(
    cfg: dict[str, Any],
    *,
    source_db_path: str,
    chain_id: int,
    asset_address: str,
) -> dict[str, Any]:
    """Pool metadata for the episode — read from source DB's `rh_pool_meta`
    table, NOT from a hardcoded fixture.  Pure read-only.

    Identity binding: chain_id + asset_address (matches source adapter).
    Schema: required columns are pool_address / chain_id / as_of /
    attestation_status / dec0 / dec1 / max_impact_bps / protocol /
    range_pct / token0 / token1 / input_price_usd / tick_data.

    Returns the meta dict (with as_of from the source row, NOT wall clock).
    Raises SourceIdentityError on missing row or schema mismatch — the
    production path MUST fail-closed rather than fall back to demo values.
    """
    pool_cfg = cfg.get("pool") or {}
    if not Path(source_db_path).is_file():
        raise SourceConfigError(
            f"pool_meta source db not found: {source_db_path}"
        )
    conn = sqlite3.connect(f"file:{source_db_path}?mode=ro", uri=True)
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='rh_pool_meta'"
        )
        if cur.fetchone() is None:
            raise SourceSchemaError(
                "rh_pool_meta table missing from source DB — cannot "
                "resolve pool metadata without demo fallback"
            )
        cols = {
            r[1]
            for r in conn.execute("PRAGMA table_info(rh_pool_meta)").fetchall()
        }
        required = {
            "pool_address", "chain_id", "as_of", "attestation_status",
            "dec0", "dec1", "max_impact_bps", "protocol", "range_pct",
            "token0", "token1", "input_price_usd", "tick_data",
        }
        missing = required - cols
        if missing:
            raise SourceSchemaError(
                f"rh_pool_meta missing columns: {sorted(missing)}"
            )
        row = conn.execute(
            """
            SELECT as_of, attestation_status, dec0, dec1, max_impact_bps,
                   protocol, range_pct, token0, token1, input_price_usd,
                   tick_data
            FROM rh_pool_meta
            WHERE chain_id=? AND LOWER(pool_address)=LOWER(?)
            """,
            (int(chain_id), str(asset_address)),
        ).fetchone()
        if row is None:
            raise SourceIdentityError(
                f"no rh_pool_meta row for chain_id={chain_id} "
                f"pool_address={asset_address}"
            )
        (
            as_of, attestation, dec0, dec1, max_impact,
            protocol, range_pct, token0, token1, input_price, tick_data_raw,
        ) = row
        import json as _json
        try:
            tick_data = _json.loads(tick_data_raw) if tick_data_raw else []
        except Exception:
            tick_data = []
        meta = {
            "pool_address": str(asset_address),
            "chain_id": int(chain_id),
            "as_of": str(as_of),
            "attestation_status": str(attestation),
            "dec0": int(dec0),
            "dec1": int(dec1),
            "max_impact_bps": int(max_impact),
            "protocol": str(protocol),
            "range_pct": float(range_pct),
            "token0": str(token0),
            "token1": str(token1),
            "input_price_usd": str(input_price),
            "tick_data": tick_data,
        }
        # cfg overrides for testability: cfg's [pool] values win on conflict
        # (e.g., test may pin dec0=18 when source row has 6).  Production
        # cfg should match the source row.
        for key in ("dec0", "dec1", "range_pct"):
            if key in pool_cfg:
                meta[key] = (
                    int(pool_cfg[key]) if key != "range_pct"
                    else float(pool_cfg[key])
                )
        if "tick_data" in pool_cfg:
            meta["tick_data"] = pool_cfg["tick_data"]
        return meta
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Engine params + cost source from cfg (production path)
# ---------------------------------------------------------------------------

# Required cfg keys for the production engine — fail-closed if missing.
REQUIRED_ENGINE_PARAM_KEYS: tuple[str, ...] = (
    "attestation_status",
    "protocol",
    "fee_apr_pct",
    "sigma_daily",
    "liquidity_raw",
    "sqrt_price_x96",
    "fee",
    "dec0",
    "dec1",
    "gas_usd_estimate",
    "legacy_required_conjunction",
    "identity_verified",
    "protocol_capabilities_sufficient",
    "data_complete_and_fresh",
    "profile_policy_pass",
    "market_and_chain_risk_pass",
    "absolute_profit_pass",
    "position_and_exit_depth_pass",
    "capital_policy_pass",
)


def _build_engine_params(cfg: dict[str, Any]) -> dict[str, Any]:
    """Build the engine-params dict from cfg.

    These are POLICY inputs (attestation, protocol capability, risk passes,
    pool constants like liquidity_raw / sqrt_price_x96 / fee / decimals).
    They MUST come from cfg — the source DB is a market-state stream, not
    a policy stream.  PAPER_SAMPLE_BASE is no longer consulted.

    If [engine_params] section is missing or any required key is absent,
    raises SourceConfigError → run_once returns EXIT_BLOCKED_DATA.
    """
    engine_cfg = cfg.get("engine_params") or {}
    if not isinstance(engine_cfg, dict):
        raise SourceConfigError(
            "[engine_params] section missing or not a dict"
        )
    missing = [k for k in REQUIRED_ENGINE_PARAM_KEYS if k not in engine_cfg]
    if missing:
        raise SourceConfigError(
            f"[engine_params] missing required keys: {missing}"
        )
    out = {k: engine_cfg[k] for k in REQUIRED_ENGINE_PARAM_KEYS}
    # Type coercion — cfg is TOML; booleans come through as bool, ints as
    # int, floats as float.  Cast aggressively to keep engine contract tight.
    out["fee_apr_pct"] = float(out["fee_apr_pct"])
    out["sigma_daily"] = float(out["sigma_daily"])
    out["liquidity_raw"] = (
        int(out["liquidity_raw"])
        if isinstance(out["liquidity_raw"], int) or
        (isinstance(out["liquidity_raw"], str) and
         out["liquidity_raw"].isdigit())
        else float(out["liquidity_raw"])
    )
    out["sqrt_price_x96"] = (
        int(out["sqrt_price_x96"])
        if isinstance(out["sqrt_price_x96"], int) or
        (isinstance(out["sqrt_price_x96"], str) and
         out["sqrt_price_x96"].isdigit())
        else float(out["sqrt_price_x96"])
    )
    out["fee"] = int(out["fee"])
    out["dec0"] = int(out["dec0"])
    out["dec1"] = int(out["dec1"])
    out["gas_usd_estimate"] = float(out["gas_usd_estimate"])
    for k in (
        "legacy_required_conjunction", "identity_verified",
        "protocol_capabilities_sufficient", "data_complete_and_fresh",
        "profile_policy_pass", "market_and_chain_risk_pass",
        "absolute_profit_pass", "position_and_exit_depth_pass",
        "capital_policy_pass",
    ):
        out[k] = bool(out[k])
    return out


def _build_cost_source(cfg: dict[str, Any]) -> dict[str, Any]:
    """Build the cost-source lookup.

    Per-event costs take precedence (cfg → [costs.per_event.<col_name>],
    a list aligned to events).  If a per-event list is missing, falls back
    to cfg-level defaults ([costs.defaults]).  If BOTH are missing, raises
    SourceConfigError.

    Returns dict with three callables, each (idx, event) → str cost:
      entry_cost_usd, exit_cost_usd, gas_usd.
    """
    cost_cfg = cfg.get("costs") or {}
    defaults = cost_cfg.get("defaults") or {}
    per_event = cost_cfg.get("per_event") or {}

    def _resolve(col: str) -> Any:
        per = per_event.get(col)
        if per is not None:
            if not isinstance(per, list):
                raise SourceConfigError(
                    f"[costs.per_event.{col}] must be a list aligned to events"
                )
            return per
        if col in defaults:
            v = defaults[col]
            return ["__default__", v]  # sentinel: always return v
        raise SourceConfigError(
            f"[costs] missing both per_event.{col} list and defaults.{col}; "
            "production paper path cannot zero-fill costs"
        )

    entry_list = _resolve("entry_cost_usd")
    exit_list = _resolve("exit_cost_usd")
    gas_list = _resolve("gas_usd")

    def _make(lst: list) -> Any:
        if len(lst) == 2 and lst[0] == "__default__":
            default = lst[1]
            def fn(_idx: int, _evt: dict) -> str:
                return str(default)
            return fn
        # per-event list — index into it
        def fn(idx: int, _evt: dict) -> str:
            if idx >= len(lst):
                raise SourceIdentityError(
                    f"[costs.per_event] index {idx} out of range "
                    f"(list length {len(lst)})"
                )
            return str(lst[idx])
        return fn

    return {
        "entry_cost_usd": _make(entry_list),
        "exit_cost_usd": _make(exit_list),
        "gas_usd": _make(gas_list),
    }


# ---------------------------------------------------------------------------
# run_once / run_daemon
# ---------------------------------------------------------------------------

def run_once(cfg_path: str) -> tuple[int, dict[str, Any]]:
    """Execute ONE episode against the configured real read-only source.

    Real events only.  NO synthetic fallback in this path.  Exit codes:
      0  — EXIT_NO_TRADE   (episode ran; no qualifying trade) or
           EXIT_NO_NEW_DATA (source OK; no events newer than cursor)
      1  — EXIT_TECH_ERROR (uncaught exception / IO failure)
      2  — EXIT_BLOCKED_DATA (source missing/structured wrong/identity unknown)

    Returns (exit_code, evidence_dict).  evidence_dict always has the fields
    `started_at`, `ended_at`, `episode_id`, plus a status branch
    (`blocked`, `no_new_data`, `episode`) describing what actually happened.
    """
    started_at = _now_iso()
    episode_id = str(uuid.uuid4())
    base_evidence: dict[str, Any] = {
        "started_at": started_at,
        "episode_id": episode_id,
        "cfg_path": cfg_path,
    }

    ok, errs = preflight(cfg_path)
    if not ok:
        return EXIT_BLOCKED_DATA, {
            **base_evidence,
            "ended_at": _now_iso(),
            "status": "blocked",
            "stage": "preflight",
            "errors": errs,
        }

    try:
        cfg = _load_config(cfg_path)
    except Exception as exc:
        return EXIT_TECH_ERROR, {
            **base_evidence,
            "ended_at": _now_iso(),
            "status": "blocked",
            "stage": "config_load",
            "errors": [f"failed to re-load config: {exc}"],
        }

    try:
        adapter = PaperSourceAdapter.from_config(cfg)
        adapter.validate()
    except (SourceConfigError, SourceSchemaError, SourceIdentityError, SourceFreshnessError) as exc:
        return EXIT_BLOCKED_DATA, {
            **base_evidence,
            "ended_at": _now_iso(),
            "status": "blocked",
            "stage": "source_validate",
            "errors": [str(exc)],
        }

    paths_cfg = cfg.get("paths") or {}
    ledger_db = str(paths_cfg.get("ledger_db") or "")
    if not ledger_db:
        return EXIT_TECH_ERROR, {
            **base_evidence,
            "ended_at": _now_iso(),
            "status": "blocked",
            "stage": "ledger_path",
            "errors": ["[paths].ledger_db missing"],
        }

    try:
        Path(ledger_db).parent.mkdir(parents=True, exist_ok=True)
        conn = open_store(ledger_db)
        migrate(conn)
    except Exception as exc:
        return EXIT_TECH_ERROR, {
            **base_evidence,
            "ended_at": _now_iso(),
            "status": "blocked",
            "stage": "ledger_open",
            "errors": [f"cannot open ledger DB: {exc}"],
        }

    cursor_ts = _read_cursor(
        conn,
        chain_id=adapter.chain_id,
        pool_address=adapter.pool_address,
    )

    now_iso = _now_iso()
    try:
        events = adapter.read_new_events(cursor_ts, now_iso=now_iso, max_events=1024)
    except (SourceConfigError, SourceSchemaError, SourceIdentityError) as exc:
        conn.close()
        return EXIT_BLOCKED_DATA, {
            **base_evidence,
            "ended_at": _now_iso(),
            "status": "blocked",
            "stage": "source_read",
            "errors": [str(exc)],
        }
    except Exception as exc:
        conn.close()
        return EXIT_TECH_ERROR, {
            **base_evidence,
            "ended_at": _now_iso(),
            "status": "blocked",
            "stage": "source_read_unexpected",
            "errors": [f"unexpected error reading source: {exc}"],
        }

    if not events:
        conn.close()
        return EXIT_NO_NEW_DATA, {
            **base_evidence,
            "ended_at": _now_iso(),
            "status": "no_new_data",
            "stage": "source_read",
            "chain_id": adapter.chain_id,
            "pool_address": adapter.pool_address,
            "cursor": cursor_ts,
            "now_iso": now_iso,
            "event_count": 0,
            "errors": [],
        }

    pool_meta = _resolve_pool_meta_fresh(
        cfg,
        source_db_path=adapter.db_path,
        chain_id=adapter.chain_id,
        asset_address=adapter.pool_address,
    )
    try:
        engine_params = _build_engine_params(cfg)
        cost_source = _build_cost_source(cfg)
    except SourceConfigError as exc:
        conn.close()
        return EXIT_BLOCKED_DATA, {
            **base_evidence,
            "ended_at": _now_iso(),
            "status": "blocked",
            "stage": "engine_params_or_costs",
            "errors": [str(exc)],
        }
    samples = _events_to_samples(
        events,
        pool=adapter.pool_address,
        expected_interval_secs=adapter.expected_interval_secs,
        chain_id=adapter.chain_id,
        asset_address=adapter.pool_address,
        engine_params=engine_params,
        cost_source=cost_source,
    )

    cap_cfg = cfg.get("capital") or {}
    capital_usd = Decimal(str(cap_cfg.get("virtual_capital_usd", "1000")))
    position_usd = Decimal(str(cap_cfg.get("position_size_usd", "100")))

    profile_cfg = cfg.get("profile") or {}
    horizon_hours = int(profile_cfg.get("horizon_hours", 24))
    target_mode = str(cfg.get("meta", {}).get("target_mode", "SHADOW_SCENARIO"))

    engine_cfg = {
        "pool": adapter.pool_address,
        "chain_id": adapter.chain_id,
        "asset_address": adapter.pool_address,
        "position_usd": position_usd,
        "horizon_hours": horizon_hours,
        "capital_usd": capital_usd,
        "target_mode": target_mode,
        "pool_meta": pool_meta,
        "pool_meta_hash": None,
        "live_db": adapter.db_path,
        "samples": len(samples),
        "ledger_db": ledger_db,
        "source_event_time_first": events[0].get("source_event_time")
        or events[0]["sample_time"],
        "source_event_time_last": events[-1].get("source_event_time")
        or events[-1]["sample_time"],
    }

    try:
        steps, duplicate_rows, copy_stats = _run_episode_persisted(
            conn,
            cfg=engine_cfg,
            episode_id=episode_id,
            sample_list=samples,
            now_fn=lambda: now_iso,
        )
    except Exception as exc:
        conn.close()
        return EXIT_TECH_ERROR, {
            **base_evidence,
            "ended_at": _now_iso(),
            "status": "blocked",
            "stage": "episode_engine",
            "errors": [f"engine raised: {exc}"],
        }

    ended_at = _now_iso()
    summary = episode_summary(
        steps,
        pool_meta=pool_meta,
        capital_usd=capital_usd,
    )
    summary["ledger_duplicate_rows"] = int(duplicate_rows or 0)
    summary["copied"] = copy_stats
    summary["event_count"] = len(events)
    summary["first_event_time"] = events[0]["sample_time"]
    summary["last_event_time"] = events[-1]["sample_time"]
    try:
        _persist_episode_summary(
            conn,
            episode_id=episode_id,
            started_at=started_at,
            ended_at=ended_at,
            pool=adapter.pool_address,
            position_usd=position_usd,
            capital_usd=capital_usd,
            summary=summary,
        )
        _write_cursor(
            conn,
            chain_id=adapter.chain_id,
            pool_address=adapter.pool_address,
            last_event_time=events[-1]["sample_time"],
            episode_id=episode_id,
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.close()
        return EXIT_TECH_ERROR, {
            **base_evidence,
            "ended_at": _now_iso(),
            "status": "blocked",
            "stage": "ledger_commit",
            "errors": [f"cannot commit ledger: {exc}"],
        }

    conn.close()

    return EXIT_NO_TRADE, {
        **base_evidence,
        "ended_at": ended_at,
        "status": "episode",
        "stage": "completed",
        "chain_id": adapter.chain_id,
        "pool_address": adapter.pool_address,
        "cursor_before": cursor_ts,
        "cursor_after": events[-1]["sample_time"],
        "event_count": len(events),
        "first_event_time": events[0]["sample_time"],
        "last_event_time": events[-1]["sample_time"],
        "summary": summary,
        "errors": [],
    }


def run_daemon(cfg_path: str) -> tuple[int, dict[str, Any]]:
    """Single-shot daemon wrapper.  Long-running loops are out of scope per
    OBSERVE_ONLY_DECISION_RULES_CN; this exists so the deployment package's
    binary entry point has a daemon-named symbol without inventing a sleep
    loop that would mask source/cursor regressions.
    """
    return run_once(cfg_path)


def run_demo_episode(
    ledger_db_path: str,
    *,
    n_steps: int = 3,
    capital_usd: Decimal | float | str = 1000,
    position_usd: Decimal | float | str = 100,
) -> tuple[int, dict[str, Any]]:
    """EXPLICIT DEMO entry — NOT production.  Drives the engine against the
    `build_demo_sample_fixture` and persists a rh_episode_summary row so the
    D1 positive control (NAV 1000→990, PnL=-10) remains a verifiable contract.

    Per NEXT_AGENT_TASK_CN.md §1, the production `run_once()` must not use
    this fixture.  Tests that want the D1 math call `run_demo_episode()`
    directly with a tmp ledger path; tests that want the production path
    call `run_once()` with a config that points at a real source.

    Returns (EXIT_NO_TRADE, evidence_dict).
    """
    started_at = "2026-01-01T00:00:00Z"
    episode_id = str(uuid.uuid4())
    capital = Decimal(str(capital_usd))
    position = Decimal(str(position_usd))

    Path(ledger_db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = open_store(ledger_db_path)
    migrate(conn)
    try:
        samples = build_demo_sample_fixture(n_steps=n_steps)
        # D1 fixture: deterministic clock pinned at 2026-01-01; horizon 8760h
        # (1y).  Matches the original positive control shape; production
        # run_once() resolves these from config / source events.
        demo_now = "2026-01-01T00:00:00Z"
        pool_meta = dict(PAPER_POOL_META_FRESH)
        pool_meta["pool_address"] = "0xpool-paper-core"
        engine_cfg = {
            "pool": "0xpool-paper-core",
            "position_usd": position,
            "horizon_hours": 8760,
            "capital_usd": capital,
            "target_mode": "SHADOW_SCENARIO",
            "pool_meta": pool_meta,
            "pool_meta_hash": "h-paper-core",
            "verify_calldata": False,
            "live_db": ":memory:",
            "samples": n_steps,
            "ledger_db": ledger_db_path,
        }
        steps, duplicate_rows, copy_stats = _run_episode_persisted(
            conn,
            cfg=engine_cfg,
            episode_id=episode_id,
            sample_list=samples,
            now_fn=lambda: demo_now,
        )
        ended_at = "2026-01-01T00:02:00Z"
        summary = episode_summary(steps, pool_meta=pool_meta, capital_usd=capital)
        summary["ledger_duplicate_rows"] = int(duplicate_rows or 0)
        summary["copied"] = copy_stats
        summary["event_count"] = len(samples)
        summary["first_event_time"] = samples[0]["sample_time"]
        summary["last_event_time"] = samples[-1]["sample_time"]
        _persist_episode_summary(
            conn,
            episode_id=episode_id,
            started_at=started_at,
            ended_at=ended_at,
            pool="0xpool-paper-core",
            position_usd=position,
            capital_usd=capital,
            summary=summary,
        )
        conn.commit()
    finally:
        conn.close()

    return EXIT_NO_TRADE, {
        "started_at": started_at,
        "ended_at": ended_at,
        "episode_id": episode_id,
        "ledger_db": ledger_db_path,
        "status": "demo_episode",
        "stage": "completed",
        "summary": summary,
        "errors": [],
    }


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

def _print_json(obj: Any) -> None:
    import json
    print(json.dumps(obj, indent=2, default=str))


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(
            "usage: lp_rh_paper_daemon_entry_v1.py "
            "<preflight|status|run-once|run-daemon> <cfg_path>",
            file=sys.stderr,
        )
        return EXIT_TECH_ERROR

    cmd = argv[1]
    cfg_path = argv[2] if len(argv) >= 3 else ""

    if cmd == "preflight":
        ok, errs = preflight(cfg_path)
        _print_json({"ok": ok, "errors": errs})
        return 0 if ok else EXIT_TECH_ERROR

    if cmd == "status":
        _print_json(status(cfg_path))
        return 0

    if cmd in ("run-once", "run_daemon", "run-once-demo"):
        exit_code, evidence = run_once(cfg_path)
        _print_json({"exit_code": exit_code, "evidence": evidence})
        return exit_code

    print(f"unknown command: {cmd}", file=sys.stderr)
    return EXIT_TECH_ERROR


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv))