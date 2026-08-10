#!/usr/bin/env python3
"""Hourly, read-only Tier-C stock-pool shadow observer.

The observer persists actual observations; it never back-dates a snapshot and
never treats DefiLlama's 7d/30d aggregate fields as our 48-hour evidence.  A
pool becomes persistence-eligible only after at least three local observations
span 48 hours and its total APY never falls below 50% of the first observed
high-yield value.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


LLAMA_POOLS_URL = "https://yields.llama.fi/pools"
DEFAULT_INTERVAL_SECONDS = 3600
PERSISTENCE_HOURS = 48.0
MIN_SAMPLES = 3
MIN_RETENTION_FRAC = 0.50


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("records", "rows", "pools", "data"):
            if isinstance(payload.get(key), list):
                return _records(payload[key])
    raise ValueError("universe must contain a list of records")


def load_c_ids(path: Path) -> set[str]:
    rows = _records(json.loads(path.read_text()))
    return {
        str(row.get("pool") or row.get("pool_id") or row.get("llama_pool_id"))
        for row in rows
        if str(row.get("tier") or row.get("stock_tier") or "").upper() == "C"
        and (row.get("pool") or row.get("pool_id") or row.get("llama_pool_id"))
    }


def fetch_llama(url: str = LLAMA_POOLS_URL) -> list[dict[str, Any]]:
    request = urllib.request.Request(url, headers={"User-Agent": "lpbot-stock-shadow/1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return _records(json.load(response))


def initialize(db: sqlite3.Connection) -> None:
    db.execute("""
        CREATE TABLE IF NOT EXISTS observations (
            pool_id TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            observed_hour TEXT NOT NULL,
            symbol TEXT NOT NULL,
            apy_base REAL,
            apy_reward REAL,
            apy_total REAL,
            tvl_usd REAL,
            volume_usd_1d REAL,
            swap_count INTEGER,
            swap_count_source TEXT,
            PRIMARY KEY(pool_id, observed_hour)
        )
    """)
    db.commit()


def persist_snapshot(
    db: sqlite3.Connection,
    c_ids: set[str],
    llama_rows: Iterable[Mapping[str, Any]],
    *,
    observed_at: datetime | None = None,
    swap_counts: Mapping[str, int] | None = None,
) -> int:
    now = (observed_at or _utc_now()).astimezone(timezone.utc)
    hour = now.replace(minute=0, second=0, microsecond=0).isoformat()
    inserted = 0
    for row in llama_rows:
        pool_id = str(row.get("pool") or "")
        if pool_id not in c_ids:
            continue
        swap_count = (swap_counts or {}).get(pool_id)
        cursor = db.execute("""
            INSERT OR IGNORE INTO observations(
                pool_id, observed_at, observed_hour, symbol, apy_base,
                apy_reward, apy_total, tvl_usd, volume_usd_1d,
                swap_count, swap_count_source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(pool_id, observed_hour) DO UPDATE SET
                observed_at=excluded.observed_at,
                apy_base=excluded.apy_base,
                apy_reward=excluded.apy_reward,
                apy_total=excluded.apy_total,
                tvl_usd=excluded.tvl_usd,
                volume_usd_1d=excluded.volume_usd_1d,
                swap_count=COALESCE(excluded.swap_count, observations.swap_count),
                swap_count_source=CASE WHEN excluded.swap_count IS NOT NULL
                    THEN excluded.swap_count_source ELSE observations.swap_count_source END
        """, (
            pool_id, now.isoformat(), hour, str(row.get("symbol") or ""),
            row.get("apyBase"), row.get("apyReward"), row.get("apy"),
            row.get("tvlUsd"), row.get("volumeUsd1d"), swap_count,
            "solana_stage2" if swap_count is not None else "unavailable_fail_closed",
        ))
        inserted += int(cursor.rowcount > 0)
    db.commit()
    return inserted


def pool_persistence(db: sqlite3.Connection, pool_id: str) -> dict[str, Any]:
    rows = db.execute("""
        SELECT observed_at, apy_base, apy_reward, apy_total, tvl_usd,
               volume_usd_1d, swap_count
        FROM observations WHERE pool_id=? ORDER BY observed_at
    """, (pool_id,)).fetchall()
    if not rows:
        return {
            "pool_id": pool_id, "sample_count": 0, "span_hours": 0.0,
            "threshold_held": False, "eligible_48h": False,
            "decay_curve": [], "cause": "NO_OBSERVATION",
        }
    timestamps = [datetime.fromisoformat(row[0]) for row in rows]
    span = (timestamps[-1] - timestamps[0]).total_seconds() / 3600.0
    apys = [float(row[3]) for row in rows if row[3] is not None]
    baseline = apys[0] if apys else None
    floor = baseline * MIN_RETENTION_FRAC if baseline is not None else None
    held = bool(apys) and baseline > 0 and len(apys) == len(rows) and min(apys) >= floor
    eligible = len(rows) >= MIN_SAMPLES and span >= PERSISTENCE_HOURS and held
    curve = []
    for row, stamp in zip(rows, timestamps):
        apy = float(row[3]) if row[3] is not None else None
        curve.append({
            "hours": round((stamp - timestamps[0]).total_seconds() / 3600.0, 6),
            "apy": apy,
            "retained_fraction": (apy / baseline if apy is not None and baseline else None),
            "tvl_usd": row[4], "volume_usd_1d": row[5], "swap_count": row[6],
        })
    cause = "INSUFFICIENT_OBSERVATION_WINDOW"
    if len(rows) >= 2:
        first, last = rows[0], rows[-1]
        if first[4] and last[4] is not None and float(last[4]) < float(first[4]) * 0.5:
            cause = "POSSIBLE_RUG_OR_LIQUIDITY_WITHDRAWAL"
        elif first[2] and last[2] is not None and float(last[2]) < float(first[2]) * 0.5:
            cause = "POSSIBLE_REWARD_EXHAUSTION"
        elif baseline and last[3] is not None and float(last[3]) < baseline * 0.5:
            cause = "YIELD_DECAY_CAUSE_UNRESOLVED"
        elif span >= PERSISTENCE_HOURS:
            cause = "PERSISTED_NO_DECAY_EVENT"
    return {
        "pool_id": pool_id, "sample_count": len(rows), "span_hours": span,
        "baseline_apy": baseline, "retention_floor_apy": floor,
        "threshold_held": held, "eligible_48h": eligible,
        "decay_curve": curve, "cause": cause,
    }


def build_report(db: sqlite3.Connection, c_ids: set[str]) -> dict[str, Any]:
    pools = [pool_persistence(db, pool_id) for pool_id in sorted(c_ids)]
    observed = sum(row["sample_count"] > 0 for row in pools)
    return {
        "generated_at": _utc_now().isoformat(),
        "policy": {
            "min_span_hours": PERSISTENCE_HOURS,
            "min_samples": MIN_SAMPLES,
            "min_retained_fraction": MIN_RETENTION_FRAC,
            "defillama_rolling_fields_count_as_local_observations": False,
        },
        "c_pool_count": len(c_ids), "observed_pool_count": observed,
        "eligible_48h_count": sum(row["eligible_48h"] for row in pools),
        "pools": pools,
    }


def load_swap_counts(path: Path | None) -> dict[str, int]:
    if path is None:
        return {}
    payload = json.loads(path.read_text())
    output = {}
    for row in payload.get("results") or []:
        replay = row.get("swap_replay") or {}
        pool_id = row.get("llama_pool_id")
        if pool_id and replay.get("status") in {"PASS", "NO_SWAP_IN_BOUNDED_SAMPLE"}:
            output[str(pool_id)] = int(replay.get("swap_count", 0))
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--interval-seconds", type=int, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--rounds", type=int, default=1,
                        help="0 means continuous; default one read-only sample")
    parser.add_argument("--llama-url", default=LLAMA_POOLS_URL)
    parser.add_argument("--stage2-swap-evidence", type=Path,
                        help="optional bounded real-swap replay JSON; absent pools remain unavailable")
    args = parser.parse_args()
    if args.interval_seconds < 60 or args.rounds < 0:
        parser.error("interval must be >=60 and rounds >=0")
    args.db.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    c_ids = load_c_ids(args.universe)
    swap_counts = load_swap_counts(args.stage2_swap_evidence)
    with sqlite3.connect(args.db) as db:
        initialize(db)
        iteration = 0
        while args.rounds == 0 or iteration < args.rounds:
            persist_snapshot(db, c_ids, fetch_llama(args.llama_url), swap_counts=swap_counts)
            args.report.write_text(json.dumps(build_report(db, c_ids), indent=2) + "\n")
            iteration += 1
            if args.rounds == 0 or iteration < args.rounds:
                time.sleep(args.interval_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
