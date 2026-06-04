#!/usr/bin/env python3
"""Stage E: Stable pool candidate source collection.

Sources (priority):
  A. Meteora DAMM v2 API (with strict on-chain owner verify in Stage F)
  B. Orca official API (14983 whirlpools; filter LST-stable)
  C. Meteora Stable Swap (ex-Saber) - on-chain discovery
  D. DexScreener (cross-check)

Output: stable_pool_candidate_source_collection.{json,csv}
"""
import json
import csv
import os
import urllib.request

REPORT_DIR = os.environ["REPORT_DIR"]
os.makedirs(f"{REPORT_DIR}/data", exist_ok=True)

ORCA_WHIRLPOOL = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
RAYDIUM_AMM_V4 = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
METEORA_DAMM_V2 = "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG"
METEORA_STABLE_SWAP = "SSwpkEEcbUqx4vtoEByFjSkhKdCT862DNVb52nZg1UZ"

USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
USDS_MINT = "2b1kV6DkMAjuzdw3XgZFuqAQnMYc1bo1U7Q4eWFQHrYH"
SOL_MINT = "So11111111111111111111111111111111111111112"
MSOL_MINT = "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So"
JITOSOL_MINT = "J1toso1uB3qeiYvot5HXxX7v9DGuQ6FBMTSqdwLB5XbZ"
BSOL_MINT = "bSo13r4TkiE4KumLAtLs5w2upAfMRJqQuL4LbXYAdJBP"
JUPSOL_MINT = "jupSoLaHXQiZZTSfXWM7RPKL6Eq2bZwcj8K4KvfN2mk"


def http_get_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "lpbot-research-readonly/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def get_orca_stable_pools():
    """From Orca official API, filter to USDC/USDT/LST stable-anchor pools."""
    url = "https://api.mainnet.orca.so/v1/whirlpool/list"
    try:
        d = http_get_json(url, timeout=60)
    except Exception as e:
        print(f"  Orca API error: {e}")
        return []
    wh = d.get("whirlpools", [])
    pools = []
    for p in wh:
        tokA = p.get("tokenA", {})
        tokB = p.get("tokenB", {})
        symA = tokA.get("symbol", "")
        symB = tokB.get("symbol", "")
        mintA = tokA.get("mint", "")
        mintB = tokB.get("mint", "")
        # Filter to LST-stable / stable-stable
        is_stable = (
            (symA in ("USDC", "USDT", "USDS") and symB in ("USDC", "USDT", "USDS")) or
            (symA in ("USDC", "USDT") and symB in ("SOL", "mSOL", "jitoSOL", "bSOL", "jupSOL")) or
            (symB in ("USDC", "USDT") and symA in ("SOL", "mSOL", "jitoSOL", "bSOL", "jupSOL"))
        )
        if not is_stable:
            continue
        # Filter for active pools (TVL > 1000)
        tvl = p.get("tvl", 0) or 0
        if tvl < 1000:
            continue
        vol = p.get("volume", {}).get("day", 0) or 0
        pools.append({
            "pool_address": p.get("address", ""),
            "name": p.get("name", ""),
            "base_symbol": symA,
            "quote_symbol": symB,
            "base_mint": mintA,
            "quote_mint": mintB,
            "tick_spacing": p.get("tickSpacing"),
            "vol24h_usd": vol,
            "tvl_usd": tvl,
            "source_type": "OrcaOfficial",
            "source_url": f"https://www.orca.so/pools/{p.get('address','')}",
            "source_confidence": "A",
        })
    return pools


def get_meteora_damm_v2_stable_pools():
    """From Meteora DAMM v2 API, pool_type=stable. Strict filter for USDC/USDT/USDS pairs."""
    pools = []
    # Search for each stable pair
    for pair in ["USDC-USDT", "USDC-USDS", "USDT-USDS", "USDC-mSOL", "USDT-mSOL", "USDC-jitoSOL", "USDC-bSOL"]:
        try:
            url = f"https://amm-v2.meteora.ag/pools/search?page=0&size=20&include_pool_token_pairs={pair}"
            d = http_get_json(url, timeout=20)
        except Exception as e:
            print(f"  Meteora API {pair} error: {e}")
            continue
        for p in d.get("data", []):
            # Strict filter: pool_type=stable AND has TVL > 1000
            if p.get("pool_type") != "stable":
                continue
            tvl = float(p.get("pool_tvl", 0) or 0)
            if tvl < 1000:
                continue
            vol = float(p.get("weekly_trading_volume", 0) or 0)
            pools.append({
                "pool_address": p.get("pool_address", ""),
                "name": p.get("pool_name", ""),
                "base_symbol": pair.split("-")[0],
                "quote_symbol": pair.split("-")[1],
                "tvl_usd": tvl,
                "vol24h_usd": vol,
                "source_type": "MeteoraDAMMv2",
                "source_url": f"https://app.meteora.ag/clmm-api/pool/{p.get('pool_address','')}",
                "source_confidence": "B",
            })
    return pools


def main():
    print("== Stage E: Stable pool candidate collection ==")
    print("fetching Orca stable pools (14983 whirlpools)...")
    orca_pools = get_orca_stable_pools()
    print(f"  Orca: {len(orca_pools)} stable-active (tvl>1000)")
    print("fetching Meteora DAMM v2 stable pools...")
    meteora_pools = get_meteora_damm_v2_stable_pools()
    print(f"  Meteora DAMM v2: {len(meteora_pools)} stable-active (tvl>1000)")

    # dedupe
    seen = set()
    all_pools = []
    for src in (orca_pools, meteora_pools):
        for p in src:
            a = p["pool_address"]
            if a in seen:
                continue
            seen.add(a)
            all_pools.append(p)

    print(f"total unique: {len(all_pools)}")

    # Select up to 80
    selected = []
    seen_addr = set()
    # priority: TVL
    for p in sorted(all_pools, key=lambda x: -(x.get("tvl_usd") or x.get("vol24h_usd", 0))):
        if p["pool_address"] not in seen_addr:
            p["selected_for_chain_verify"] = True
            selected.append(p)
            seen_addr.add(p["pool_address"])
            if len(selected) >= 80:
                break

    for p in all_pools:
        if p["pool_address"] not in seen_addr:
            p["selected_for_chain_verify"] = False

    # write JSON
    out_json = f"{REPORT_DIR}/stable_pool_candidate_source_collection.json"
    with open(out_json, "w") as f:
        json.dump(all_pools, f, indent=2)
    print(f"wrote {out_json}: {len(all_pools)} total")

    # CSV
    out_csv = f"{REPORT_DIR}/stable_pool_candidate_source_collection.csv"
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "pool_address", "name", "base_symbol", "quote_symbol",
            "tvl_usd", "vol24h_usd", "tick_spacing",
            "source_type", "source_url", "source_confidence",
            "selected_for_chain_verify",
        ])
        for p in all_pools:
            w.writerow([
                p.get("pool_address", ""),
                p.get("name", ""),
                p.get("base_symbol", ""),
                p.get("quote_symbol", ""),
                f"{p.get('tvl_usd', 0):.2f}",
                f"{p.get('vol24h_usd', 0):.2f}",
                p.get("tick_spacing", ""),
                p.get("source_type", ""),
                p.get("source_url", ""),
                p.get("source_confidence", ""),
                p.get("selected_for_chain_verify", False),
            ])
    print(f"wrote {out_csv}")

    from collections import Counter
    src_counter = Counter(p["source_type"] for p in all_pools)
    summary = {
        "stage": "LP_SOLANA_STABLE_POOL_RESEARCH_V1",
        "run_id": os.environ.get("RUN_ID", ""),
        "candidate_raw_count": len(all_pools),
        "selected_for_chain_verify_count": len(selected),
        "source_count_by_type": dict(src_counter),
        "duplicate_count": (len(orca_pools) + len(meteora_pools)) - len(all_pools),
    }
    with open(f"{REPORT_DIR}/data/collection_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"summary: {summary}")


if __name__ == "__main__":
    main()
