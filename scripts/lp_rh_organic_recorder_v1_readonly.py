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

A non-COMPLETE window is queued in rh_organic_pending and retried (fewest
attempts first, up to --max-attempts) before the recorder advances, so a gap is
never silently skipped; a COMPLETE window clears it. An explicitly-passed
--span-blocks that is below the span required to cover --period-secs is raised
to that span with a warning (the built-in default is left as-is).
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
from decimal import Decimal, localcontext
from pathlib import Path

# Every module here that imports `scripts.*` needs this: pytest inserts the repo
# root itself, so a module without it passes the whole suite and then fails the
# moment it is run as a script.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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
-- Failed windows that must be retried. A row is inserted when a window lands
-- INPUTS_UNAVAILABLE/PARTIAL and deleted when a retry lands COMPLETE. Rows that
-- reach the attempt cap are kept (not retried) so a permanent gap leaves a trace.
CREATE TABLE IF NOT EXISTS rh_organic_pending (
  window_start_block INTEGER NOT NULL,
  window_end_block   INTEGER NOT NULL,
  first_failed_at TEXT,
  attempts INTEGER NOT NULL DEFAULT 1,
  last_error TEXT,
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


def required_span_blocks(period_secs: float, block_time_secs: float = 0.102,
                         margin: float = 1.15) -> int:
    """Minimum window span so one period of real time is fully covered.

    At ``block_time_secs`` per block, ``period_secs`` of wall-clock elapses
    ``period_secs / block_time_secs`` blocks; the ``margin`` guards against
    block-time variance so the next window never starts behind the head.
    """
    return int(period_secs / block_time_secs * margin)


def _fetch_error_summary(fetch: dict) -> str:
    """Non-empty human summary of a non-COMPLETE fetch, from failed_ranges."""
    fr = fetch["failed_ranges"]
    failed_blocks = sum(b - a + 1 for a, b in fr)
    return (f"fetch_status={fetch['status']}: {len(fr)} failed range(s), "
            f"{failed_blocks} of {fetch['requested_blocks']} blocks uncovered")


def _upsert_pending(conn: sqlite3.Connection, lo: int, hi: int, error: str) -> None:
    """Record a failed window for retry: insert with attempts=1, or bump the
    existing row's attempts and refresh last_error (first_failed_at is kept)."""
    row = conn.execute(
        "SELECT attempts FROM rh_organic_pending "
        "WHERE window_start_block=? AND window_end_block=?", (lo, hi),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE rh_organic_pending SET attempts=attempts+1, last_error=? "
            "WHERE window_start_block=? AND window_end_block=?", (error, lo, hi),
        )
    else:
        conn.execute(
            "INSERT INTO rh_organic_pending "
            "(window_start_block, window_end_block, first_failed_at, attempts, last_error) "
            "VALUES (?,?,?,?,?)", (lo, hi, _now(), 1, error),
        )


def _clear_pending(conn: sqlite3.Connection, lo: int, hi: int) -> None:
    """Drop a window from the retry queue once it lands COMPLETE."""
    conn.execute(
        "DELETE FROM rh_organic_pending WHERE window_start_block=? AND window_end_block=?",
        (lo, hi),
    )


def next_window(
    conn: sqlite3.Connection,
    head: int,
    *,
    span_blocks: int,
    max_lookback_blocks: int,
    max_attempts: int = 5,
) -> tuple[int, int] | None:
    """Next (lo, hi) window. A failed window still in rh_organic_pending is
    retried first (fewest attempts, below the cap) so a gap is never skipped;
    only when nothing is pending does it advance to a new window. Empty table
    -> (head-span, head); else continue from the last window_end_block. If the
    gap exceeds provider retention the old blocks may be pruned, so jump to
    (head-span, head); record_window notes the skip in the row's error field.
    Rows at/above max_attempts are left in the table (a trace) but not retried."""
    row = conn.execute(
        "SELECT window_start_block, window_end_block FROM rh_organic_pending "
        "WHERE attempts < ? ORDER BY attempts ASC, window_start_block ASC LIMIT 1",
        (max_attempts,),
    ).fetchone()
    if row:
        return (row[0], row[1])
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
    that arrived and labelled honestly, coverage_frac is carried through as-is,
    and the error column records why (a failed_ranges summary). A non-COMPLETE
    window is queued in rh_organic_pending for retry; a COMPLETE one clears it.
    A forward jump that skips blocks is noted in the error column."""
    prev_end = _last_end_block(conn)
    error = None
    if prev_end is not None and lo > prev_end + 1:
        error = (f"skipped {lo - 1 - prev_end} blocks between {prev_end + 1} "
                 f"and {lo - 1} (gap beyond provider retention; jumped to head-span)")

    with localcontext() as ctx:
        ctx.prec = 60
        fetch = fetch_swaps(pool, lo, hi, call_fn)
        events = to_organic_events(fetch["events"])
        conc = participant_concentration(events)
        rt = round_trip_volume(events)
        est = organic_volume_estimate(events)

    if fetch["status"] != "COMPLETE":
        fetch_error = _fetch_error_summary(fetch)
        error = f"{error}; {fetch_error}" if error else fetch_error

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
    if fetch["status"] == "COMPLETE":
        _clear_pending(conn, lo, hi)
    else:
        _upsert_pending(conn, lo, hi, error)
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
    ap.add_argument("--span-blocks", type=int, default=None,
                    help="Window size in blocks (default 8800; when explicitly set "
                         "below the span required to cover --period-secs it is raised)")
    ap.add_argument("--period-secs", type=float, default=900.0)
    ap.add_argument("--max-lookback-blocks", type=int, default=1700000)
    ap.add_argument("--max-attempts", type=int, default=5,
                    help="Retry cap for a failed window before it is left as a trace")
    ap.add_argument("--pid-file", default=None)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args(argv)

    # A span explicitly passed on the command line that is too small to cover
    # one period is raised to the required span (with a warning); the built-in
    # default is left as-is so a bare invocation keeps its historical window.
    span_explicit = args.span_blocks is not None
    if args.span_blocks is None:
        args.span_blocks = 8800
    if span_explicit:
        required = required_span_blocks(args.period_secs)
        if args.span_blocks < required:
            print(f"{_now()} warning: --span-blocks {args.span_blocks} < required "
                  f"{required} for --period-secs {args.period_secs}; using {required}",
                  file=sys.stderr, flush=True)
            args.span_blocks = required

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
                max_attempts=args.max_attempts,
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
