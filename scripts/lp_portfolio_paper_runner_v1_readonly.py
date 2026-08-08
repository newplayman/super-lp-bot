#!/usr/bin/env python3
"""Multi-pool LP paper-shadow runner (READ-ONLY research).

Takes a fixed allocation (the portfolio allocator's output) and tracks the
paper P&L of the whole book over time. Per pool it holds a vol-sized *passive*
LP position and:
  - accrues real fees from real on-chain swaps that land inside the band,
  - accrues reward emissions linearly from the pool's reward_apr,
  - marks LP value + IL from the latest on-chain price,
  - logs band breaches for the operator (does NOT auto-rebalance — Tier-A
    policy is wide-range-passive; a breach is information, not an action).

This mirrors strategy_pivot_d4_realtime_paper_shadow_validation.py (the
single-pool Tier-A version) but is LP-only (no hedge) and multi-pool.

FROZEN-project rules: read-only. No wallet / signing / broadcast / chain
writes. RPC reads only. Honors FETCH_PACE_SECS for getLogs pacing.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone

# repo-root import shim so `scripts.*` resolves when run as a file
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.lp_tier_c_exit_feasibility_v1_readonly import (  # noqa: E402
    fetch_pool_swaps,
    _rpc_with_retry,
)
from scripts.lp_il_inventory_engine_v1_readonly import (  # noqa: E402
    alpha_vs_hodl,
    hodl_nav,
    il_pct,
    il_usd,
    lp_nav_ex_fee,
    paper_entry_baseline,
    pnl_vs_usdc,
    position_state_from_capital,
)
from scripts.lp_v3_fee_share import (  # noqa: E402
    position_liquidity_raw,
    fee_for_swap_usd,
)
from scripts.lp_swap_cost_model_v1_readonly import (  # noqa: E402
    exit_conversion_cost_usd,
)
from scripts.lp_rpc_pool_v1_readonly import RpcPool  # noqa: E402

# Rotating free-public-RPC pool, set up in run(). Until then, calls fall back to
# the single-URL _rpc_with_retry so the pure engine + tests need no network.
_POOL = None


def _rpc():
    """The active RPC entrypoint: rotating pool if initialized, else single-URL."""
    return _POOL.call if _POOL is not None else _rpc_with_retry


# ---------------------------------------------------------------------------
# Pure engine (unit-tested, NO network)
# ---------------------------------------------------------------------------

def init_state(*, capital, anchor, range_pct, fee_tier, dec0, dec1, last_block,
               exit_on_breach=False, exit_cost_bps=None, entry_swap_cost=0.0):
    """Build a fresh passive-position state dict.

    exit_on_breach: Tier-B policy — on the first band breach, auto-exit the LP
      position and convert back to base currency (holding the breached token is
      risky). Tier-A leaves this False (wide-range passive: breach = log only).
    exit_cost_bps: conversion cost charged on exit (swap fee + slippage). If
      None, a placeholder = round(fee_tier*1e4)+10bps is used until the
      depth/slippage model (lp_swap_cost_model) is wired in to size it properly.
    """
    if exit_cost_bps is None:
        exit_cost_bps = round(float(fee_tier) * 1e4) + 10.0
    paper_position = position_state_from_capital(anchor, capital, range_pct)
    baseline = paper_entry_baseline(anchor, capital, range_pct, entry_swap_cost)
    return {
        "capital": float(capital),
        "anchor": float(anchor),
        "range_pct": float(range_pct),
        "fee_tier": float(fee_tier),
        "dec0": int(dec0),
        "dec1": int(dec1),
        # liquidity for ONE unit of capital (size=1.0); fees are scaled by
        # capital afterwards, exactly like the passive replay convention.
        "l_pos_raw": position_liquidity_raw(1.0, anchor, range_pct, int(dec0), int(dec1)),
        # INV-IL-02: actual post-ratio-swap V3 legs, frozen by dataclass.
        "entry_baseline": baseline,
        # Principal-only range/liquidity state used by the single IL/NAV engine.
        "lp_principal_state": paper_position,
        "fees_quote": 0.0,
        "reward_quote": 0.0,
        "last_block": int(last_block),
        "breaches": [],
        "in_range_now": True,
        "exit_on_breach": bool(exit_on_breach),
        "exit_cost_bps": float(exit_cost_bps),
        "exited": None,
    }


def _do_exit(state, *, exit_price, block, l_active_raw=None):
    """Realize a position at exit_price and convert to base currency (paper).

    Frozen once set: LP value at exit + accrued fees, minus the cost of
    converting the LP holdings back to base. If the active pool liquidity is
    known (l_active_raw, from the breach swap), the depth-aware swap-cost model
    sizes that conversion (fee + real slippage); otherwise a flat exit_cost_bps
    placeholder is used. Fees are already in base, so only lp_value is converted.
    Reward is held separately and added at mark time. After exit the position
    holds base cash and accrues nothing.
    """
    cap = state["capital"]
    lp_value = lp_nav_ex_fee(state["lp_principal_state"], exit_price)
    entry_hodl = hodl_nav(state["entry_baseline"], exit_price, 1.0)
    il = il_usd(lp_value, entry_hodl)
    if l_active_raw and l_active_raw > 0:
        cost = exit_conversion_cost_usd(
            lp_value, l_active_raw, exit_price, state["fee_tier"],
            state["dec0"], state["dec1"], side="sell_base",
        )
    else:
        cost = lp_value * state["exit_cost_bps"] / 1e4
    state["exited"] = {
        "block": int(block),
        "price": float(exit_price),
        "lp_value_quote": lp_value,
        "lp_nav_ex_fee_quote": lp_value,
        "il_quote": il,
        "fees_quote": state["fees_quote"],
        "exit_cost_quote": cost,
        "realized_quote": lp_value - cost + state["fees_quote"],  # base cash recovered
    }
    return state


def update_position(state, swaps, *, now_block):
    """Advance a passive position with new swaps (block > state['last_block']).

    In-range swaps accrue fees (scaled by capital). Out-of-range swaps accrue
    NO fee and record a breach once per crossing (in->out transition). The
    anchor and capital never change — this is a passive, no-rebalance position.

    If exit_on_breach is set (Tier-B), the FIRST out-of-range swap closes the
    position (convert to base) and no further swaps are processed.
    """
    if state.get("exited"):  # closed: holds base cash, accrues nothing
        state["last_block"] = int(now_block)
        return state

    anchor = state["anchor"]
    r = state["range_pct"]
    lo = anchor * (1 - r / 100)
    hi = anchor * (1 + r / 100)
    l_pos_unit = state["l_pos_raw"]
    cap = state["capital"]
    in_range = state.get("in_range_now", True)

    for s in swaps:
        if s["block"] <= state["last_block"]:
            continue
        price = s["price"]
        if lo <= price <= hi:
            fee_unit = fee_for_swap_usd(
                l_pos_unit, s["liquidity"], s["amount1"], state["fee_tier"], state["dec1"]
            )
            state["fees_quote"] += cap * fee_unit
            in_range = True
        else:
            if in_range:  # only log the crossing, not every out-of-range tick
                state["breaches"].append({"block": s["block"], "price": price})
            in_range = False
            if state.get("exit_on_breach"):
                _do_exit(state, exit_price=price, block=s["block"],
                         l_active_raw=s.get("liquidity"))
                state["last_block"] = int(now_block)
                state["in_range_now"] = False
                return state  # stop: position closed at the breach

    state["last_block"] = int(now_block)
    state["in_range_now"] = in_range
    return state


def mark_position(state, current_price):
    """Mark the position to market at current_price (quote-token units).

    If the position has exited, current_price is ignored: it holds base cash, so
    the marks are the frozen realized values (plus reward accrued to exit).
    """
    cap = state["capital"]
    current_hodl = hodl_nav(state["entry_baseline"], current_price, 1.0)
    if state.get("exited"):
        ex = state["exited"]
        realized = ex["realized_quote"]
        current_total = realized + state["reward_quote"]
        net = current_total - cap
        # The LP principal was realized at exit, but the counterfactual HODL
        # basket keeps marking at today's price.  Preserve the IL identity
        # instead of freezing it merely because cash is now frozen.
        principal_at_exit = ex["lp_nav_ex_fee_quote"]
        current_il = il_usd(principal_at_exit, current_hodl)
        return {
            "lp_value_quote": realized,  # now base cash, not an LP position
            "il_quote": current_il,
            "fees_quote": ex["fees_quote"],
            "net_quote": net,
            "net_pct": (net / cap * 100) if cap else 0.0,
            "hodl_nav_quote": current_hodl,
            "lp_nav_ex_fee_quote": principal_at_exit,
            "il_vs_hodl_quote": current_il,
            "il_vs_hodl_pct": il_pct(current_il, current_hodl),
            "current_total_nav_quote": current_total,
            "pnl_vs_usdc_quote": pnl_vs_usdc(current_total, cap),
            "alpha_vs_hodl_quote": alpha_vs_hodl(current_total, current_hodl),
            "exited": True,
            "exit_price": ex["price"],
            "exit_cost_quote": ex["exit_cost_quote"],
        }
    lp_value = lp_nav_ex_fee(state["lp_principal_state"], current_price)
    il = il_usd(lp_value, current_hodl)
    fees = state["fees_quote"]
    net = lp_value + fees - cap
    net_pct = (net / cap * 100) if cap else 0.0
    current_total = lp_value + fees + state["reward_quote"]
    return {
        "lp_value_quote": lp_value,
        "il_quote": il,
        "fees_quote": fees,
        "net_quote": net,
        "net_pct": net_pct,
        "hodl_nav_quote": current_hodl,
        "lp_nav_ex_fee_quote": lp_value,
        "il_vs_hodl_quote": il,
        "il_vs_hodl_pct": il_pct(il, current_hodl),
        "current_total_nav_quote": current_total,
        "pnl_vs_usdc_quote": pnl_vs_usdc(current_total, cap),
        "alpha_vs_hodl_quote": alpha_vs_hodl(current_total, current_hodl),
        "exited": False,
    }


def accrue_reward(capital, reward_apr_pct, elapsed_secs):
    """Linear reward income over wall-clock time. Pure."""
    return float(capital) * (float(reward_apr_pct) / 100.0) * (float(elapsed_secs) / (365.0 * 86400.0))


# ---------------------------------------------------------------------------
# Runner (network)
# ---------------------------------------------------------------------------

def _now_utc():
    return datetime.now(timezone.utc)


def _latest_block():
    return int(_rpc()("eth_blockNumber", []), 16)


def _report_dir(out):
    if out:
        d = out
    else:
        stamp = _now_utc().strftime("%Y%m%d_%H%M%S")
        d = os.path.join(_REPO_ROOT, "reports", "lp_portfolio_paper_runner", stamp)
    os.makedirs(d, exist_ok=True)
    return d


def _load_allocation(path):
    with open(path) as f:
        data = json.load(f)
    allocs = data.get("allocations", [])
    if not allocs:
        raise SystemExit(f"no allocations in {path}")
    return allocs


def _init_book(allocs, *, entry_window_blocks, latest):
    """Tick 0: fetch a small recent window per pool to set the entry anchor."""
    book = []
    for a in allocs:
        pool = a["pool"]
        dec0, dec1 = int(a["dec0"]), int(a["dec1"])
        from_b = max(0, latest - entry_window_blocks)
        swaps = fetch_pool_swaps(pool, from_b, latest, dec0, dec1, rpc_call=_rpc())
        if not swaps:
            print(f"[warn] {a['symbol']} {pool}: no swaps in entry window; skipping")
            continue
        anchor = swaps[-1]["price"]
        tier = str(a.get("tier", "")).upper()
        # Tier-B auto-exits on breach (convert to base); Tier-A is wide-passive.
        exit_on_breach = a.get("exit_on_breach", tier == "B")
        st = init_state(
            capital=a["usd"], anchor=anchor, range_pct=a["range_pct"],
            fee_tier=a["fee_tier"], dec0=dec0, dec1=dec1, last_block=latest,
            exit_on_breach=exit_on_breach, exit_cost_bps=a.get("exit_cost_bps"),
        )
        book.append({
            "symbol": a["symbol"], "project": a.get("project", ""),
            "tier": a.get("tier", ""), "pool": pool,
            "reward_apr": float(a.get("reward_apr", 0.0)),
            "last_price": anchor, "state": st,
        })
        print(f"[init] {a['symbol']:14s} {a['tier']} cap={a['usd']:.0f} "
              f"anchor={anchor:.6g} range=±{a['range_pct']:.2f}% "
              f"exit_on_breach={exit_on_breach} pool={pool}")
        time.sleep(float(os.environ.get("CALL_PACE_SECS", "0.0")))
    if not book:
        raise SystemExit("no pools initialized (no swaps found)")
    return book


def _tick(book, *, last_ts):
    latest = _latest_block()
    now = _now_utc()
    elapsed = (now - last_ts).total_seconds()
    by_pool = []
    portfolio_net = 0.0
    for p in book:
        st = p["state"]
        if st.get("exited"):
            # closed position holds base cash: no RPC, no further accrual.
            mk = mark_position(st, p["last_price"])
            pool_net = mk["net_quote"]  # exited mark already includes reward
            n_swaps, new_breach = 0, False
        else:
            swaps = fetch_pool_swaps(p["pool"], st["last_block"] + 1, latest,
                                     st["dec0"], st["dec1"], rpc_call=_rpc())
            n_breach_before = len(st["breaches"])
            # book reward for elapsed BEFORE update, so a same-tick exit keeps it
            st["reward_quote"] += accrue_reward(st["capital"], p["reward_apr"], elapsed)
            update_position(st, swaps, now_block=latest)
            if swaps:
                p["last_price"] = swaps[-1]["price"]
            mk = mark_position(st, p["last_price"])
            # active mark excludes reward; exited mark includes it
            pool_net = mk["net_quote"] if st.get("exited") else mk["net_quote"] + st["reward_quote"]
            n_swaps = len(swaps)
            new_breach = len(st["breaches"]) > n_breach_before
            time.sleep(float(os.environ.get("CALL_PACE_SECS", "0.0")))
        portfolio_net += pool_net
        by_pool.append({
            "symbol": p["symbol"], "tier": p["tier"], "pool": p["pool"],
            "net_pct": round(mk["net_pct"], 4),
            "net_usd": round(pool_net, 2),
            "fees": round(st["fees_quote"], 4),
            "il": round(mk["il_quote"], 4),
            "hodl_nav": round(mk["hodl_nav_quote"], 4),
            "lp_nav_ex_fee": round(mk["lp_nav_ex_fee_quote"], 4),
            "current_total_nav": round(mk["current_total_nav_quote"], 4),
            "pnl_vs_usdc": round(mk["pnl_vs_usdc_quote"], 4),
            "alpha_vs_hodl": round(mk["alpha_vs_hodl_quote"], 4),
            "reward": round(st["reward_quote"], 4),
            "lp_value": round(mk["lp_value_quote"], 2),
            "n_swaps": n_swaps,
            "breaches": len(st["breaches"]),
            "new_breach": new_breach,
            "in_range": st["in_range_now"],
            "exited": bool(st.get("exited")),
        })
    return {"ts_utc": now.isoformat(), "block": latest,
            "portfolio_net_usd": round(portfolio_net, 2), "by_pool": by_pool}, now


def _write_pid(run_dir):
    with open(os.path.join(run_dir, "runner.pid"), "w") as f:
        f.write(str(os.getpid()))


def _append_heartbeat(run_dir, rec, tick):
    rec = {"tick": tick, **rec}
    with open(os.path.join(run_dir, "heartbeat.jsonl"), "a") as f:
        f.write(json.dumps(rec) + "\n")


_CSV_HEADER = "ts_utc,tick,block,portfolio_net_usd\n"


def _append_hourly_csv(run_dir, rec, tick):
    path = os.path.join(run_dir, "portfolio_state_hourly.csv")
    new = not os.path.exists(path)
    with open(path, "a") as f:
        if new:
            f.write(_CSV_HEADER)
        f.write(f"{rec['ts_utc']},{tick},{rec['block']},{rec['portfolio_net_usd']}\n")


def run(allocation_path, *, poll_secs=1800, max_ticks=None, out=None,
        entry_window_blocks=4000, chain="base"):
    global _POOL
    _POOL = RpcPool(chain)
    allocs = _load_allocation(allocation_path)
    run_dir = _report_dir(out)
    _write_pid(run_dir)
    print(f"[run] dir={run_dir} pools={len(allocs)} poll={poll_secs}s "
          f"max_ticks={max_ticks} chain={chain} "
          f"rpc_pool={len(_POOL._endpoints)} endpoints (rotating, free public)")

    latest = _latest_block()
    book = _init_book(allocs, entry_window_blocks=entry_window_blocks, latest=latest)
    # snapshot the resolved book for reproducibility
    with open(os.path.join(run_dir, "book_init.json"), "w") as f:
        json.dump([{k: v for k, v in p.items() if k != "state"} | {
            "anchor": p["state"]["anchor"], "capital": p["state"]["capital"],
            "range_pct": p["state"]["range_pct"], "fee_tier": p["state"]["fee_tier"],
        } for p in book], f, indent=2)

    last_ts = _now_utc()
    last_hour = -1
    tick = 0
    stop = {"flag": False}

    def _handle(signum, frame):  # graceful flush
        stop["flag"] = True
    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    try:
        while not stop["flag"]:
            rec, last_ts = _tick(book, last_ts=last_ts)
            _append_heartbeat(run_dir, rec, tick)
            cur_hour = datetime.fromisoformat(rec["ts_utc"]).hour
            if cur_hour != last_hour:
                _append_hourly_csv(run_dir, rec, tick)
                last_hour = cur_hour
            print(f"[tick {tick}] blk={rec['block']} net=${rec['portfolio_net_usd']:.2f} "
                  + " ".join(f"{p['symbol']}:{p['net_pct']:+.2f}%"
                             + ("!" if p["new_breach"] else "")
                             + ("·EXIT" if p.get("exited") else ("" if p["in_range"] else "·OOR"))
                             for p in rec["by_pool"]))
            tick += 1
            if max_ticks is not None and tick >= max_ticks:
                break
            if stop["flag"]:
                break
            for _ in range(int(poll_secs)):
                if stop["flag"]:
                    break
                time.sleep(1)
    finally:
        _flush_state(run_dir, book, tick)
        print(f"[done] {tick} ticks; state flushed to {run_dir}")


def _flush_state(run_dir, book, tick):
    snap = {"final_tick": tick, "pools": []}
    for p in book:
        st = p["state"]
        mk = mark_position(st, p["last_price"])
        net_quote = mk["net_quote"] if st.get("exited") else mk["net_quote"] + st["reward_quote"]
        snap["pools"].append({
            "symbol": p["symbol"], "tier": p["tier"], "pool": p["pool"],
            "capital": st["capital"], "anchor": st["anchor"],
            "range_pct": st["range_pct"], "last_price": p["last_price"],
            "fees_quote": st["fees_quote"], "reward_quote": st["reward_quote"],
            "il_quote": mk["il_quote"], "lp_value_quote": mk["lp_value_quote"],
            "hodl_nav_quote": mk["hodl_nav_quote"],
            "lp_nav_ex_fee_quote": mk["lp_nav_ex_fee_quote"],
            "il_vs_hodl_quote": mk["il_vs_hodl_quote"],
            "il_vs_hodl_pct": mk["il_vs_hodl_pct"],
            "current_total_nav_quote": mk["current_total_nav_quote"],
            "pnl_vs_usdc_quote": mk["pnl_vs_usdc_quote"],
            "alpha_vs_hodl_quote": mk["alpha_vs_hodl_quote"],
            "net_quote": net_quote,
            "net_pct": mk["net_pct"], "n_breaches": len(st["breaches"]),
            "in_range": st["in_range_now"], "breaches": st["breaches"],
            "exit_on_breach": st.get("exit_on_breach", False),
            "exited": st.get("exited"),
        })
    with open(os.path.join(run_dir, "final_state.json"), "w") as f:
        json.dump(snap, f, indent=2)


# ---------------------------------------------------------------------------
# Self-test (pure, no network)
# ---------------------------------------------------------------------------

def run_self_test():
    dec0 = dec1 = 18
    fee_tier = 0.003
    r = 10.0
    anchor = 1.0
    st = init_state(capital=1000.0, anchor=anchor, range_pct=r,
                    fee_tier=fee_tier, dec0=dec0, dec1=dec1, last_block=0)
    L = 10 ** 18
    amt1 = 10 ** 18  # 1.0 token1 raw
    # two in-range swaps
    in_swaps = [
        {"block": 1, "price": 1.00, "liquidity": L, "amount1": amt1},
        {"block": 2, "price": 1.02, "liquidity": L, "amount1": amt1},
    ]
    update_position(st, in_swaps, now_block=2)
    assert st["fees_quote"] > 0, "in-range swaps must accrue fees"
    assert st["breaches"] == [], "no breach while in range"
    assert st["anchor"] == anchor, "anchor must not move (passive)"
    fees_after_in = st["fees_quote"]

    mk = mark_position(st, anchor)
    assert abs(mk["il_quote"]) < 1e-6, "round-trip to anchor => IL ~ 0"
    assert mk["net_quote"] > 0, "net positive once fees accrued at anchor"

    # an out-of-range swap: no fee, one breach, anchor unchanged
    out_swaps = [{"block": 3, "price": 1.50, "liquidity": L, "amount1": amt1}]
    update_position(st, out_swaps, now_block=3)
    assert st["fees_quote"] == fees_after_in, "out-of-range swap accrues no fee"
    assert len(st["breaches"]) == 1, "one breach recorded"
    assert st["anchor"] == anchor, "anchor still unchanged (no rebalance)"

    mk2 = mark_position(st, 1.20)
    assert mk2["il_quote"] < 0, "price move => IL < 0"

    # reward: linear, zero at zero elapsed
    assert accrue_reward(1000.0, 50.0, 0) == 0.0
    half = accrue_reward(1000.0, 50.0, 365 * 86400 / 2)
    full = accrue_reward(1000.0, 50.0, 365 * 86400)
    assert abs(full - 500.0) < 1e-6, "50% APR for 1y on 1000 => 500"
    assert abs(half * 2 - full) < 1e-9, "reward linear in elapsed"
    assert abs(accrue_reward(2000.0, 50.0, 365 * 86400) - 1000.0) < 1e-6, "linear in capital"

    # Tier-B auto-exit on breach: position closes, converts to base, stops accruing
    stb = init_state(capital=1000.0, anchor=1.0, range_pct=r, fee_tier=fee_tier,
                     dec0=dec0, dec1=dec1, last_block=0, exit_on_breach=True)
    update_position(stb, [{"block": 1, "price": 1.0, "liquidity": L, "amount1": amt1}], now_block=1)
    assert stb["exited"] is None, "in-range: not exited"
    update_position(stb, [{"block": 2, "price": 1.5, "liquidity": L, "amount1": amt1}], now_block=2)
    assert stb["exited"] is not None, "breach must trigger exit for Tier-B"
    assert stb["exited"]["exit_cost_quote"] > 0, "exit pays a conversion cost"
    fees_at_exit = stb["fees_quote"]
    # further swaps after exit accrue nothing (holds base cash)
    update_position(stb, [{"block": 3, "price": 1.0, "liquidity": L, "amount1": amt1}], now_block=3)
    assert stb["fees_quote"] == fees_at_exit, "no accrual after exit"
    mkb = mark_position(stb, 9.99)  # current price ignored once exited
    assert mkb["exited"] is True and mkb["lp_value_quote"] == stb["exited"]["realized_quote"]

    print("self-test OK: fees accrue in-range, breaches logged out-of-range, "
          "anchor passive, IL sign correct, reward linear, Tier-B auto-exit works.")


def main():
    ap = argparse.ArgumentParser(description="Multi-pool LP paper-shadow runner (read-only)")
    ap.add_argument("--allocation", help="path to allocator allocation.json")
    ap.add_argument("--poll-secs", type=int, default=1800,
                    help="seconds between ticks; default 1800 (30min) keeps "
                         "free-RPC load low")
    ap.add_argument("--chain", default="base",
                    help="chain key for the rotating free-RPC pool")
    ap.add_argument("--max-ticks", type=int, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--entry-window-blocks", type=int, default=4000)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        run_self_test()
        return
    if not args.allocation:
        ap.error("--allocation is required (or use --self-test)")
    run(args.allocation, poll_secs=args.poll_secs, max_ticks=args.max_ticks,
        out=args.out, entry_window_blocks=args.entry_window_blocks, chain=args.chain)


if __name__ == "__main__":
    main()
