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
import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
import tomllib
from datetime import datetime, timezone
from typing import Any

# Local dependency — no network, no signing, no broadcasting.
from scripts.lp_rh_paper_pid_lock_v1 import acquire, is_alive, read_pid

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


def status(cfg_path: str) -> dict[str, Any]:
    """Return the current operational state of the paper daemon.

    Reads the config file to surface key fields; does NOT query a running daemon.
    Returns a dict with keys:
      mode, profile, capital_usd, position_size_usd,
      episodes_run (always 0 — no daemon required), last_tick_at (always None)
    """
    default = {
        "mode": MODE_PAPER_ONLY,
        "profile": PROFILE_PAPER,
        "capital_usd": 1000.0,
        "position_size_usd": 100.0,
        "episodes_run": 0,
        "last_tick_at": None,
    }

    if not os.path.isfile(cfg_path):
        return default

    try:
        with open(cfg_path, "rb") as fh:
            cfg = tomllib.load(fh)
    except Exception:
        return default

    capital_cfg = cfg.get("capital") or {}
    exec_cfg = cfg.get("execution") or {}
    meta_cfg = cfg.get("meta") or {}

    capital_value = capital_cfg.get("virtual_capital_usd")
    capital_usd = float(capital_value) if isinstance(capital_value, (int, float)) and capital_value > 0 else 1000.0

    position_value = capital_cfg.get("position_size_usd")
    position_size = float(position_value) if isinstance(position_value, (int, float)) and position_value > 0 else 100.0

    return {
        "mode": exec_cfg.get("mode") or MODE_PAPER_ONLY,
        "profile": meta_cfg.get("profile") or PROFILE_PAPER,
        "capital_usd": capital_usd,
        "position_size_usd": position_size,
        "episodes_run": 0,       # no daemon started by this package
        "last_tick_at": None,    # no daemon started by this package
    }


def run_once(cfg_path: str) -> int:
    """Execute one paper episode (stub — awaiting W1+W2 real implementation).

    Load config, validate preconditions, run one episode loop, persist summary.

    Returns EXIT_NO_TRADE (0) when no candidate passes filters.
    Returns EXIT_TECH_ERROR (1) on any unexpected exception.

    This stub implementation always returns 0 (NO_TRADE) without touching
    any database or making any RPC calls.
    """
    # Validate preconditions before attempting anything
    ok, errs = preflight(cfg_path)
    if not ok:
        # Tech error: config invalid or guards failed
        sys.stderr.write(f"run_once preflight failed: {errs}\n")
        return EXIT_TECH_ERROR

    # ---- STUB ----
    # Real implementation (W1+W2): load pool manifest → scan candidates →
    # run AUDIT → run strategy → risk check → position sizing → episode record.
    # This stub intentionally does nothing.
    #
    # In production: would persist episode summary to ledger_db.
    # ---- STUB ----
    return EXIT_NO_TRADE


def run_daemon(cfg_path: str) -> None:
    """Start the paper daemon event loop (stub — shell only, NOT for execution).

    In production: event-driven sleep loop reading chain events, processing
    episodes, updating ledger, handling SIGTERM gracefully.

    Raises NotImplementedError("W5 deploy package shell only; not for execution").
    """
    raise NotImplementedError(
        "W5 deploy package shell only; not for execution. "
        "Do not call run_daemon — this package is for review and approval only."
    )
