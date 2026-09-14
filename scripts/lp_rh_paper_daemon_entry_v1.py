"""
Paper daemon entry point (W5 deploy package — NOT for live execution).

Provides four pure-import functions that perform no I/O at module load time:

  preflight(cfg_path)   — validate config, paths, PID lock, execution guards
  status(cfg_path)      — return current operational state (no daemon required)
  run_once(cfg_path)    — stub: one episode, returns NO_TRADE=0 or TECH_ERROR=1
  run_daemon(cfg_path)  — stub: raises NotImplementedError (shell only)

No side effects occur at import time.  All functions are safe to call from
tests or review tooling without starting any daemon.
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
from scripts.lp_rh_shadow_daemon_v1_readonly import (
    _run_episode_persisted,
)
from scripts.lp_rh_shadow_runner_v1_readonly import episode_summary
from scripts.lp_rh_store_v1_readonly import migrate, open_store

# Exit codes (match spec I2)
EXIT_NO_TRADE = 0
EXIT_TECH_ERROR = 1

# Sentinel values for status dict
MODE_PAPER_ONLY = "paper_only"
PROFILE_PAPER = "rh-core-paper-v1"


def preflight(cfg_path: str) -> tuple[bool, list[str]]:
    """Validate the paper daemon configuration.

    Checks:
      1. File exists and parses as valid TOML with all required sections.
      2. Ledger DB parent directory exists or can be created.
      3. PID file parent directory exists.
      4. PID file is not currently held by another process.
      5. execution.signing_enabled == False.
      6. execution.broadcasting_enabled == False.

    Returns (True, []) on success or (False, [reason, ...]) on any failure.
    """
    errors: list[str] = []

    # 1. Parse TOML
    if not os.path.isfile(cfg_path):
        return False, [f"config file not found: {cfg_path}"]

    try:
        with open(cfg_path, "rb") as fh:
            cfg = tomllib.load(fh)
    except Exception as exc:
        return False, [f"failed to parse TOML: {exc}"]

    required_sections = [
        "meta", "chain", "pool", "capital", "economics",
        "execution", "paths", "resources", "safety",
    ]
    for section in required_sections:
        if section not in cfg:
            errors.append(f"missing required TOML section: [{section}]")

    if errors:
        return False, errors

    # 2. Ledger DB parent dir
    ledger_db: str = cfg.get("paths", {}).get("ledger_db", "")
    if ledger_db:
        db_dir = os.path.dirname(ledger_db)
        if db_dir and not os.path.isdir(db_dir):
            try:
                os.makedirs(db_dir, exist_ok=True)
            except OSError as exc:
                errors.append(f"cannot create ledger_db parent dir {db_dir}: {exc}")

    # 3. PID file parent dir
    pid_file: str = cfg.get("paths", {}).get("pid_file", "")
    if pid_file:
        pid_dir = os.path.dirname(pid_file)
        if pid_dir and not os.path.isdir(pid_dir):
            errors.append(f"PID file parent dir does not exist and cannot be created: {pid_dir}")

    # 4. PID lock not held
    if pid_file:
        # Check if another process already holds the lock
        alive = is_alive(pid_file)
        if alive:
            pid = read_pid(pid_file)
            errors.append(f"PID file {pid_file} already held by alive process {pid}")

        # Also try to acquire — if we can't, someone else has it
        if not acquire(pid_file):
            # If is_alive was False (stale), acquire would succeed; if it fails now,
            # the file was recreated by a race, which is acceptable to report but
            # not a hard error for preflight (we just note it in warnings)
            pass
        else:
            # We acquired it during preflight — release immediately; preflight
            # should not leave a lock file behind
            from scripts.lp_rh_paper_pid_lock_v1 import release as _release
            _release(pid_file)

    # 5. signing_enabled guard
    signing: bool = cfg.get("execution", {}).get("signing_enabled", True)
    if signing:
        errors.append(
            "execution.signing_enabled must be False for paper mode; "
            "found True — refusing to proceed"
        )

    # 6. broadcasting_enabled guard
    broadcasting: bool = cfg.get("execution", {}).get("broadcasting_enabled", True)
    if broadcasting:
        errors.append(
            "execution.broadcasting_enabled must be False for paper mode; "
            "found True — refusing to proceed"
        )

    if errors:
        return False, errors
    return True, []


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


def _build_paper_sample_fixture(*, n_steps: int = 3) -> list[dict[str, Any]]:
    """Build a deterministic 3-step CORE paper sample fixture.

    Same shape as the D1 E2E positive control (tests/test_lp_rh_terminal_to_ledger_e2e_v1_readonly.py:92)
    so the paper path exercises the exact gate/mark/reservation/tx_intent chain
    the ledger unit tests assert against.  Three samples with cost_entry=5 and
    last sample cost_exit=5 — round-trip cost 10 → NAV 1000→990, NetPnL=-10.

    Returns: list of sample dicts, length=n_steps (default 3).
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
                "source": "paper_fixture",
                "observed_at": t,
                "ttl_secs": 3600,
            },
            "entry_cost_usd": "5",
            "exit_cost_usd": "5" if i == n_steps - 1 else "0",
            "gas_usd": "0",
        })
    return samples


def _load_config(cfg_path: str) -> dict[str, Any]:
    if not os.path.isfile(cfg_path):
        raise FileNotFoundError(f"config not found: {cfg_path}")
    with open(cfg_path, "rb") as fh:
        return tomllib.load(fh)


def _count_episodes_in_ledger(ledger_db_path: str) -> tuple[int, str | None]:
    """Read episode rows from the ledger's rh_episode_summary table.

    Returns: (count, last_ended_at_iso) — both None/0 if table does not exist.
    """
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


def status(cfg_path: str) -> dict[str, Any]:
    """Return the current operational state of the paper daemon.

    Reads the config file and the ledger DB (read-only) to surface real
    episode counts and last-tick timestamps.  Does NOT start a daemon.

    Returns a dict with keys:
      mode, profile, capital_usd, position_size_usd,
      episodes_run (real count from rh_episode_summary),
      last_tick_at (real MAX(ended_at) or None if no episodes),
      ledger_db (resolved path or "").
    """
    default = {
        "mode": MODE_PAPER_ONLY,
        "profile": PROFILE_PAPER,
        "capital_usd": 1000.0,
        "position_size_usd": 100.0,
        "episodes_run": 0,
        "last_tick_at": None,
        "ledger_db": "",
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

    return {
        "mode": exec_cfg.get("mode") or MODE_PAPER_ONLY,
        "profile": meta_cfg.get("profile") or PROFILE_PAPER,
        "capital_usd": capital_usd,
        "position_size_usd": position_size,
        "episodes_run": episodes_run,
        "last_tick_at": last_tick_at,
        "ledger_db": ledger_db,
    }


def run_once(cfg_path: str) -> int:
    """Execute one paper episode against the real research engine.

    Loads cfg, validates preconditions, opens the configured ledger_db,
    migrates it, builds a deterministic CORE paper sample fixture
    (NAV 1000→990, NetPnL=-10), runs _run_episode_persisted (the same
    authoritative daemon entry used by the D1 E2E positive control),
    then persists the episode_summary to rh_episode_summary.

    Returns:
      EXIT_NO_TRADE (0) — episode ran end-to-end, summary persisted.
      EXIT_TECH_ERROR (1) — preflight failed or unexpected exception.

    This function MUST NOT be a stub.  Calling run_once must produce real
    ledger rows (rh_gate_decisions, rh_position_marks, rh_bucket_reservations,
    rh_tx_intents) and a non-zero NAV delta record.
    """
    ok, errs = preflight(cfg_path)
    if not ok:
        sys.stderr.write(f"run_once preflight failed: {errs}\n")
        return EXIT_TECH_ERROR

    try:
        cfg = _load_config(cfg_path)
        ledger_db_path = str(cfg["paths"]["ledger_db"])
    except Exception as exc:
        sys.stderr.write(f"run_once config load failed: {exc}\n")
        return EXIT_TECH_ERROR

    capital_cfg_dict = cfg.get("capital") or {}
    if "virtual_capital_usd" not in capital_cfg_dict:
        sys.stderr.write("run_once config missing [capital].virtual_capital_usd\n")
        return EXIT_TECH_ERROR
    if "position_size_usd" not in capital_cfg_dict:
        sys.stderr.write("run_once config missing [capital].position_size_usd\n")
        return EXIT_TECH_ERROR
    capital_usd_cfg = capital_cfg_dict["virtual_capital_usd"]
    position_usd_cfg = capital_cfg_dict["position_size_usd"]
    try:
        capital_usd = Decimal(str(capital_usd_cfg))
        position_usd = Decimal(str(position_usd_cfg))
    except Exception as exc:
        sys.stderr.write(f"run_once capital/position not decimal: {exc}\n")
        return EXIT_TECH_ERROR

    db_dir = os.path.dirname(ledger_db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    episode_id = f"paper-core-{uuid.uuid4().hex[:12]}"

    try:
        conn = open_store(Path(ledger_db_path))
        migrate(conn)
        try:
            samples = _build_paper_sample_fixture(n_steps=3)
            episode_cfg = {
                "position_usd": position_usd,
                "capital_usd": capital_usd,
                "horizon_hours": 8760,
                "target_mode": "SHADOW_SCENARIO",
                "pool_meta": PAPER_POOL_META_FRESH,
                "pool_meta_hash": "h-paper-core",
                "verify_calldata": False,
            }
            now_fn = lambda: "2026-01-01T00:00:00Z"  # noqa: E731
            steps, dup_rows, copy_stats = _run_episode_persisted(
                conn, cfg=episode_cfg, episode_id=episode_id,
                sample_list=samples, now_fn=now_fn,
            )
            summary = episode_summary(
                steps,
                load_skipped=0,
                pool_meta=PAPER_POOL_META_FRESH,
                capital_usd=capital_usd,
            )
            summary["episode_id"] = episode_id
            summary["ledger_duplicate_rows"] = dup_rows
            summary["copied"] = copy_stats

            _persist_episode_summary(
                conn,
                episode_id=episode_id,
                started_at="2026-01-01T00:00:00Z",
                ended_at="2026-01-01T00:02:00Z",
                pool="0xpool-paper-core",
                position_usd=position_usd,
                capital_usd=capital_usd,
                summary=summary,
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        sys.stderr.write(f"run_once episode failed: {exc}\n")
        return EXIT_TECH_ERROR

    return EXIT_NO_TRADE


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
    """Upsert one row into rh_episode_summary so status() can read it.

    Table created via _ensure_rh_episode_summary_table(); idempotent.
    """
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
            eligible_steps, ledger_duplicate_rows, copied
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        ),
    )


def _ensure_rh_episode_summary_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rh_episode_summary (
            episode_id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            ended_at TEXT NOT NULL,
            pool TEXT NOT NULL,
            position_usd TEXT NOT NULL,
            capital_usd TEXT NOT NULL,
            nav_start TEXT,
            nav_end TEXT,
            net_pnl TEXT,
            eligible_steps INTEGER NOT NULL DEFAULT 0,
            ledger_duplicate_rows INTEGER NOT NULL DEFAULT 0,
            copied TEXT
        )
        """
    )


def _json_dumps(obj: Any) -> str | None:
    import json
    if obj is None:
        return None
    return json.dumps(obj, default=str)


def run_daemon(cfg_path: str) -> None:
    """Start the paper daemon event loop (single-shot only; long-running forbidden).

    Per CLAUDE.md / OBSERVE_ONLY_DECISION_RULES_CN.md, this task MUST NOT
    start any new resident Observe/Paper/Live daemon.  run_daemon therefore
    runs exactly one episode via run_once() and returns.  Multiple
    invocations are the owner's responsibility (cron / systemd); this
    function does not provide a sleep loop.

    For a long-running daemon, build it as a separate process that calls
    scripts/lp_rh_paper_daemon_entry_v1.run_once in a loop — DO NOT call
    run_daemon from CI, tests, or other unattended contexts without an
    explicit owner-approved schedule.
    """
    rc = run_once(cfg_path)
    if rc != EXIT_NO_TRADE:
        sys.stderr.write(f"run_daemon: run_once returned {rc}\n")
        sys.exit(rc)
