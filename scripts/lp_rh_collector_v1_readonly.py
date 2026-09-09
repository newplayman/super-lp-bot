#!/usr/bin/env python3
"""RH forward market-state collector (read-only, unattended 72h capable).

Polls the trusted Robinhood Chain provider for the identity-gated target
pool; per round persists rh_market_states + rh_rpc_health + rh_source_
snapshots. Stdlib urllib only (User-Agent curl/8.5.0); no requests/web3/
solana; never signs/broadcasts/touches wallets; never contacts the untrusted
endpoint (T12); money/price are decimal text (the store rejects floats).

Column semantics (RH-02i): `reference_mid` holds the DEX pool price derived
from sqrtPriceX96, not an external reference price. This collector makes no
REST calls. For chain-price-vs-reference premium analysis use
reports/lp_rh/premium.db (lp_rh_premium_recorder), where the two are
separate columns. `reference_age_secs` is the true age of the sampled block
(now - block timestamp), None when the timestamp is unavailable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_store_v1_readonly import (  # noqa: E402
    DEFAULT_DB_PATH, budget_status, insert_row, migrate, open_store,
)
from scripts.lp_rh_market_session_v1_readonly import (  # noqa: E402
    classify_session,
)

# --- constants -------------------------------------------------------------
RH_RPC_PRIMARY = os.environ.get(
    "RH_RPC_PRIMARY", "https://rpc.mainnet.chain.robinhood.com")
USER_AGENT = "curl/8.5.0"
RPC_TIMEOUT_SECS = 12
CHAIN_ID = 4663

# Identity-gated target pool (RH-01b): token0=WETH, token1=USDG.
POOL = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
TOKEN0 = "0x0Bd7D308f8E1639FAb988df18A8011f41EAcAD73"
TOKEN1 = "0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168"

SEL_SLOT0 = "0x3850c7bd"
SEL_LIQUIDITY = "0x1a686502"
SEL_BALANCE_OF = "0x70a08231"
SEL_DECIMALS = "0x313ce567"

BACKOFF_BASE_SECS = 1.0
BACKOFF_MAX_EXP = 10
MAX_RETRIES_PER_ROUND = 3
BUDGET_CHECK_EVERY = 20

def _utc_now() -> str:
    """UTC RFC3339 with microseconds (keeps per-round PKs unique)."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + "%06dZ" % now.microsecond

def _classify_sample_session(now: str) -> str:
    """Market session for the sample instant (RH-02p).

    ``now`` is the RFC3339 UTC sample_time string written to
    rh_market_states. Unparseable input keeps the historical "UNKNOWN"
    fallback; classify_session's None-input behavior is owned by the
    session module and is never exercised here.
    """
    try:
        dt = datetime.fromisoformat(now.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return "UNKNOWN"
    return classify_session(dt, calendar=None)[0]

def _hex_to_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, int):
        return value
    text = str(value).strip()
    try:
        return int(text, 16) if text.lower().startswith("0x") else int(text, 10)
    except (ValueError, TypeError):
        return None

def _err_text(error: Any) -> str:
    if error is None:
        return ""
    if isinstance(error, dict):
        try:
            return json.dumps(error)
        except (TypeError, ValueError):
            return str(error)
    return str(error)

def _balance_data(pool: str) -> str:
    return SEL_BALANCE_OF + "0" * 24 + pool.lower().replace("0x", "")

def backoff_seconds(fails: int, base: float = BACKOFF_BASE_SECS,
                    max_exp: int = BACKOFF_MAX_EXP) -> float:
    """Exponential backoff, exponent capped (no OverflowError; RH-00b)."""
    exp = min(max(fails - 1, 0), max_exp)
    return base * (2 ** exp)

def is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True

def pid_file_is_free(path: str) -> bool:
    """True if absent/unreadable/stale; False if a live PID holds it (§16.1)."""
    if not os.path.exists(path):
        return True
    try:
        with open(path) as handle:
            pid = int(handle.read().strip())
    except (OSError, ValueError):
        return True
    return not is_pid_alive(pid)

def compute_price_human(sqrt_price_x96: int, dec0: int, dec1: int) -> Decimal:
    """price_token1_per_token0 in human units from sqrtPriceX96."""
    sqrt_price = Decimal(sqrt_price_x96) / (Decimal(2) ** 96)
    price_raw = sqrt_price * sqrt_price
    return price_raw * (Decimal(10) ** dec0) / (Decimal(10) ** dec1)

def price_to_text(price: Decimal) -> str:
    """Plain decimal text (no scientific notation) for the store guard."""
    return format(price.quantize(Decimal("0.000001")), "f")


# --- rpc --------------------------------------------------------------------
def rpc(method: str, params: Optional[list] = None, *, url: str = RH_RPC_PRIMARY,
        timeout: int = RPC_TIMEOUT_SECS) -> Tuple[Any, Any, int]:
    """Return (result, error, latency_ms). A JSON-RPC error is never a 0 (T12)."""
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                       "params": params or []}).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read())
        ms = int((time.time() - started) * 1000)
        if "error" in payload:
            return None, payload["error"], ms
        return payload.get("result"), None, ms
    except Exception as exc:  # noqa: BLE001 transport failure
        return None, {"transport": f"{type(exc).__name__}: {exc}"}, \
            int((time.time() - started) * 1000)


def read_decimals(token: str, rpc_fn: Callable = rpc) -> Optional[int]:
    res, err, _ = rpc_fn("eth_call", [{"to": token, "data": SEL_DECIMALS},
                                      "latest"])
    return _hex_to_int(res) if err is None else None


# --- one round --------------------------------------------------------------
def collect_round(conn, *, dec0: int, dec1: int, last_good_block: Optional[int],
                  rpc_fn: Callable = rpc,
                  now_fn: Callable[[], float] = time.time) -> Dict[str, Any]:
    """Collect one sample; write rh_rpc_health + rh_market_states + snapshot."""
    now = _utc_now()
    raw: Dict[str, Any] = {}
    errors: List[str] = []
    latencies: List[int] = []

    blk, err, ms = rpc_fn("eth_getBlockByNumber", ["latest", False])
    latencies.append(ms)
    block_number = None
    if err is None and isinstance(blk, dict):
        block_number = _hex_to_int(blk.get("number"))
        raw["block"] = {k: blk.get(k) for k in
                        ("number", "hash", "timestamp", "baseFeePerGas")}
    else:
        errors.append(f"eth_getBlockByNumber:{_err_text(err)}")

    slot0, err, ms = rpc_fn("eth_call",
                            [{"to": POOL, "data": SEL_SLOT0}, "latest"])
    latencies.append(ms)
    if err is None:
        raw["slot0"] = slot0
    else:
        errors.append(f"slot0:{_err_text(err)}")

    liq, err, ms = rpc_fn("eth_call",
                          [{"to": POOL, "data": SEL_LIQUIDITY}, "latest"])
    latencies.append(ms)
    if err is None:
        raw["liquidity"] = liq
    else:
        errors.append(f"liquidity:{_err_text(err)}")

    balances = {}
    for label, token in (("token0", TOKEN0), ("token1", TOKEN1)):
        bal, err, ms = rpc_fn("eth_call",
                              [{"to": token, "data": _balance_data(POOL)},
                               "latest"])
        latencies.append(ms)
        if err is None:
            balances[label] = bal
        else:
            errors.append(f"balance_{label}:{_err_text(err)}")
    raw["balances"] = balances

    state = "NORMAL" if not errors else ("DEGRADED" if len(errors) < 3 else "EXIT_ONLY")
    good_block = block_number if block_number is not None else last_good_block

    # RH-02i: fetch good_block's timestamp to compute the true data age.
    # good_block may be last_good_block from a prior round when the current
    # fetch failed, so re-fetch that specific block rather than reusing the
    # timestamp from the "latest" call above. One extra RPC call per round.
    block_timestamp = None
    block_hash = None
    if good_block is not None:
        blk_age, err_age, ms_age = rpc_fn(
            "eth_getBlockByNumber", [hex(good_block), False])
        latencies.append(ms_age)
        if err_age is None and isinstance(blk_age, dict):
            block_timestamp = _hex_to_int(blk_age.get("timestamp"))
            # RH-02p: provenance hash of good_block itself (not of the
            # "latest" call above; good_block may be a prior round's
            # last_good_block). None when unavailable, never "".
            block_hash = blk_age.get("hash") or None

    insert_row(conn, "rh_rpc_health", {
        "provider": RH_RPC_PRIMARY, "method": "pool_state_round",
        "sample_time": now,
        "latency_ms": max(latencies) if latencies else None,
        "error": "; ".join(errors) if errors else None,
        "last_good_block": good_block, "state": state,
    })

    price_text = None
    if isinstance(raw.get("slot0"), str) and len(raw["slot0"]) >= 66:
        sqrt_price = _hex_to_int("0x" + raw["slot0"][2:66])
        if sqrt_price:
            price_text = price_to_text(compute_price_human(sqrt_price, dec0, dec1))

    payload_hash = hashlib.sha256(
        json.dumps(raw, sort_keys=True).encode()).hexdigest()
    try:
        insert_row(conn, "rh_source_snapshots", {
            "source": "rh_rpc:pool_state", "payload_hash": payload_hash,
            "source_event_time": None, "fetch_time": now,
            "schema_kind": "JSON_RPC_V1", "raw_ref": None,
            "quality": "OK" if not errors else "PARTIAL",
        })
    except sqlite3.IntegrityError:
        pass  # identical payload already recorded; idempotent, keep going

    # RH-02i: true data age = now - good_block's timestamp. None when there
    # is no price or the block timestamp is unavailable (never a fake 0).
    # A future timestamp (clock skew) clamps to 0 but is flagged, not hidden.
    now_epoch = now_fn()
    reference_age_secs = None
    clock_skew = False
    if price_text is not None and block_timestamp is not None:
        reference_age_secs = int(now_epoch - block_timestamp)
        if reference_age_secs < 0:
            reference_age_secs = 0
            clock_skew = True
    flags = set()
    if state != "NORMAL":
        flags.add("CHAIN_DEGRADED")
    if clock_skew:
        flags.add("CLOCK_SKEW")

    session = _classify_sample_session(now)

    insert_row(conn, "rh_market_states", {
        "asset_address": POOL, "sample_time": now,
        "chain_id": CHAIN_ID, "source_payload_hash": payload_hash,
        "session": session,
        "health_flags_json": json.dumps(sorted(flags)),
        "reference_bid": None, "reference_ask": None,
        # reference_mid is the DEX pool price from sqrtPriceX96, not an
        # external reference (no REST here); see the module docstring.
        "reference_mid": price_text,
        "reference_age_secs": reference_age_secs,
        "multiplier_human": None, "oracle_paused": None,
        # RH-02p: provenance columns for the reorg-rollback chain.
        "derived_block_number": good_block,
        "derived_block_hash": block_hash,
    })
    conn.commit()
    return {"block_number": good_block, "price": price_text, "state": state,
            "errors": errors}


# --- daemon -----------------------------------------------------------------
_STOP = {"flag": False}


def _handle_signal(signum, _frame):  # pragma: no cover - signal path
    _STOP["flag"] = True


def run(db_path: str, *, interval_secs: int, max_rounds: int,
        pid_file: Optional[str], once: bool, rpc_fn: Callable = rpc) -> int:
    if pid_file and not pid_file_is_free(pid_file):
        print(f"collector already running per {pid_file}", file=sys.stderr)
        return 2
    if pid_file:
        Path(pid_file).parent.mkdir(parents=True, exist_ok=True)
        Path(pid_file).write_text(str(os.getpid()))
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = open_store(db_path)
    migrate(conn)

    dec0 = read_decimals(TOKEN0, rpc_fn) or 18
    dec1 = read_decimals(TOKEN1, rpc_fn)
    if dec1 is None:
        print("cannot read token1 decimals; refusing to guess", file=sys.stderr)
        return 3
    print(f"decimals token0={dec0} token1={dec1} (read from chain)", flush=True)

    rounds = 0
    fails = 0
    last_good = None
    sleep_for = interval_secs
    while not _STOP["flag"]:
        round_started = time.monotonic()
        try:
            out = collect_round(conn, dec0=dec0, dec1=dec1,
                                last_good_block=last_good, rpc_fn=rpc_fn)
            last_good = out["block_number"] or last_good
            fails = 0 if out["state"] == "NORMAL" else fails + 1
            print(f"{_utc_now()} block={out['block_number']} "
                  f"price={out['price']} state={out['state']}", flush=True)
        except Exception as exc:  # noqa: BLE001 keep the daemon alive
            fails += 1
            print(f"{_utc_now()} round failed: {type(exc).__name__}: {exc}",
                  file=sys.stderr, flush=True)
        rounds += 1
        if once or (max_rounds and rounds >= max_rounds):
            break
        if rounds % 20 == 0:
            budget = budget_status(db_path)
            if budget["state"] == "OVER":
                print(f"{_utc_now()} data budget exceeded ({budget}); stopping",
                      flush=True)
                break
            sleep_for = interval_secs * 2 if budget["state"] == "WARN" else interval_secs
        # Sleep to a deadline measured from the round's START, not from its end.
        # A round costs ~1.5s of serial RPC; sleeping a fixed interval afterwards
        # stretched the real period to 16.5s and cost ~10% of Stage A coverage.
        delay = sleep_for + (backoff_seconds(fails) if fails else 0)
        deadline = round_started + delay
        while not _STOP["flag"]:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(1.0, remaining))
    conn.commit()
    conn.close()
    if pid_file:
        try:
            Path(pid_file).unlink()
        except OSError:
            pass
    print(f"{_utc_now()} collector stopped after {rounds} rounds", flush=True)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="RH forward market-state collector")
    ap.add_argument("--db", default=str(DEFAULT_DB_PATH))
    ap.add_argument("--interval-secs", type=int, default=15)
    ap.add_argument("--max-rounds", type=int, default=0)
    ap.add_argument("--pid-file", default=None)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args(argv)
    return run(args.db, interval_secs=args.interval_secs,
               max_rounds=args.max_rounds, pid_file=args.pid_file,
               once=args.once)


if __name__ == "__main__":
    raise SystemExit(main())
