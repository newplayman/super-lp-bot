#!/usr/bin/env python3
"""RH-05e-rec: live premium recorder (read-only, no signing, no broadcast).

Appends a time series of (chain price vs reference price) premium samples so
that RH-05e's analysis module has real data to work on.  A single snapshot
cannot distinguish a mean-reverting premium (a real, repeating LVR drain) from
a persistent offset (a one-off repricing of inventory); those push NetCover in
opposite directions, so the series is required before STOCK can enter shadow.

Writes its OWN database file (reports/lp_rh/premium.db).  The Stage A collector
is the single writer of scanner.db and is NOT touched.

Correctness rules this file must obey (each one is a bug already caught here):
  * Never assume token0 is the quote token.  Uniswap orders tokens by address.
    Resolve token0()/token1() on chain and invert the price when needed.
  * Normalise for decimals: P = (sqrtP/2**96)**2 * 10**d0 / 10**d1.
  * Missing inputs are recorded as NULL, never as 0.
  * Sleep to a deadline measured from the round's START, or the period drifts.
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

getcontext().prec = 60

RPC = os.environ.get("RH_RPC_PRIMARY", "https://rpc.mainnet.chain.robinhood.com")
PRICES_URL = "https://api.robinhood.com/rhj/prices"
UA = "lp-bot-rh-readonly/1.0"
_STOP = {"flag": False}

# symbol -> (pool, stock token).  Deepest USDG-quoted pool per symbol, from
# STOCK_POOLS_TVL.json (2026-09-08 live scan).  Pools with liquidity == 0 are
# uninitialised and return nonsense prices, so they are never selected.
WATCH = {
    "SGOV": ("0xfab520051f96f4d2a32c22b6a3dd7fffdf231bfe", "0x92FD66527192E3e61d4DDd13322Aa222DE86F9B5"),
    "GLD":  ("0x7a6a053eccf1446a2633e05aa6d40d09381997ec", "0xC9a981FEE1F9DEc688bb123ccDeCc63D0deBFC4e"),
    "SPY":  ("0xa7bb1ac63bbab0c44316e6c8c455213441689167", "0x117cc2133c37B721F49dE2A7a74833232B3B4C0C"),
    "QQQ":  ("0xd60a5d14db690b7afad71f76b108071d7175597d", "0xD5f3879160bc7c32ebb4dC785F8a4F505888de68"),
    "NVDA": ("0xd4eb21209c4d6093f80b5b84f5c45cc093ea14a3", "0xd0601CE157Db5bdC3162BbaC2a2C8aF5320D9EEC"),
    "AMC":  ("0xaa34fea710a1a737840329051d81d3b0b7c564d5", "0x05a3d1Cd21d0C88145E82600E62e7E496e0F222B"),
}

SEL = {          # keccak256(sig)[:4], precomputed; no keccak dependency needed.
    "token0": "0x0dfe1681", "token1": "0xd21220a7", "decimals": "0x313ce567",
    "symbol": "0x95d89b41", "slot0": "0x3850c7bd",
    # PRD §9.5's currentMultiplier()/oraclePaused() both revert on chain; these
    # are the selectors actually present in the shared beacon implementation.
    "multiplier": "0xa60bf13d", "paused": "0x5c975abb",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS rh_premium_samples (
  symbol TEXT NOT NULL, sample_time TEXT NOT NULL, pool TEXT NOT NULL,
  block INTEGER, sqrt_price_x96 TEXT, token0_is_quote INTEGER,
  quote_symbol TEXT, token_paused INTEGER,
  chain_price_usd TEXT, reference_bid TEXT, reference_ask TEXT,
  reference_mid TEXT, multiplier TEXT, reference_token_price TEXT,
  premium_bps TEXT, reference_generated_at TEXT, reference_age_secs REAL,
  is_trading_halt INTEGER, status TEXT NOT NULL, error TEXT,
  PRIMARY KEY (symbol, sample_time));
CREATE INDEX IF NOT EXISTS ix_prem_time ON rh_premium_samples(sample_time);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _rpc(method: str, params: list, timeout: float = 12.0):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                       "params": params}).encode()
    req = urllib.request.Request(RPC, data=body,
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as fh:
        out = json.loads(fh.read().decode())
    if "error" in out:
        raise RuntimeError(str(out["error"])[:200])
    return out["result"]


def _call(to: str, selector: str) -> str:
    return _rpc("eth_call", [{"to": to, "data": selector}, "latest"])


def _u(hexstr: str, word: int = 0) -> int:
    raw = hexstr[2:]
    return int(raw[word * 64:(word + 1) * 64] or "0", 16)


def _addr(hexstr: str) -> str:
    return "0x" + hexstr[2:][24:64]


def _str_ret(hexstr: str) -> str:
    """Decode a dynamic string return, falling back to bytes32."""
    raw = bytes.fromhex(hexstr[2:])
    if len(raw) >= 64:
        n = int.from_bytes(raw[32:64], "big")
        if 0 < n <= len(raw) - 64:
            return raw[64:64 + n].decode("utf-8", "replace")
    return raw.rstrip(b"\x00").decode("utf-8", "replace")


def resolve_pool(pool: str, stock_token: str) -> dict:
    """Resolve token roles ONCE. Never assume the quote token is token0.

    Returns dict with t0/t1/d0/d1/quote_symbol/token0_is_quote, or raises.
    """
    t0 = _addr(_call(pool, SEL["token0"]))
    t1 = _addr(_call(pool, SEL["token1"]))
    st = stock_token.lower()
    if st not in (t0, t1):
        raise RuntimeError(f"stock token {st} is neither token0 {t0} nor token1 {t1}")
    token0_is_quote = (t0 != st)
    quote = t0 if token0_is_quote else t1
    d0 = _u(_call(t0, SEL["decimals"]))
    d1 = _u(_call(t1, SEL["decimals"]))
    try:
        qsym = _str_ret(_call(quote, SEL["symbol"]))
    except Exception:
        qsym = "UNKNOWN"
    return {"t0": t0, "t1": t1, "d0": d0, "d1": d1, "quote": quote,
            "quote_symbol": qsym, "token0_is_quote": token0_is_quote}


def chain_price_usd(sqrt_price_x96: int, meta: dict):
    """Stock price in USD from sqrtPriceX96, decimals-normalised and un-inverted.

    P = (sqrtP/2**96)**2 * 10**d0 / 10**d1  is token1-per-token0 in human units.
    If token0 is the quote, P is stock-per-USD and must be inverted.  Returns
    None (never 0) when the value is not computable.
    """
    if not sqrt_price_x96:
        return None
    q = Decimal(sqrt_price_x96) / (Decimal(2) ** 96)
    p = (q * q) * (Decimal(10) ** meta["d0"]) / (Decimal(10) ** meta["d1"])
    if p <= 0:
        return None
    return (Decimal(1) / p) if meta["token0_is_quote"] else p


def fetch_prices(attempts: int = 4) -> dict:
    """GET /rhj/prices -> {SYMBOL: record}. Server-side generatedAt is kept.

    The endpoint rate-limits on bursts (HTTP 429 seen while probing back to
    back; the same URLs returned 200 moments later), so back off 5/15/45/90s
    rather than losing the whole cycle's reference prices.  One call serves all
    six symbols, so a 180s period is ~480 free requests/day.
    """
    req = urllib.request.Request(PRICES_URL, headers={"User-Agent": UA,
                                                      "Accept": "application/json"})
    last = None
    for i in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=20) as fh:
                payload = json.loads(fh.read().decode())
            break
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code not in (429, 500, 502, 503, 504) or i == attempts - 1:
                raise
            time.sleep(min(90.0, 5.0 * (3 ** i)))
        except Exception as exc:
            last = exc
            if i == attempts - 1:
                raise
            time.sleep(min(90.0, 5.0 * (3 ** i)))
    else:
        raise RuntimeError(f"prices unavailable: {last}")
    if isinstance(payload, list):
        rows = payload
    else:                      # observed container key is "quotes" (194 rows)
        rows = payload.get("quotes")
        if rows is None:       # tolerate a rename: take the first list value
            rows = next((v for v in payload.values() if isinstance(v, list)), [])
    out = {}
    for r in rows:
        s = r.get("tokenSymbol") or r.get("symbol")
        if s:
            out[s] = r
    return out


def _age_secs(generated_at) -> float | None:
    if not generated_at:
        return None
    try:                      # nanosecond precision: trim to microseconds
        t = str(generated_at).replace("Z", "+00:00")
        if "." in t:
            head, frac = t.split(".", 1)
            off = ""
            for mark in ("+", "-"):
                if mark in frac:
                    frac, off = frac.split(mark, 1)
                    off = mark + off
                    break
            t = f"{head}.{frac[:6]}{off}"
        return (datetime.now(timezone.utc) - datetime.fromisoformat(t)).total_seconds()
    except Exception:
        return None


def _dec(v):
    if v is None:
        return None
    try:
        d = Decimal(str(v))
        return d if d.is_finite() else None
    except Exception:
        return None


def sample_one(symbol: str, pool: str, meta: dict, ref: dict | None) -> dict:
    """One (symbol, tick) sample. Any missing piece stays None, never 0."""
    row = {"symbol": symbol, "sample_time": _now(), "pool": pool,
           "token0_is_quote": 1 if meta["token0_is_quote"] else 0,
           "quote_symbol": meta["quote_symbol"],
           "status": "COMPUTED", "error": None}
    try:                       # PRD: a failed read is UNKNOWN, never "not paused"
        row["token_paused"] = int(bool(_u(_call(meta["stock_token"], SEL["paused"]))))
    except Exception:
        row["token_paused"] = None
    try:
        row["block"] = int(_rpc("eth_blockNumber", []), 16)
        sqrt_p = _u(_call(pool, SEL["slot0"]))
        row["sqrt_price_x96"] = str(sqrt_p)
        row["chain_price_usd"] = chain_price_usd(sqrt_p, meta)
    except Exception as exc:
        row.update(status="INPUTS_UNAVAILABLE", error=f"chain:{exc}"[:200])
    if ref is None:
        row["status"] = "INPUTS_UNAVAILABLE"
        row["error"] = ((row.get("error") or "") + "|ref:missing")[:200]
    else:
        bid, ask = _dec(ref.get("bid")), _dec(ref.get("ask"))
        row["reference_bid"], row["reference_ask"] = bid, ask
        row["reference_mid"] = ((bid + ask) / 2) if (bid and ask) else None
        row["reference_generated_at"] = ref.get("generatedAt")
        row["reference_age_secs"] = _age_secs(ref.get("generatedAt"))
        halt = ref.get("isTradingHalt")
        row["is_trading_halt"] = None if halt is None else int(bool(halt))
    try:
        row["multiplier"] = _dec(_u(_call(meta["stock_token"],
                                         SEL["multiplier"]))) / (Decimal(10) ** 18)
    except Exception as exc:
        row["multiplier"] = None
        row["error"] = ((row.get("error") or "") + f"|mult:{exc}")[:200]
    mid, mult, cp = row.get("reference_mid"), row.get("multiplier"), row.get("chain_price_usd")
    if mid is not None and mult is not None:
        row["reference_token_price"] = mid * mult
    else:
        row["reference_token_price"] = None
    rtp = row["reference_token_price"]
    if cp is not None and rtp is not None and rtp > 0:
        row["premium_bps"] = (cp / rtp - 1) * Decimal(10000)
    else:
        row["premium_bps"] = None
        if row["status"] == "COMPUTED":
            row["status"] = "INPUTS_UNAVAILABLE"
    return row


COLS = ("symbol", "sample_time", "pool", "block", "sqrt_price_x96",
        "token0_is_quote", "quote_symbol", "token_paused", "chain_price_usd", "reference_bid", "reference_ask",
        "reference_mid", "multiplier", "reference_token_price", "premium_bps",
        "reference_generated_at", "reference_age_secs", "is_trading_halt",
        "status", "error")


def _write(conn, rows) -> None:
    vals = [tuple(str(r[c]) if isinstance(r.get(c), Decimal) else r.get(c)
                  for c in COLS) for r in rows]
    conn.executemany(
        f"INSERT OR REPLACE INTO rh_premium_samples ({','.join(COLS)}) "
        f"VALUES ({','.join('?' * len(COLS))})", vals)
    conn.commit()


def _on_signal(signum, frame):
    _STOP["flag"] = True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="RH premium series recorder (read-only)")
    ap.add_argument("--db", default="reports/lp_rh/premium.db")
    ap.add_argument("--period-secs", type=float, default=180.0)
    ap.add_argument("--pid-file", default=None)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args(argv)
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    if args.pid_file:
        Path(args.pid_file).write_text(str(os.getpid()))
    conn = sqlite3.connect(args.db, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)

    meta = {}
    for sym, (pool, token) in WATCH.items():
        try:
            m = resolve_pool(pool, token)
            m["stock_token"] = token
            if m["quote_symbol"] != "USDG":
                print(f"{sym}: SKIP quote={m['quote_symbol']} is not USDG; its "
                      f"price is not USD-denominated", file=sys.stderr, flush=True)
                continue
            meta[sym] = m
            print(f"{sym}: quote={m['quote_symbol']} token0_is_quote={m['token0_is_quote']} "
                  f"d0={m['d0']} d1={m['d1']}", flush=True)
        except Exception as exc:
            print(f"{sym}: SKIP ({exc})", file=sys.stderr, flush=True)
    if not meta:
        print("no resolvable pools", file=sys.stderr)
        return 1

    while not _STOP["flag"]:
        started = time.monotonic()          # deadline from round START, not end
        try:
            prices = fetch_prices()
        except Exception as exc:
            print(f"{_now()} prices fetch failed: {exc}", file=sys.stderr, flush=True)
            prices = {}
        rows = [sample_one(s, WATCH[s][0], meta[s], prices.get(s)) for s in meta]
        _write(conn, rows)
        ok = sum(1 for r in rows if r["status"] == "COMPUTED")
        print(f"{_now()} wrote {len(rows)} rows ({ok} COMPUTED)", flush=True)
        if args.once:
            break
        deadline = started + args.period_secs
        while not _STOP["flag"]:
            left = deadline - time.monotonic()
            if left <= 0:
                break
            time.sleep(min(1.0, left))
    conn.close()
    if args.pid_file:
        try:
            os.unlink(args.pid_file)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
