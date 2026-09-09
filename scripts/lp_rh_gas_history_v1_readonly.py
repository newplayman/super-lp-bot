#!/usr/bin/env python3
"""RH gas history: record gas observations over time into a SQLite table.

RH-03e.  RH-03d (``lp_rh_gas_refresh_v1_readonly``) recomputes
``pool_meta.gas_usd_estimate`` from live chain state, but ``pool_meta`` keeps
only the *latest* refresh -- there is no history.  A capital policy sized on a
single gas point goes stale the moment gas moves (measured: gas swung 13% in a
day, 0.5% in seven minutes; the minimal viable position is ~linear in gas).
This package records each refresh into ``rh_gas_observations`` so a
distribution (or a gas ceiling gate) can be derived later.

The module performs no network I/O: chain data arrives through an injected
``rpc_fn(method, params)`` (JSON-RPC envelope, the ``_call`` contract) and
``native_price_usd`` is supplied by the caller (RH-03d convention).  Collection
and computation reuse the accepted RH-03d ``collect_gas_inputs`` /
``compute_refresh`` -- nothing is re-derived here.  All money is stored as
decimal TEXT (``gas_usd``, ``native_price_usd``), never ``float`` (RH-02n).
This package only records; it influences no verdict.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_gas_refresh_v1_readonly import (  # noqa: E402
    collect_gas_inputs,
    compute_refresh,
)
from scripts.lp_rh_capabilities_v1_readonly import (  # noqa: E402
    _default_rpc,
)

RPC_URL = "https://rpc.mainnet.chain.robinhood.com"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    """Make a result JSON-serialisable (Decimal -> str to preserve precision)."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def ensure_table(conn: sqlite3.Connection) -> None:
    """Idempotently create ``rh_gas_observations``.

    Money columns (``gas_usd``, ``native_price_usd``) are decimal TEXT.  The
    primary key ``(observed_at, block_number)`` makes re-observing the same
    block a no-op.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rh_gas_observations (
            observed_at TEXT NOT NULL,
            gas_price_wei INTEGER,
            native_price_usd TEXT,
            gas_usd TEXT,
            block_number INTEGER,
            receipt_n INTEGER,
            source TEXT,
            PRIMARY KEY (observed_at, block_number)
        )
        """
    )
    conn.commit()


def record_observation(
    conn: sqlite3.Connection,
    *,
    rpc_fn: Callable,
    native_price_usd: Any,
    source: str = "gas-history-v1",
    observed_at: Optional[str] = None,
) -> dict:
    """Take one gas observation and record it.

    Reuses RH-03d ``collect_gas_inputs`` + ``compute_refresh``.  When the
    verdict is not ``REFRESHED`` (any input missing/non-positive, or RPC
    failure) nothing is written and ``{"written": False, "verdict": ...}`` is
    returned -- never a 0/placeholder row.  ``observed_at`` defaults to now;
    pass it explicitly to pin the timestamp (e.g. for idempotent re-runs).
    """
    inputs = collect_gas_inputs(rpc_fn)
    refresh = compute_refresh(
        inputs, native_price_usd=native_price_usd, current_estimate=None,
    )
    verdict = refresh.get("verdict")
    new_gas_usd = refresh.get("new_gas_usd")
    if verdict != "REFRESHED" or new_gas_usd is None:
        return {"written": False, "verdict": verdict}

    prov = refresh.get("provenance") or {}
    if observed_at is None:
        observed_at = _utc_now_iso()
    native_str = str(native_price_usd) if native_price_usd is not None else None
    conn.execute(
        "INSERT OR IGNORE INTO rh_gas_observations "
        "(observed_at, gas_price_wei, native_price_usd, gas_usd, "
        "block_number, receipt_n, source) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            observed_at,
            prov.get("gas_price_wei"),
            native_str,
            str(new_gas_usd),
            prov.get("block_number"),
            prov.get("receipt_n"),
            source,
        ),
    )
    conn.commit()
    return {
        "written": True,
        "verdict": verdict,
        "observed_at": observed_at,
        "block_number": prov.get("block_number"),
        "gas_usd": str(new_gas_usd),
    }


def _median(values):
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _percentile(values, pct: Decimal):
    """Linear-interpolation percentile (pct in [0, 100]), Decimal-only."""
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    if n == 1:
        return ordered[0]
    rank = (pct / 100) * (n - 1)
    lower = int(rank)
    upper = min(lower + 1, n - 1)
    fraction = rank - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def summarize(conn: sqlite3.Connection, *, limit: Optional[int] = None) -> dict:
    """Summarise recorded gas observations.  All money values are ``str``.

    ``limit`` restricts to the most recent N observations (by ``observed_at``).
    When ``n == 0`` every statistic is ``None`` (never 0).  Sorting and
    percentiles use ``Decimal`` -- never ``float``.
    """
    if limit is not None:
        rows = conn.execute(
            "SELECT observed_at, gas_usd FROM rh_gas_observations "
            "ORDER BY observed_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT observed_at, gas_usd FROM rh_gas_observations"
        ).fetchall()

    pairs = []
    for observed_at, gas_usd in rows:
        if gas_usd is None:
            continue
        pairs.append((observed_at, Decimal(gas_usd)))
    if not pairs:
        return {
            "n": 0, "min": None, "max": None, "median": None,
            "p90": None, "latest": None, "oldest_at": None, "newest_at": None,
        }

    gas_values = [d for _, d in pairs]
    by_time = sorted(pairs, key=lambda p: p[0])
    return {
        "n": len(pairs),
        "min": str(min(gas_values)),
        "max": str(max(gas_values)),
        "median": str(_median(gas_values)),
        "p90": str(_percentile(gas_values, Decimal(90))),
        "latest": str(by_time[-1][1]),
        "oldest_at": by_time[0][0],
        "newest_at": by_time[-1][0],
    }


def main(argv=None, *, rpc_fn: Optional[Callable] = None) -> int:
    """CLI.  ``--once`` records one observation; ``--summary`` prints the
    summary read-only.  With neither flag it does nothing and returns 0.
    ``rpc_fn`` is injectable for offline tests; the default is the family
    urllib JSON-RPC client."""
    ap = argparse.ArgumentParser(
        description="Record gas observations over time "
                    "(read-only unless --once).")
    ap.add_argument("--db", help="path to the SQLite database")
    ap.add_argument("--native-price-usd", help="native token price in USD")
    ap.add_argument("--once", action="store_true",
                    help="record one observation")
    ap.add_argument("--summary", action="store_true",
                    help="print the summary (read-only)")
    args = ap.parse_args(argv)

    if not args.db:
        return 0

    if args.summary:
        conn = sqlite3.connect(args.db)
        try:
            ensure_table(conn)
            summary = summarize(conn)
        finally:
            conn.close()
        print(json.dumps(_json_safe(summary), indent=2, sort_keys=True))
        return 0

    if args.once:
        if rpc_fn is None:
            rpc_fn = _default_rpc(RPC_URL)
        conn = sqlite3.connect(args.db)
        try:
            ensure_table(conn)
            result = record_observation(
                conn,
                rpc_fn=rpc_fn,
                native_price_usd=args.native_price_usd,
            )
        finally:
            conn.close()
        print(json.dumps(_json_safe(result), indent=2, sort_keys=True))
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
