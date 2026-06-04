#!/usr/bin/env python3
"""Stage J: Orca survival EV preview on quote-ready pools.

Model (heuristic, same shape as V7 + Meteora V8):
  gross_fee_usd      = notional * daily_turnover * (pool_fee_rate_bps / 10000)
  il_lvr_cost_usd    = notional * IL_LVR_PCT[scenario] * days
  total_cost_usd     = ORCA_FIXED_COST_USD
  net_ev_usd         = gross_fee - il_lvr - cost

Where:
  - daily_turnover: 0.5% heuristic
  - IL_LVR_PCT: zero_il_lvr=0, optimistic=0.001, realistic=0.005, conservative=0.020
  - ORCA_FIXED_COST_USD: 0.006 (round-trip cost $0.005-0.008 per V1 design doc)

Use REAL fee_rate from Stage G (Orca pool on-chain feeRate) — not max_fee.
Max_fee is only dynamic peak during volatility.

10 USD / 20 USD (priority, matches V1 probe preflight)
Plus 100 / 500 / 1000 / 2000 USD for broader sweep.
"""
import json
import csv
import os
from pathlib import Path

REPORT_DIR = os.environ["REPORT_DIR"]

# Load quote data + decode data
quote_path = Path(REPORT_DIR) / "orca_quote_smoke.json"
decode_path = Path(REPORT_DIR) / "orca_whirlpool_pool_snapshot.json"
collection_path = Path(REPORT_DIR) / "orca_candidate_source_collection.json"

with open(quote_path) as f:
    quote_data = json.load(f)
with open(decode_path) as f:
    decode_data = json.load(f)
with open(collection_path) as f:
    collection_data = json.load(f)

# Build lookup: pool_address -> decoded row + collection row
decoded_by_addr = {r["pool_address"]: r for r in decode_data if r.get("sdk_decode_success")}
collection_by_addr = {r["pool_address"]: r for r in collection_data}

# Get unique quote-ready pools (one row per pool, prefer 10u)
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
ORCA_FIXED_COST_USD = 0.006  # V1 design doc: $0.005-0.008

NOTIONALS = [10, 20, 100, 500, 1000, 2000]
HOLD_WINDOWS = ["15m", "30m", "1h", "2h", "6h", "24h", "7d"]
HOLD_HOURS = {"15m": 0.25, "30m": 0.5, "1h": 1, "2h": 2, "6h": 6, "24h": 24, "7d": 168}
SCENARIOS = ["zero_il_lvr", "optimistic", "realistic", "conservative"]

rows = []
for q in quote_ready:
    addr = q["pool_address"]
    decoded = decoded_by_addr.get(addr, {})
    collection = collection_by_addr.get(addr, {})
    fee_rate_bps = decoded.get("fee_rate_bps") or 0  # on-chain feeRate
    if isinstance(fee_rate_bps, str):
        try:
            fee_rate_bps = int(fee_rate_bps)
        except:
            fee_rate_bps = 0
    # token pair (short)
    a_sym = (collection.get("base_symbol") or "?")[:6]
    b_sym = (collection.get("quote_symbol") or "?")[:6]
    token_pair = f"{a_sym}/{b_sym}"
    # Real fee (10u in raw) for sanity
    fee_10u_raw = int(q.get("fee") or 0)
    in_mint = q.get("token_in", "")
    if in_mint in ("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"):
        real_fee_10u_usd = fee_10u_raw / 1e6
    else:
        # SOL: lamports -> SOL -> USD
        real_fee_10u_usd = fee_10u_raw / 1e9 * 130
    tvl = collection.get("tvl_usd") or 0
    vol24h = collection.get("vol24h_usd") or 0

    for notional in NOTIONALS:
        for hw in HOLD_WINDOWS:
            hours = HOLD_HOURS[hw]
            days = hours / 24
            for scenario in SCENARIOS:
                gross_fee_usd = notional * DAILY_TURNOVER * days * (fee_rate_bps / 10000.0)
                il_lvr_cost_usd = notional * IL_LVR_PCT[scenario] * days
                total_cost_usd = ORCA_FIXED_COST_USD
                net_ev_usd = gross_fee_usd - il_lvr_cost_usd - total_cost_usd
                net_ev_pct = (net_ev_usd / notional * 100) if notional > 0 else 0.0
                rows.append({
                    "pool_address": addr,
                    "token_pair": token_pair,
                    "tick_spacing": decoded.get("tick_spacing"),
                    "anchor_token": "USDC" if in_mint.startswith("EPjFW") or in_mint.startswith("Es9vM") else "SOL",
                    "fee_rate_bps": fee_rate_bps,
                    "tvl_usd": tvl,
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
                    "real_fee_10u_usd": round(real_fee_10u_usd, 6),
                    "confidence": 0.3,
                    "heuristic": True,
                    "scope": "orca_whirlpool_readonly_connector",
                    "invalid_reason": None,
                })

print(f"row_count: {len(rows)}")

# write JSON
with open(f"{REPORT_DIR}/orca_survival_ev_preview.json", "w") as f:
    json.dump(rows, f, indent=2)

# write CSV
with open(f"{REPORT_DIR}/orca_survival_ev_preview.csv", "w", newline="") as f:
    w = csv.writer(f)
    cols = [
        "pool_address", "token_pair", "tick_spacing", "anchor_token",
        "fee_rate_bps", "tvl_usd", "vol24h_usd",
        "notional_usd", "hold_window", "hold_hours", "scenario",
        "daily_turnover", "gross_fee_usd", "il_lvr_cost_usd",
        "total_cost_usd", "net_ev_usd", "net_ev_pct", "quote_ready",
        "real_fee_10u_usd", "confidence", "heuristic", "scope", "invalid_reason",
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
n_near = sum(1 for r in rows if abs(r["net_ev_usd"]) <= 0.05)
best = max(rows, key=lambda r: r["net_ev_usd"])
best_per_pool = {}
for r in rows:
    a = r["pool_address"]
    if a not in best_per_pool or r["net_ev_usd"] > best_per_pool[a]["net_ev_usd"]:
        best_per_pool[a] = r
top5 = sorted(best_per_pool.values(), key=lambda r: -r["net_ev_usd"])[:5]

summary = {
    "stage": "LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1",
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
            "fee_rate_bps": p["fee_rate_bps"],
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
