#!/usr/bin/env python3
"""Stage E: Orca Whirlpool candidate source collection.

Sources (priority):
  A. Orca official API: https://api.mainnet.orca.so/v1/whirlpool/list (14983 pools)
  B. GeckoTerminal Solana Orca pools
  C. DexScreener Solana Orca pairs

For each candidate, record source_type and source_confidence.
Output: orca_candidate_source_collection.{json,csv}
"""
import json
import csv
import os
import urllib.request
import time

REPORT_DIR = os.environ["REPORT_DIR"]
os.makedirs(f"{REPORT_DIR}/data", exist_ok=True)

ORCA_PROGRAM = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"


def http_get_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "lpbot-research-readonly/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def get_orca_official_pools():
    """14983 Orca mainnet pools, full metadata."""
    url = "https://api.mainnet.orca.so/v1/whirlpool/list"
    try:
        d = http_get_json(url, timeout=60)
    except Exception as e:
        print(f"  Orca API error: {e}")
        return []
    pools = []
    for p in d.get("whirlpools", []):
        a = p.get("address")
        if not a:
            continue
        tok_a = p.get("tokenA") or {}
        tok_b = p.get("tokenB") or {}
        sym_a = tok_a.get("symbol", "?")
        sym_b = tok_b.get("symbol", "?")
        fee_rate = p.get("lpFeeRate")  # fraction (e.g. 0.0004 for 4bps)
        tvl = p.get("tvl", 0) or 0
        vol = p.get("volume", {})
        vol24 = float((vol or {}).get("day", 0) or 0)
        tick_spacing = p.get("tickSpacing")
        pools.append({
            "pool_address": a,
            "name": f"{sym_a}/{sym_b}",
            "base_symbol": sym_a,
            "quote_symbol": sym_b,
            "token_a_mint": tok_a.get("mint", ""),
            "token_b_mint": tok_b.get("mint", ""),
            "token_a_decimals": tok_a.get("decimals"),
            "token_b_decimals": tok_b.get("decimals"),
            "tick_spacing": tick_spacing,
            "fee_rate": fee_rate,
            "fee_rate_bps": int(fee_rate * 10000) if fee_rate is not None else None,
            "tvl_usd": tvl,
            "vol24h_usd": vol24,
            "source_type": "OrcaOfficial",
            "source_url": f"https://www.orca.so/pools/{a}",
            "source_confidence": "A",
        })
    return pools


def get_gecko_orca_pools():
    """GeckoTerminal Solana Orca (whirlpools) pools."""
    pools = []
    for page in [1, 2]:
        url = f"https://api.geckoterminal.com/api/v2/networks/solana/dexes/orca_whirlpools/pools?page={page}"
        try:
            d = http_get_json(url, timeout=20)
        except Exception as e:
            print(f"  GeckoTerminal page {page} error: {e}")
            continue
        for entry in d.get("data", []):
            rel = entry.get("relationships", {})
            dex = rel.get("dex", {}).get("data", {}).get("id", "")
            if "orca" not in dex.lower() and "whirlpool" not in dex.lower():
                continue
            attrs = entry.get("attributes", {})
            addr = attrs.get("address", "")
            if not addr:
                continue
            name = attrs.get("name", "")
            pair = [s.strip() for s in name.split("/")]
            base_sym = pair[0] if len(pair) > 0 else "?"
            quote_sym = pair[1] if len(pair) > 1 else "?"
            vol = attrs.get("volume_usd", {})
            v24 = float(vol.get("h24", 0) or 0)
            reserve = float(attrs.get("reserve_in_usd", 0) or 0)
            pools.append({
                "pool_address": addr,
                "name": name,
                "base_symbol": base_sym,
                "quote_symbol": quote_sym,
                "vol24h_usd": v24,
                "reserve_usd": reserve,
                "source_type": "GeckoTerminal",
                "source_url": f"https://www.geckoterminal.com/solana/pools/{addr}",
                "source_confidence": "B",
            })
    return pools


def get_dex_orca_pairs():
    """DexScreener search for Orca Solana pairs."""
    pools = []
    for q in ["orca%20solana", "orca%20usdc", "orca%20sol"]:
        url = f"https://api.dexscreener.com/latest/dex/search?q={q}"
        try:
            d = http_get_json(url, timeout=20)
        except Exception as e:
            print(f"  DS error: {e}")
            continue
        for p in d.get("pairs", []):
            if p.get("dexId", "").lower() != "whirlpool" and "orca" not in p.get("dexId", "").lower():
                continue
            if p.get("chainId") != "solana":
                continue
            addr = p.get("pairAddress", "")
            if not addr:
                continue
            base = p.get("baseToken", {}).get("symbol", "?")
            quote = p.get("quoteToken", {}).get("symbol", "?")
            vol = p.get("volume", {})
            v24 = float(vol.get("h24", 0) or 0)
            liq = p.get("liquidity", {})
            liq_usd = float(liq.get("usd", 0) or 0) if isinstance(liq, dict) else 0
            pools.append({
                "pool_address": addr,
                "name": f"{base}/{quote}",
                "base_symbol": base,
                "quote_symbol": quote,
                "vol24h_usd": v24,
                "reserve_usd": liq_usd,
                "source_type": "DexScreener",
                "source_url": f"https://dexscreener.com/solana/{addr}",
                "source_confidence": "B",
            })
    return pools


def main():
    print("== Stage E: Orca candidate collection ==")
    print("fetching Orca official API (14983 pools)...")
    orca = get_orca_official_pools()
    print(f"  Orca official: {len(orca)}")
    print("fetching GeckoTerminal Orca pools...")
    gecko = get_gecko_orca_pools()
    print(f"  GeckoTerminal: {len(gecko)}")
    print("fetching DexScreener Orca pairs...")
    ds = get_dex_orca_pairs()
    print(f"  DexScreener: {len(ds)}")

    # dedupe by pool_address
    seen = set()
    all_pools = []
    for src in (orca, gecko, ds):
        for p in src:
            a = p["pool_address"]
            if a in seen:
                continue
            seen.add(a)
            all_pools.append(p)

    # Filter to high-fee / high-volume
    # Orca fee tiers: 1bps, 4bps, 5bps, 12bps, 30bps, 100bps (per pool.tickSpacing or lpFeeRate)
    # Strategy: keep all from official API (already filtered by Orca), but prioritize high-fee (>=30bps) and high-volume
    high_fee = [p for p in all_pools if (p.get("fee_rate_bps") or 0) >= 30]
    high_vol = [p for p in all_pools if p.get("vol24h_usd", 0) >= 1_000_000]
    has_anchor = [p for p in all_pools if p.get("quote_symbol") in ("USDC", "USDT", "SOL", "wsol") or p.get("base_symbol") in ("USDC", "USDT", "SOL", "wsol")]

    print(f"total unique: {len(all_pools)}")
    print(f"  high_fee (>=30bps): {len(high_fee)}")
    print(f"  high_vol (vol24h >= $1M): {len(high_vol)}")
    print(f"  has anchor USDC/SOL: {len(has_anchor)}")

    # Pick: high-fee anchor + high-vol anchor
    selected = []
    seen_addr = set()
    for p in sorted(high_fee, key=lambda x: -(x.get("vol24h_usd") or 0))[:40]:
        if p["pool_address"] not in seen_addr:
            p["selected_for_chain_verify"] = True
            selected.append(p)
            seen_addr.add(p["pool_address"])
    for p in sorted(high_vol, key=lambda x: -(x.get("vol24h_usd") or 0))[:40]:
        if p["pool_address"] not in seen_addr:
            p["selected_for_chain_verify"] = True
            selected.append(p)
            seen_addr.add(p["pool_address"])
    # cap at 80
    if len(selected) > 80:
        selected = selected[:80]
    # mark unselected
    for p in all_pools:
        if p["pool_address"] not in seen_addr:
            p["selected_for_chain_verify"] = False

    # write JSON
    out_json = f"{REPORT_DIR}/orca_candidate_source_collection.json"
    with open(out_json, "w") as f:
        json.dump(all_pools, f, indent=2)
    print(f"wrote {out_json}: {len(all_pools)} total")

    # CSV — only selected
    out_csv = f"{REPORT_DIR}/orca_candidate_source_collection.csv"
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "pool_address", "name", "base_symbol", "quote_symbol",
            "tick_spacing", "fee_rate_bps", "tvl_usd", "vol24h_usd",
            "source_type", "source_url", "source_confidence",
            "selected_for_chain_verify",
        ])
        for p in all_pools:
            w.writerow([
                p.get("pool_address", ""),
                p.get("name", ""),
                p.get("base_symbol", ""),
                p.get("quote_symbol", ""),
                p.get("tick_spacing", ""),
                p.get("fee_rate_bps", ""),
                p.get("tvl_usd", ""),
                p.get("vol24h_usd", ""),
                p.get("source_type", ""),
                p.get("source_url", ""),
                p.get("source_confidence", ""),
                p.get("selected_for_chain_verify", False),
            ])
    print(f"wrote {out_csv}")

    from collections import Counter
    src_counter = Counter(p["source_type"] for p in all_pools)
    summary = {
        "stage": "LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1",
        "run_id": os.environ.get("RUN_ID", ""),
        "candidate_raw_count": len(all_pools),
        "selected_for_chain_verify_count": len(selected),
        "source_count_by_type": dict(src_counter),
        "high_fee_candidate_count": len(high_fee),
        "high_volume_candidate_count": len(high_vol),
        "has_anchor_count": len(has_anchor),
        "duplicate_count": (len(orca) + len(gecko) + len(ds)) - len(all_pools),
    }
    with open(f"{REPORT_DIR}/data/collection_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"summary: {summary}")


if __name__ == "__main__":
    main()
