#!/usr/bin/env python3
"""Stage J: Raydium CLMM survival EV preview on quote-ready pools.

For Raydium CLMM, feeRate is stored in amm_config (PoolFeeConfig), not in pool.
This is a major difference from Orca: pool.feeRate not directly on chain.

For Stage J we use:
  - pool has liquidity (proxy: pool can absorb the trade)
  - Raydium standard fee tiers: 1bps, 5bps, 25bps, 30bps, 100bps (or custom via amm_config)
  - We use a 25bps default assumption (most common Raydium CLMM fee tier)
  - Note: actual fee would require reading amm_config.account, but that's beyond Stage I scope

Model (heuristic, same shape as Meteora V8 + Orca V1):
  gross_fee_usd      = notional * daily_turnover * (fee_bps / 10000)
  il_lvr_cost_usd    = notional * IL_LVR_PCT[scenario] * days
  total_cost_usd     = RAYDIUM_FIXED_COST_USD
  net_ev_usd         = gross_fee - il_lvr - cost
"""
import json
import csv
import os
from pathlib import Path

REPORT_DIR = os.environ["REPORT_DIR"]

quote_path = Path(REPORT_DIR) / "raydium_clmm_quote_smoke.json"
decode_path = Path(REPORT_DIR) / "raydium_clmm_pool_snapshot.json"
collection_path = Path(REPORT_DIR) / "raydium_clmm_candidate_source_collection.json"

with open(quote_path) as f:
    quote_data = json.load(f)
with open(decode_path) as f:
    decode_data = json.load(f)
with open(collection_path) as f:
    collection_data = json.load(f)

decoded_by_addr = {r["pool_address"]: r for r in decode_data if r.get("sdk_decode_success")}
collection_by_addr = {r["pool_address"]: r for r in collection_data}

# Quote-ready unique pools
quote_ready = {}
for r in quote_data:
    if r.get("quote_success"):
        a = r["pool_address"]
        if a not in quote_ready or r["notional_usd"] < quote_ready[a]["notional_usd"]:
            quote_ready[a] = r
quote_ready = list(quote_ready.values())
print(f"quote_ready pool count: {len(quote_ready)}")

# Heuristic constants
DAILY_TURNOVER = 0.005
IL_LVR_PCT = {
    "zero_il_lvr": 0.0,
    "optimistic": 0.001,
    "realistic": 0.005,
    "conservative": 0.020,
}
# Raydium round-trip cost: ~ $0.005-0.012 per V1 design (NFT mint + position rent + tx)
RAYDIUM_FIXED_COST_USD = 0.008

# Raydium standard fee tiers (we use 25bps as default for Stage J)
# Actual fee per pool would need amm_config lookup
DEFAULT_FEE_BPS = 25

NOTIONALS = [10, 20, 100, 500, 1000, 2000]
HOLD_WINDOWS = ["15m", "30m", "1h", "2h", "6h", "24h", "7d"]
HOLD_HOURS = {"15m": 0.25, "30m": 0.5, "1h": 1, "2h": 2, "6h": 6, "24h": 24, "7d": 168}
SCENARIOS = ["zero_il_lvr", "optimistic", "realistic", "conservative"]

rows = []
for q in quote_ready:
    addr = q["pool_address"]
    decoded = decoded_by_addr.get(addr, {})
    collection = collection_by_addr.get(addr, {})
    a_sym = (collection.get("base_symbol") or "?")[:6]
    b_sym = (collection.get("quote_symbol") or "?")[:6]
    token_pair = f"{a_sym}/{b_sym}"
    tick_spacing = decoded.get("tick_spacing")
    in_mint = q.get("token_in", "")
    if in_mint in (USDC_MINT := "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                   USDT_MINT := "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"):
        anchor = "USDC/USDT"
    else:
        anchor = "SOL"
    vol24h = collection.get("vol24h_usd", 0) or 0

    for notional in NOTIONALS:
        for hw in HOLD_WINDOWS:
            hours = HOLD_HOURS[hw]
            days = hours / 24
            for scenario in SCENARIOS:
                gross_fee_usd = notional * DAILY_TURNOVER * days * (DEFAULT_FEE_BPS / 10000.0)
                il_lvr_cost_usd = notional * IL_LVR_PCT[scenario] * days
                total_cost_usd = RAYDIUM_FIXED_COST_USD
                net_ev_usd = gross_fee_usd - il_lvr_cost_usd - total_cost_usd
                net_ev_pct = (net_ev_usd / notional * 100) if notional > 0 else 0.0
                rows.append({
                    "pool_address": addr,
                    "token_pair": token_pair,
                    "tick_spacing": tick_spacing,
                    "anchor_token": anchor,
                    "fee_rate_bps": DEFAULT_FEE_BPS,
                    "vol24h_usd": vol24h,
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
                    "confidence": 0.3,
                    "heuristic": True,
                    "scope": "raydium_clmm_readonly_connector",
                    "invalid_reason": None,
                })

print(f"row_count: {len(rows)}")

with open(f"{REPORT_DIR}/raydium_clmm_survival_ev_preview.json", "w") as f:
    json.dump(rows, f, indent=2)

with open(f"{REPORT_DIR}/raydium_clmm_survival_ev_preview.csv", "w", newline="") as f:
    w = csv.writer(f)
    cols = [
        "pool_address", "token_pair", "tick_spacing", "anchor_token",
        "fee_rate_bps", "vol24h_usd",
        "notional_usd", "hold_window", "hold_hours", "scenario",
        "daily_turnover", "gross_fee_usd", "il_lvr_cost_usd",
        "total_cost_usd", "net_ev_usd", "net_ev_pct", "quote_ready",
        "confidence", "heuristic", "scope", "invalid_reason",
    ]
    w.writerow(cols)
    for r in rows:
        w.writerow([r[c] for c in cols])

def count_pos(scenario):
    return sum(1 for r in rows if r["scenario"] == scenario and r["net_ev_usd"] > 0)
n_zero = count_pos("zero_il_lvr")
n_opt = count_pos("optimistic")
n_real = count_pos("realistic")
n_cons = count_pos("conservative")
n_near = sum(1 for r in rows if abs(r["net_ev_usd"]) <= 0.05)
best = max(rows, key=lambda r: r["net_ev_usd"])
best_per_pool = {}
for r in rows:
    a = r["pool_address"]
    if a not in best_per_pool or r["net_ev_usd"] > best_per_pool[a]["net_ev_usd"]:
        best_per_pool[a] = r
top5 = sorted(best_per_pool.values(), key=lambda r: -r["net_ev_usd"])[:5]

summary = {
    "stage": "LP_RAYDIUM_CLMM_READONLY_CONNECTOR_V1",
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
    "fee_rate_bps_used": DEFAULT_FEE_BPS,
    "top5_pools": [
        {
            "pool": p["pool_address"],
            "pair": p["token_pair"],
            "notional": p["notional_usd"],
            "hold_window": p["hold_window"],
            "scenario": p["scenario"],
            "net_ev_usd": p["net_ev_usd"],
        }
        for p in top5
    ],
}
with open(f"{REPORT_DIR}/data/survival_ev_summary.json", "w") as f:
    json.dump(summary, f, indent=2)
print(json.dumps(summary, indent=2))
