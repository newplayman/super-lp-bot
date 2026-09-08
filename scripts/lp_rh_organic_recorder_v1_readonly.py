#!/usr/bin/env python3
"""RH-05i: organic-volume long-window recorder (read-only, no signing/broadcast).

Turns RH-05f's one-shot organic-volume snapshot into a cross-day/night series.
Each round fetches one block window of Swap logs for a pool, runs the three
organic-volume metrics, and appends one row to its OWN db (organic.db); the
single-writer scanner.db and premium.db are never touched.  Reuses (not
rewrites) fetch_swaps/to_organic_events and the three organic-volume metrics.

Rules: amounts/ratios stored as TEXT (Decimal strings), never float; missing
values are NULL, never 0; the window advances from the last window_end_block
and, if the gap exceeds provider retention, jumps to head-span and records the
skip in error (never request pruned blocks); sleep to a deadline from the
round's START; on a transient provider error (-32005/429/5xx) back off
8/24/72s and retry, else record that window INPUTS_UNAVAILABLE and continue.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from pathlib import Path

from scripts.lp_rh_swap_logs_v1_readonly import (
    fetch_swaps,
    make_urllib_call_fn,
    to_organic_events,
)
from scripts.lp_rh_organic_volume_v1_readonly import (
    organic_volume_estimate,
    participant_concentration,
    round_trip_volume,
)

getcontext().prec = 60

UA = "lpbot-rh05i/1.0 (read-only research)"
_STOP = {"flag": False}
_BACKOFF_SECS = (8, 24, 72)

SCHEMA = """
CREATE TABLE IF NOT EXISTS rh_organic_windows (
  window_start_block INTEGER NOT NULL,
  window_end_block   INTEGER NOT NULL,
  sample_time TEXT, provider TEXT,
  n_events INTEGER, n_unique_senders INTEGER,
  top1_share TEXT, top5_share TEXT, hhi TEXT, round_trip_share TEXT,
  total_volume TEXT, round_trip_volume TEXT, concentration_excess_volume TEXT,
  organic_fraction TEXT, coverage_frac TEXT,
  fetch_status TEXT, estimate_status TEXT, error TEXT,
  PRIMARY KEY (window_start_block, window_end_block)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _on_signal(signum, frame):
    _STOP["flag"] = True


def _text(value) -> str | None:
    """Decimal/int -> TEXT for storage; None stays NULL (never 0)."""
    if value is None:
        return None
    return str(value)


def _sleep_until(started: float, period_secs: float) -> None:
    """Sleep to a deadline measured from the round's START (not its end)."""
    deadline = started + period_secs
    while not _STOP["flag"]:
        left = deadline - time.monotonic()
        if left <= 0:
            break
        time.sleep(min(1.0, left))


def _last_end_block(conn: sqlite3.Connection) -> int | None:
    row = conn.execute(
        "SELECT MAX(window_end_block) FROM rh_organic_windows"
    ).fetchone()
    return row[0] if row and row[0] is not None else None


def next_window(
    conn: sqlite3.Connection,
    head: int,
    *,
    span_blocks: int,
    max_lookback_blocks: int,
) -> tuple[int, int] | None:
    """Next (lo, hi) window. Empty table -> (head-span, head); else continue
    from the last window_end_block. If the gap exceeds provider retention the
    old blocks may be pruned, so jump to (head-span, head); record_window notes
    the skip in the row's error field."""
    prev_end = _last_end_block(conn)
    if prev_end is None:
        return (head - span_blocks, head)
    if head - prev_end > max_lookback_blocks:
        return (head - span_blocks, head)
    lo = prev_end + 1
    hi = lo + span_blocks
    return (lo, hi)


def record_window(
    conn: sqlite3.Connection,
    pool: str,
    lo: int,
    hi: int,
    call_fn,
    provider: str,
) -> dict:
    """Fetch one window, run the three metrics, and write one row. When
    fetch_status is not COMPLETE the metrics are still computed from the events
    that arrived and labelled honestly, and coverage_frac is carried through
    as-is. A forward jump that skips blocks is noted in the error column."""
    prev_end = _last_end_block(conn)
    error = None
    if prev_end is not None and lo > prev_end + 1:
        error = (f"skipped {lo - 1 - prev_end} blocks between {prev_end + 1} "
                 f"and {lo - 1} (gap beyond provider retention; jumped to head-span)")

    fetch = fetch_swaps(pool, lo, hi, call_fn)
    events = to_organic_events(fetch["events"])
    conc = participant_concentration(events)
    rt = round_trip_volume(events)
    est = organic_volume_estimate(events)

    row = {
        "window_start_block": lo,
        "window_end_block": hi,
        "sample_time": _now(),
        "provider": provider,
        "n_events": est["n_events"],
        "n_unique_senders": est["n_unique_senders"],
        "top1_share": _text(conc["top1_share"]),
        "top5_share": _text(conc["top5_share"]),
        "hhi": _text(conc["hhi"]),
        "round_trip_share": _text(rt["round_trip_share"]),
        "total_volume": _text(est["total_volume"]),
        "round_trip_volume": _text(est["round_trip_volume"]),
        "concentration_excess_volume": _text(est["concentration_excess_volume"]),
        "organic_fraction": _text(est["organic_fraction"]),
        "coverage_frac": _text(fetch["coverage_frac"]),
        "fetch_status": fetch["status"],
        "estimate_status": est["status"],
        "error": error,
    }
    cols = (
        "window_start_block", "window_end_block", "sample_time", "provider",
        "n_events", "n_unique_senders", "top1_share", "top5_share", "hhi",
        "round_trip_share", "total_volume", "round_trip_volume",
        "concentration_excess_volume", "organic_fraction", "coverage_frac",
        "fetch_status", "estimate_status", "error",
    )
    conn.execute(
        "INSERT OR REPLACE INTO rh_organic_windows (%s) VALUES (%s)"
        % (",".join(cols), ",".join("?" * len(cols))),
        tuple(row[c] for c in cols),
    )
    conn.commit()
    return row


def _is_transient(exc: Exception) -> bool:
    """True for provider errors worth a backoff retry: -32005, 429, or 5xx."""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code == 429 or 500 <= exc.code < 600
    msg = str(exc).lower()
    return (
        "-32005" in msg
        or "429" in msg
        or "too many requests" in msg
        or "network is busy" in msg
    )


def make_backoff_call_fn(base, sleep_fn=time.sleep):
    """Wrap a call_fn: on a transient error sleep 8/24/72s and retry; else raise.

    If it still fails after the last backoff the exception propagates, so
    fetch_swaps records the range as failed and the window lands as
    INPUTS_UNAVAILABLE -- the recorder then moves on to the next round.
    """

    def call_fn(params: dict):
        attempt = 0
        while True:
            try:
                return base(params)
            except Exception as exc:
                if not _is_transient(exc) or attempt >= len(_BACKOFF_SECS):
                    raise
                sleep_fn(_BACKOFF_SECS[attempt])
                attempt += 1

    return call_fn


def make_head_fn(rpc_url: str):
    """Build a head_fn returning the latest block number via eth_blockNumber."""

    def head_fn() -> int:
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []}
        ).encode("utf-8")
        request = urllib.request.Request(
            rpc_url,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": UA},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
        if isinstance(body, dict) and body.get("error"):
            raise RuntimeError(str(body["error"]))
        return int(body["result"], 16)

    return head_fn


def main(argv=None, *, call_fn=None, head_fn=None) -> int:
    ap = argparse.ArgumentParser(description="RH organic-volume window recorder (read-only)")
    ap.add_argument("--db", default="reports/lp_rh/organic.db")
    ap.add_argument("--pool", required=True, help="Pool address (0x...)")
    ap.add_argument("--provider-url", default="https://rpc.ordofi.network")
    ap.add_argument("--span-blocks", type=int, default=8800)
    ap.add_argument("--period-secs", type=float, default=900.0)
    ap.add_argument("--max-lookback-blocks", type=int, default=1700000)
    ap.add_argument("--pid-file", default=None)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args(argv)

    if head_fn is None:
        head_fn = make_head_fn(args.provider_url)
    if call_fn is None:
        call_fn = make_backoff_call_fn(make_urllib_call_fn(args.provider_url))

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    if args.pid_file:
        Path(args.pid_file).write_text(str(os.getpid()))
    conn = sqlite3.connect(args.db, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)

    try:
        while not _STOP["flag"]:
            started = time.monotonic()  # deadline from round START, not end
            try:
                head = head_fn()
            except Exception as exc:
                print(f"{_now()} head fetch failed: {exc}", file=sys.stderr, flush=True)
                if args.once:
                    break
                _sleep_until(started, args.period_secs)
                continue
            window = next_window(
                conn, head,
                span_blocks=args.span_blocks,
                max_lookback_blocks=args.max_lookback_blocks,
            )
            lo, hi = window
            try:
                row = record_window(conn, args.pool, lo, hi, call_fn, args.provider_url)
                print(
                    f"{_now()} window [{lo},{hi}] fetch={row['fetch_status']} "
                    f"est={row['estimate_status']} n={row['n_events']}",
                    flush=True,
                )
            except Exception as exc:
                print(f"{_now()} window [{lo},{hi}] failed: {exc}", file=sys.stderr, flush=True)
            if args.once:
                break
            _sleep_until(started, args.period_secs)
    finally:
        conn.close()
        if args.pid_file:
            try:
                os.unlink(args.pid_file)
            except OSError:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
