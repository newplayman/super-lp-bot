#!/usr/bin/env python3
"""Stage I: Raydium CPMM (AMM v4) quote smoke.

Constant product formula:
  if swapping dx of token A for token B:
    amount_out = (reserveB * dx * (1 - fee)) / (reserveA + dx * (1 - fee))
  slippage vs spot: dy/dx_spot = reserveB/reserveA
  actual_impact: amount_out / (dx * spot) - 1 (positive = worse than spot)

Heuristic: read reserves from decoded pool data, compute quote for 10/20/100/500 USD.

NO wallet / signer / transaction. Pure math.
"""
import json
import csv
import os
from pathlib import Path

REPORT_DIR = os.environ["REPORT_DIR"]

decode_path = Path(REPORT_DIR) / "raydium_cpmm_pool_snapshot.json"
collection_path = Path(REPORT_DIR) / "raydium_cpmm_candidate_source_collection.json"

with open(decode_path) as f:
    decode_data = json.load(f)
with open(collection_path) as f:
    collection_data = json.load(f)

USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
SOL_MINT = "So11111111111111111111111111111111111111112"

# Heuristic: SOL price
SOL_PRICE_USD = 130.0

def pick_in_mint(pool):
    """Pick anchor mint to swap in."""
    if pool.get("token_a") in (USDC_MINT, USDT_MINT): return pool["token_a"]
    if pool.get("token_b") in (USDC_MINT, USDT_MINT): return pool["token_b"]
    if pool.get("token_a") == SOL_MINT: return SOL_MINT
    if pool.get("token_b") == SOL_MINT: return SOL_MINT
    return None

def compute_cpmm_quote(reserve_in, reserve_out, amount_in, fee_bps):
    """Constant product quote with fee on input side (Raydium AMM v4 default).

    amount_in_after_fee = amount_in * (1 - fee)
    amount_out = (reserve_out * amount_in_after_fee) / (reserve_in + amount_in_after_fee)
    """
    if reserve_in <= 0 or reserve_out <= 0 or amount_in <= 0 or fee_bps < 0:
        return None
    fee = fee_bps / 10000.0
    in_after = amount_in * (1 - fee)
    if reserve_in + in_after <= 0:
        return None
    out = (reserve_out * in_after) / (reserve_in + in_after)
    return {
        "amount_out": out,
        "spot_price": reserve_out / reserve_in if reserve_in > 0 else 0,
        "fee": amount_in * fee,
        "price_impact": abs((out / amount_in) - (reserve_out / reserve_in)) / (reserve_out / reserve_in) if reserve_in > 0 and reserve_out > 0 else 0,
    }

def main():
    decoded = [r for r in decode_data if r.get("sdk_decode_success")]
    print(f"decoded pools: {len(decoded)}")

    results = []
    for pool in decoded:
        in_mint = pick_in_mint(pool)
        if not in_mint:
            continue
        # identify which side is in_mint
        if pool["token_a"] == in_mint:
            reserve_in = int(pool.get("reserve_a_raw") or 0)
            reserve_out = int(pool.get("reserve_b_raw") or 0)
            decimals_in = pool.get("token_a_decimals") or 0
            decimals_out = pool.get("token_b_decimals") or 0
            out_mint = pool["token_b"]
        else:
            reserve_in = int(pool.get("reserve_b_raw") or 0)
            reserve_out = int(pool.get("reserve_a_raw") or 0)
            decimals_in = pool.get("token_b_decimals") or 0
            decimals_out = pool.get("token_a_decimals") or 0
            out_mint = pool["token_a"]
        if reserve_in == 0 or reserve_out == 0:
            continue

        fee_bps = pool.get("fee_bps") or 25  # default 25bps for AMM v4

        # Quote for 10, 20, 100, 500 USD
        usd_notionals = [10, 20, 100, 500]
        for usd in usd_notionals:
            # convert usd to raw in_amount
            if in_mint in (USDC_MINT, USDT_MINT):
                in_raw = usd * (10 ** decimals_in)
            elif in_mint == SOL_MINT:
                sol_amount = usd / SOL_PRICE_USD
                in_raw = int(sol_amount * (10 ** decimals_in))
            else:
                # skip non-anchor
                continue

            q = compute_cpmm_quote(reserve_in, reserve_out, in_raw, fee_bps)
            if q is None:
                continue
            # require price impact < 5% for "low slippage"
            low_slippage = q["price_impact"] < 0.05
            results.append({
                "pool_address": pool["pool_address"],
                "notional_usd": usd,
                "token_in": in_mint,
                "token_out": out_mint,
                "amount_in_raw": in_raw,
                "quote_success": True,
                "amount_out_raw": int(q["amount_out"]),
                "price_impact": round(q["price_impact"], 6),
                "fee": int(q["fee"]),
                "fee_bps": fee_bps,
                "spot_price": round(q["spot_price"], 12),
                "quote_method": "constant_product_formula",
                "low_slippage": low_slippage,
                "confidence": 0.85,
                "invalid_reason": None,
            })

    # write JSON
    out_json = f"{REPORT_DIR}/raydium_cpmm_quote_smoke.json"
    with open(out_json, "w") as f:
        json.dump(results, f, indent=2)
    print(f"wrote {out_json}: {len(results)}")

    # CSV
    out_csv = f"{REPORT_DIR}/raydium_cpmm_quote_smoke.csv"
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "pool_address", "notional_usd", "token_in", "token_out",
            "amount_in_raw", "quote_success", "amount_out_raw",
            "price_impact", "fee", "fee_bps", "spot_price", "quote_method",
            "low_slippage", "confidence", "invalid_reason",
        ])
        for r in results:
            w.writerow([
                r["pool_address"], r["notional_usd"], r["token_in"], r["token_out"],
                r["amount_in_raw"], r["quote_success"], r["amount_out_raw"],
                r["price_impact"], r["fee"], r["fee_bps"], r["spot_price"],
                r["quote_method"], r["low_slippage"], r["confidence"],
                r.get("invalid_reason", "") or "",
            ])
    print(f"wrote {out_csv}")

    # summary
    n_quote_pools = len(set(r["pool_address"] for r in results if r["quote_success"]))
    n_10 = sum(1 for r in results if r["notional_usd"] == 10 and r["quote_success"])
    n_20 = sum(1 for r in results if r["notional_usd"] == 20 and r["quote_success"])
    n_100 = sum(1 for r in results if r["notional_usd"] == 100 and r["quote_success"])
    n_500 = sum(1 for r in results if r["notional_usd"] == 500 and r["quote_success"])
    n_high_fee = sum(1 for r in results if r["quote_success"] and r["fee_bps"] >= 30)
    n_low_slip = sum(1 for r in results if r["quote_success"] and r["low_slippage"])
    summary = {
        "stage": "LP_RAYDIUM_CPMM_READONLY_CONNECTOR_V1",
        "run_id": os.environ.get("RUN_ID", ""),
        "candidate_count": len(results),
        "quote_ready_pool_count": n_quote_pools,
        "quote_10u_success_count": n_10,
        "quote_20u_success_count": n_20,
        "quote_100u_success_count": n_100,
        "quote_500u_success_count": n_500,
        "high_fee_quote_ready_count": n_high_fee,
        "low_slippage_pool_count": n_low_slip,
    }
    with open(f"{REPORT_DIR}/data/quote_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"summary: {summary}")


if __name__ == "__main__":
    main()
