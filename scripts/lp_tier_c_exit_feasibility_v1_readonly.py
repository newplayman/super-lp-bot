#!/usr/bin/env python3
"""
LP Tier-C exit feasibility — read-only backtest.

Decisive question for Tier-C (newly-launched, >800% APR, near-doubling-daily,
zero-out risk) LP positions: the operator's plan is "if price breaks the LP
range lower bound, stop-loss and clear the position immediately." This pipeline
tests the hidden assumption in that plan — that you can actually EXIT at the
floor. For the dominant Tier-C death (rug / honeypot / liquidity drain) price
does not cross the floor continuously; it GAPS through in one block while
liquidity collapses, so a resting price-floor stop never fills at the floor.

This replays a pool's REAL historical swap stream through a hypothetical
Tier-C LP entry and measures, at the first lower-bound breach:
  - gap_through:  did price cross the floor continuously (fills available at the
                  floor) or discontinuously (one swap jumped far past it)?
  - liq_collapse: did active liquidity crater around the breach (rug signature)?
  - realized exit vs assumed floor: how much WORSE than the stop's assumed floor
                  price would a real market-exit during the dump have been?
Verdict per pool: EXITABLE_CLEAN / GAPPED / UNEXITABLE / NO_BREACH.

What it does NOT cover (by design, v1): Burn-event liquidity removal, honeypot
sellability, transfer-tax — those are ENTRY-screening concerns handled by
internal/core/tierc (holder snapshot, hard rejection policy), and they matter
MORE than any exit logic. This pipeline isolates the exit-execution question.

Read-only: public Base RPC (or env D4_BASE_RPC_URL / BASE_RPC_URL), no wallet,
no signing, no broadcast. The pure analyzer needs no network and is the unit
under test. Freeze discipline intact.

Usage:
  python3 scripts/lp_tier_c_exit_feasibility_v1_readonly.py --self-test
  python3 scripts/lp_tier_c_exit_feasibility_v1_readonly.py --config pools.json
  python3 scripts/lp_tier_c_exit_feasibility_v1_readonly.py \
      --pool 0x... --entry-block N --blocks-forward 5000 --range-pct 5 \
      --dec0 18 --dec1 18
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Config / constants
# ---------------------------------------------------------------------------

WORKSPACE = Path(os.environ.get("REPO_ROOT_OVERRIDE", "/opt/lpbot/lp-bot-v3-origin-check"))
REPORT_BASE = WORKSPACE / "reports" / "lp_tier_c_exit_feasibility"

V3_SWAP_TOPIC = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
PUBLIC_BASE_RPCS = [
    "https://mainnet.base.org",
    "https://base-rpc.publicnode.com",
    "https://developer-access-mainnet.base.org",
]
POLL_BLOCK_WINDOW = 2000

# Verdict thresholds (fractions, not pct points).
GAP_UNEXITABLE = 0.50      # first sub-floor print >=50% below floor => teleported past
GAP_DEGRADED = 0.10        # >=10% below floor => stop fills materially worse than floor
COLLAPSE_UNEXITABLE = 0.90  # active liquidity fell >=90% around breach => rug signature
NEAR_FLOOR_BAND = 0.02     # +/-2% band around floor counts as "a chance to exit near floor"
DUMP_LOOKAHEAD = 10        # swaps after breach used to estimate a realistic market-exit price


# ---------------------------------------------------------------------------
# Pure V3 helpers (decimal-free where possible; unit-tested)
# ---------------------------------------------------------------------------

def price_from_sqrt_x96(sqrt_price_x96: int, dec0: int, dec1: int) -> float:
    """Human price = token1 per token0, adjusted for decimals.

    For pool 0xb2cc (token0=WETH 18, token1=USDC 6) this returns USDC per WETH.
    For a NEWTOKEN(18)/WETH(18) pool it returns WETH per NEWTOKEN.
    """
    raw = (sqrt_price_x96 / (2 ** 96)) ** 2
    return raw * (10 ** (dec0 - dec1))


def _to_signed_256(uval: int) -> int:
    if uval >= (1 << 255):
        uval -= (1 << 256)
    return uval


def decode_v3_swap_data(data_hex: str):
    """Decode a Uniswap/Aerodrome V3 Swap event data blob (5 words).

    Mirrors the fixed decoder in the D4 runner: signed amounts/tick via two's
    complement, correct word offsets.
    """
    if not data_hex or len(data_hex) < 2:
        return None
    p = data_hex[2:]
    if len(p) < 320:
        return None
    try:
        return {
            "amount0": _to_signed_256(int(p[0:64], 16)),
            "amount1": _to_signed_256(int(p[64:128], 16)),
            "sqrt_price_x96": int(p[128:192], 16),
            "liquidity": int(p[192:256], 16),
            "tick": _to_signed_256(int(p[256:320], 16)),
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Pure analyzer — the unit under test (no network)
# ---------------------------------------------------------------------------

def analyze_exit_feasibility(
    swaps,
    entry_price,
    range_pct,
    *,
    gap_unexitable=GAP_UNEXITABLE,
    gap_degraded=GAP_DEGRADED,
    collapse_unexitable=COLLAPSE_UNEXITABLE,
    near_floor_band=NEAR_FLOOR_BAND,
    dump_lookahead=DUMP_LOOKAHEAD,
):
    """Replay `swaps` through a Tier-C LP entry and judge exit feasibility.

    `swaps`: list of dicts ordered in time, each with:
        'price'     (float, human token1/token0 at/after the swap)
        'liquidity' (int, active pool liquidity at the swap; 0 if unknown)
        'block'     (int, optional, for reporting)
    `entry_price`: price at LP entry.
    `range_pct`: LP half-range %. lower_floor = entry*(1 - range_pct/100).

    Returns a verdict dict. Verdict semantics:
      NO_BREACH       price never crossed the floor in the window.
      EXITABLE_CLEAN  floor crossed continuously, liquidity stable, low slippage.
      GAPPED          floor crossed with a material gap / realized exit well below floor.
      UNEXITABLE      price teleported far past floor and/or liquidity collapsed.
    """
    if not swaps or entry_price <= 0:
        return {"verdict": "NO_DATA", "breached": False, "n_swaps": len(swaps or [])}

    floor = entry_price * (1.0 - range_pct / 100.0)
    cap = entry_price * (1.0 + range_pct / 100.0)

    liq_entry = next((s.get("liquidity", 0) for s in swaps if s.get("liquidity")), 0)

    prices = [s["price"] for s in swaps]
    min_price = min(prices)
    max_drawdown_pct = (entry_price - min_price) / entry_price

    # chances to exit near the floor anywhere in the stream
    near_floor_fills = sum(
        1 for p in prices if floor * (1 - near_floor_band) <= p <= floor * (1 + near_floor_band)
    )

    # first lower-bound breach
    breach_i = None
    prev_price = entry_price
    for i, s in enumerate(swaps):
        if s["price"] < floor:
            breach_i = i
            break
        prev_price = s["price"]

    if breach_i is None:
        return {
            "verdict": "NO_BREACH",
            "breached": False,
            "n_swaps": len(swaps),
            "floor": floor,
            "cap": cap,
            "min_price": min_price,
            "max_drawdown_pct": max_drawdown_pct,
            "in_range_end": floor <= prices[-1] <= cap,
        }

    breach = swaps[breach_i]
    breach_price = breach["price"]

    # how far past the floor the FIRST sub-floor print landed (the gap)
    gap_through_pct = (floor - breach_price) / floor if floor > 0 else 1.0

    # realistic market-exit during the dump: the worst (lowest) price you'd
    # plausibly get racing the crowd out over the next few swaps.
    window = swaps[breach_i: breach_i + max(1, dump_lookahead)]
    realized_exit_price = min(s["price"] for s in window)
    realized_loss_vs_floor_pct = (floor - realized_exit_price) / floor if floor > 0 else 1.0

    # liquidity collapse around the breach
    liq_window = [s.get("liquidity", 0) for s in swaps[: breach_i + max(1, dump_lookahead)] if s.get("liquidity")]
    min_liq = min(liq_window) if liq_window else 0
    if liq_entry > 0:
        collapse_ratio = 1.0 - (min_liq / liq_entry)
    else:
        collapse_ratio = 0.0

    # verdict
    if collapse_ratio >= collapse_unexitable or gap_through_pct >= gap_unexitable:
        verdict = "UNEXITABLE"
    elif gap_through_pct >= gap_degraded or realized_loss_vs_floor_pct >= gap_degraded:
        verdict = "GAPPED"
    else:
        verdict = "EXITABLE_CLEAN"

    return {
        "verdict": verdict,
        "breached": True,
        "n_swaps": len(swaps),
        "floor": floor,
        "cap": cap,
        "entry_price": entry_price,
        "breach_block": breach.get("block"),
        "breach_index": breach_i,
        "price_before_breach": prev_price,
        "breach_price": breach_price,
        "gap_through_pct": gap_through_pct,
        "near_floor_fills": near_floor_fills,
        "realized_exit_price": realized_exit_price,
        "realized_loss_vs_floor_pct": realized_loss_vs_floor_pct,
        "liq_entry": liq_entry,
        "min_liq_around_breach": min_liq,
        "liq_collapse_ratio": collapse_ratio,
        "min_price": min_price,
        "max_drawdown_pct": max_drawdown_pct,
    }


# ---------------------------------------------------------------------------
# RPC layer (read-only)
# ---------------------------------------------------------------------------

def _rpc_url():
    return (
        os.environ.get("D4_BASE_RPC_URL")
        or os.environ.get("BASE_RPC_URL")
        or PUBLIC_BASE_RPCS[0]
    )


def _rpc_post(method, params, url=None, timeout=20):
    url = url or _rpc_url()
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _rpc_with_retry(method, params, attempts=4):
    last = None
    urls = [_rpc_url()] + [u for u in PUBLIC_BASE_RPCS if u != _rpc_url()]
    for a in range(attempts):
        url = urls[min(a, len(urls) - 1)]
        try:
            out = _rpc_post(method, params, url=url)
            if "result" in out:
                return out["result"]
            last = out.get("error")
        except Exception as e:  # noqa: BLE001
            last = str(e)
        time.sleep([0.5, 1, 2, 4][min(a, 3)])
    raise RuntimeError(f"RPC {method} failed after {attempts} attempts: {last}")


def fetch_pool_swaps(pool, from_block, to_block, dec0, dec1):
    """Fetch + decode V3 swaps for `pool` over [from_block, to_block]."""
    swaps = []
    b = from_block
    while b <= to_block:
        to_b = min(b + POLL_BLOCK_WINDOW, to_block)
        logs = _rpc_with_retry(
            "eth_getLogs",
            [{
                "address": pool,
                "topics": [V3_SWAP_TOPIC],
                "fromBlock": hex(b),
                "toBlock": hex(to_b),
            }],
        )
        for lg in logs:
            ev = decode_v3_swap_data(lg.get("data", ""))
            if ev is None:
                continue
            swaps.append({
                "block": int(lg.get("blockNumber", "0x0"), 16),
                "price": price_from_sqrt_x96(ev["sqrt_price_x96"], dec0, dec1),
                "liquidity": ev["liquidity"],
                "tick": ev["tick"],
                "amount0": ev["amount0"],
                "amount1": ev["amount1"],
            })
        b = to_b + 1
    swaps.sort(key=lambda s: s["block"])
    return swaps


# ---------------------------------------------------------------------------
# Synthetic streams for the self-test / demonstration
# ---------------------------------------------------------------------------

def synthetic_streams(entry=1.0):
    """Three canonical Tier-C exit scenarios, decimal-free price streams."""
    L = 10 ** 18

    # 1) clean: gentle continuous decline straddling the floor, stable liquidity.
    clean = [{"price": p, "liquidity": L, "block": i}
             for i, p in enumerate([1.00, 0.99, 0.975, 0.96, 0.95, 0.94, 0.93, 0.92])]

    # 2) gapped: one swap teleports from above the floor to 40% below it.
    gapped = [{"price": 1.00, "liquidity": L, "block": 0},
              {"price": 0.99, "liquidity": L, "block": 1},
              {"price": 0.98, "liquidity": L, "block": 2},
              {"price": 0.58, "liquidity": L, "block": 3},   # gap through ~5% floor
              {"price": 0.50, "liquidity": L, "block": 4}]

    # 3) collapse: liquidity craters to ~zero at the breach (rug signature).
    collapse = [{"price": 1.00, "liquidity": L, "block": 0},
                {"price": 0.99, "liquidity": L, "block": 1},
                {"price": 0.97, "liquidity": L // 50, "block": 2},
                {"price": 0.80, "liquidity": L // 1000, "block": 3}]

    # 4) no breach: stays inside the range.
    no_breach = [{"price": p, "liquidity": L, "block": i}
                 for i, p in enumerate([1.00, 1.01, 0.99, 1.02, 0.98, 1.00])]

    return {"clean": clean, "gapped": gapped, "collapse": collapse, "no_breach": no_breach}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _report_dir():
    stamp = os.environ.get("RUN_ID_OVERRIDE") or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    d = REPORT_BASE / stamp
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_self_test():
    streams = synthetic_streams()
    range_pct = 5.0  # Tier-C tight range
    results = {}
    for name, swaps in streams.items():
        results[name] = analyze_exit_feasibility(swaps, entry_price=1.0, range_pct=range_pct)
    out = _report_dir()
    (out / "self_test_verdicts.json").write_text(json.dumps(results, indent=2))
    print("Tier-C exit feasibility — self-test (synthetic streams, range ±5%)")
    for name, r in results.items():
        extra = ""
        if r.get("breached"):
            extra = (f" gap={r['gap_through_pct']*100:.0f}% "
                     f"realized_loss_vs_floor={r['realized_loss_vs_floor_pct']*100:.0f}% "
                     f"liq_collapse={r['liq_collapse_ratio']*100:.0f}%")
        print(f"  {name:10s} -> {r['verdict']}{extra}")
    print(f"\nwrote {out/'self_test_verdicts.json'}")
    return results


def run_config(cfg_path):
    cfg = json.loads(Path(cfg_path).read_text())
    pools = cfg if isinstance(cfg, list) else cfg.get("pools", [])
    out = _report_dir()
    verdicts = []
    for p in pools:
        entry = int(p["entry_block"])
        fwd = int(p.get("blocks_forward", 5000))
        dec0, dec1 = int(p.get("dec0", 18)), int(p.get("dec1", 18))
        swaps = fetch_pool_swaps(p["pool"], entry, entry + fwd, dec0, dec1)
        entry_price = swaps[0]["price"] if swaps else 0.0
        r = analyze_exit_feasibility(swaps, entry_price, float(p.get("range_pct", 5)))
        r["label"] = p.get("label", p["pool"])
        r["pool"] = p["pool"]
        verdicts.append(r)
        print(f"  {r['label']:24s} -> {r['verdict']}  (swaps={r.get('n_swaps')})")
    agg = _aggregate(verdicts)
    (out / "exit_feasibility_verdicts.json").write_text(
        json.dumps({"verdicts": verdicts, "aggregate": agg}, indent=2)
    )
    print(f"\naggregate: {agg}")
    print(f"wrote {out/'exit_feasibility_verdicts.json'}")
    return verdicts


def _aggregate(verdicts):
    counts = {}
    for v in verdicts:
        counts[v["verdict"]] = counts.get(v["verdict"], 0) + 1
    breached = [v for v in verdicts if v.get("breached")]
    exitable = sum(1 for v in breached if v["verdict"] == "EXITABLE_CLEAN")
    return {
        "n_pools": len(verdicts),
        "verdict_counts": counts,
        "breached": len(breached),
        "clean_exit_rate_of_breached": (exitable / len(breached)) if breached else None,
    }


def main():
    ap = argparse.ArgumentParser(description="Tier-C LP exit feasibility (read-only)")
    ap.add_argument("--self-test", action="store_true", help="run synthetic-stream demonstration")
    ap.add_argument("--config", help="JSON file: list of {pool, entry_block, blocks_forward, range_pct, dec0, dec1, label}")
    ap.add_argument("--pool")
    ap.add_argument("--entry-block", type=int)
    ap.add_argument("--blocks-forward", type=int, default=5000)
    ap.add_argument("--range-pct", type=float, default=5.0)
    ap.add_argument("--dec0", type=int, default=18)
    ap.add_argument("--dec1", type=int, default=18)
    args = ap.parse_args()

    if args.self_test or (not args.config and not args.pool):
        run_self_test()
        return
    if args.config:
        run_config(args.config)
        return
    # single pool
    swaps = fetch_pool_swaps(args.pool, args.entry_block, args.entry_block + args.blocks_forward, args.dec0, args.dec1)
    entry_price = swaps[0]["price"] if swaps else 0.0
    r = analyze_exit_feasibility(swaps, entry_price, args.range_pct)
    out = _report_dir()
    (out / "exit_feasibility_verdicts.json").write_text(json.dumps(r, indent=2))
    print(json.dumps(r, indent=2))
    print(f"wrote {out/'exit_feasibility_verdicts.json'}")


if __name__ == "__main__":
    main()
