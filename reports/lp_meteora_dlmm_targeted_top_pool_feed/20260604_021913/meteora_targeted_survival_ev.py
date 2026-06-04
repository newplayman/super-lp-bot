#!/usr/bin/env python3
"""Stage H: survival EV preview for 27 quote-ready Meteora DLMM pools.

Model (heuristic, same shape as V7 + overnight):
  gross_fee_usd      = notional * daily_turnover * (base_fee_bps / 10000)
  il_lvr_cost_usd    = notional * IL_LVR_PCT[scenario]
  total_cost_usd     = SOLANA_FIXED_COST_USD
  net_ev_usd         = gross_fee - il_lvr - cost

Where:
  - daily_turnover: 0.5% heuristic (V7 used same)
  - IL_LVR_PCT: zero_il_lvr=0, optimistic=0.001, realistic=0.005, conservative=0.020
  - SOLANA_FIXED_COST_USD: $0.156 (rent + priority fee, V7 figure)

This is a HEURISTIC model. Real on-chain volume is unknown.
fee_10u / fee_20u (real quote data) is used to bound gross_fee by AMOUNT.
For per-cell gross_fee we use base_fee (not max_fee); max_fee is the
dynamic-fee cap under volatility, not a static rate.

Output: meteora_targeted_survival_ev.{json,csv}
"""
import json
import csv
import os
import sys
from pathlib import Path

REPORT_DIR = os.environ["REPORT_DIR"]

# Load quote data + decode data
quote_path = Path(REPORT_DIR) / "meteora_targeted_quote_readiness.json"
decode_path = Path(REPORT_DIR) / "meteora_targeted_pool_snapshot.json"

with open(quote_path) as f:
    quote_data = json.load(f)
with open(decode_path) as f:
    decode_data = json.load(f)

# Build lookup: pool_address -> decoded row
decoded_by_addr = {r["pool_address"]: r for r in decode_data if r.get("sdk_decode_success")}

# Filter to quote_ready pools
quote_ready = [r for r in quote_data if r.get("quote_ready")]
print(f"quote_ready pool count: {len(quote_ready)}")

# Heuristic constants
DAILY_TURNOVER = 0.005  # 0.5% of notional per day (heuristic)
IL_LVR_PCT = {
    "zero_il_lvr": 0.0,
    "optimistic": 0.001,
    "realistic": 0.005,
    "conservative": 0.020,
}
SOLANA_FIXED_COST_USD = 0.156  # rent + priority fee (V7)

NOTIONALS = [10, 20, 100, 500, 1000, 2000]
HOLD_WINDOWS = ["15m", "30m", "1h", "2h", "6h", "24h", "7d"]
HOLD_HOURS = {"15m": 0.25, "30m": 0.5, "1h": 1, "2h": 2, "6h": 6, "24h": 24, "7d": 168}
SCENARIOS = ["zero_il_lvr", "optimistic", "realistic", "conservative"]

rows = []
for q in quote_ready:
    addr = q["pool_address"]
    decoded = decoded_by_addr.get(addr, {})
    base_fee_bps = q.get("base_fee_bps") or 0
    max_fee_bps = q.get("max_fee_bps") or 0
    bin_step = q.get("bin_step") or 0
    # Token pair (re-derive from decoded)
    token_x = decoded.get("token_x", "")[:6] + "…"
    token_y = decoded.get("token_y", "")[:6] + "…"
    token_pair = f"{token_x}/{token_y}"
    # Real quote fee bounds (10u and 20u in raw)
    fee_10u_raw = int(q.get("fee_10u") or 0)
    fee_20u_raw = int(q.get("fee_20u") or 0)
    # Approximate USD value of 10u / 20u notional: anchor assumed USDC for Y=USDC, else SOL
    # For heuristic: assume in-token is USDC if Y=USDC, else SOL (130 USD)
    y_mint = decoded.get("token_y", "")
    x_mint = decoded.get("token_x", "")
    if y_mint in ("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"):
        # 10u USDC in -> fee in USDC raw
        # 10u USDC = 1e7 raw
        # fee_10u USD = fee_10u_raw / 1e6
        anchor = "USDC"
        in_10u_raw = 10_000_000
        in_20u_raw = 20_000_000
        fee_10u_usd = fee_10u_raw / 1e6
        fee_20u_usd = fee_20u_raw / 1e6
    else:
        # assume SOL in: 10 USD ≈ 7.69e7 lamports @ 130 USD/SOL
        anchor = "SOL"
        in_10u_raw = 76_923_077
        in_20u_raw = 153_846_154
        fee_10u_usd = fee_10u_raw / 1e9 * 130
        fee_20u_usd = fee_20u_raw / 1e9 * 130
    # Heuristic fee cap (real fee) as a sanity check
    real_fee_10u_usd = round(fee_10u_usd, 6)
    real_fee_20u_usd = round(fee_20u_usd, 6)

    for notional in NOTIONALS:
        for hw in HOLD_WINDOWS:
            hours = HOLD_HOURS[hw]
            days = hours / 24
            for scenario in SCENARIOS:
                # gross_fee based on base_fee_bps and heuristic turnover
                gross_fee_usd = notional * DAILY_TURNOVER * days * (base_fee_bps / 10000.0)
                il_lvr_cost_usd = notional * IL_LVR_PCT[scenario] * days  # scale by days
                total_cost_usd = SOLANA_FIXED_COST_USD
                net_ev_usd = gross_fee_usd - il_lvr_cost_usd - total_cost_usd
                net_ev_pct = (net_ev_usd / notional * 100) if notional > 0 else 0.0

                # mark heuristic (all are heuristic)
                rows.append({
                    "pool_address": addr,
                    "token_pair": token_pair,
                    "bin_step": bin_step,
                    "anchor_token": anchor,
                    "base_fee_bps": base_fee_bps,
                    "max_fee_bps": max_fee_bps,
                    "notional_usd": notional,
                    "hold_window": hw,
                    "hold_hours": hours,
                    "scenario": scenario,
                    "daily_turnover": DAILY_TURNOVER,
                    "gross_fee_usd": round(gross_fee_usd, 6),
                    "il_lvr_cost_usd": round(il_lvr_cost_usd, 6),
                    "total_cost_usd": round(total_cost_usd, 6),
                    "net_ev_usd": round(net_ev_usd, 6),
                    "net_ev_pct": round(net_ev_pct, 4),
                    "quote_ready": True,
                    "real_fee_10u_usd": real_fee_10u_usd,
                    "real_fee_20u_usd": real_fee_20u_usd,
                    "confidence": 0.3,  # heuristic
                    "heuristic": True,
                    "scope": "targeted_top_pool_feed",
                    "invalid_reason": None,
                })

print(f"row_count: {len(rows)}")

# write JSON
with open(f"{REPORT_DIR}/meteora_targeted_survival_ev.json", "w") as f:
    json.dump(rows, f, indent=2)

# write CSV
with open(f"{REPORT_DIR}/meteora_targeted_survival_ev.csv", "w", newline="") as f:
    w = csv.writer(f)
    cols = [
        "pool_address", "token_pair", "bin_step", "anchor_token",
        "base_fee_bps", "max_fee_bps", "notional_usd", "hold_window", "hold_hours",
        "scenario", "daily_turnover", "gross_fee_usd", "il_lvr_cost_usd",
        "total_cost_usd", "net_ev_usd", "net_ev_pct", "quote_ready",
        "real_fee_10u_usd", "real_fee_20u_usd", "confidence", "heuristic",
        "scope", "invalid_reason",
    ]
    w.writerow(cols)
    for r in rows:
        w.writerow([r[c] for c in cols])

# Compute summary
def count_pos(scenario):
    return sum(1 for r in rows if r["scenario"] == scenario and r["net_ev_usd"] > 0)

n_zero = count_pos("zero_il_lvr")
n_opt = count_pos("optimistic")
n_real = count_pos("realistic")
n_cons = count_pos("conservative")
# near_break_even: |net_ev_usd| <= $0.05
n_near = sum(1 for r in rows if abs(r["net_ev_usd"]) <= 0.05)

# best cell
best = max(rows, key=lambda r: r["net_ev_usd"])
# best per pool
best_per_pool = {}
for r in rows:
    a = r["pool_address"]
    if a not in best_per_pool or r["net_ev_usd"] > best_per_pool[a]["net_ev_usd"]:
        best_per_pool[a] = r
# top 5 pools by best_net_ev
top_pools = sorted(best_per_pool.values(), key=lambda r: -r["net_ev_usd"])[:5]

summary = {
    "stage": "LP_METEORA_DLMM_TARGETED_TOP_POOL_FEED_EXPANSION_V1",
    "run_id": os.environ.get("RUN_ID", ""),
    "row_count": len(rows),
    "quote_ready_pool_count": len(quote_ready),
    "positive_zero_il_lvr_count": n_zero,
    "positive_optimistic_count": n_opt,
    "positive_realistic_count": n_real,
    "positive_conservative_count": n_cons,
    "near_break_even_count": n_near,
    "best_pool": best["pool_address"],
    "best_pair": best["token_pair"],
    "best_notional": best["notional_usd"],
    "best_hold_window": best["hold_window"],
    "best_scenario": best["scenario"],
    "best_net_ev_proxy_usd": best["net_ev_usd"],
    "best_net_ev_proxy_pct": best["net_ev_pct"],
    "top5_pools": [
        {
            "pool": p["pool_address"],
            "pair": p["token_pair"],
            "base_fee_bps": p["base_fee_bps"],
            "notional": p["notional_usd"],
            "hold_window": p["hold_window"],
            "scenario": p["scenario"],
            "net_ev_usd": p["net_ev_usd"],
        }
        for p in top_pools
    ],
}
with open(f"{REPORT_DIR}/data/survival_ev_summary.json", "w") as f:
    json.dump(summary, f, indent=2)
print(json.dumps(summary, indent=2))
