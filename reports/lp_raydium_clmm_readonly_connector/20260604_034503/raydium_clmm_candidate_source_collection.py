#!/usr/bin/env python3
"""Stage E: Raydium CLMM candidate source collection.

Sources (priority):
  A. (Raydium official API v2 404; falling back to GeckoTerminal)
  B. GeckoTerminal Solana Raydium CLMM pools (dex=raydium-clmm)
  C. DexScreener Solana Raydium pairs

For each candidate, record source_type and source_confidence.
Output: raydium_clmm_candidate_source_collection.{json,csv}
"""
import json
import csv
import os
import urllib.request

REPORT_DIR = os.environ["REPORT_DIR"]
os.makedirs(f"{REPORT_DIR}/data", exist_ok=True)

RAYDIUM_CLMM_PROGRAM = "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK"


def http_get_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "lpbot-research-readonly/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def get_gecko_raydium_clmm_pools(pages=3):
    pools = []
    for p in range(1, pages + 1):
        url = f"https://api.geckoterminal.com/api/v2/networks/solana/dexes/raydium-clmm/pools?page={p}"
        try:
            d = http_get_json(url, timeout=20)
        except Exception as e:
            print(f"  GeckoTerminal page {p} error: {e}")
            continue
        for entry in d.get("data", []):
            rel = entry.get("relationships", {})
            dex = rel.get("dex", {}).get("data", {}).get("id", "")
            if dex != "raydium-clmm":
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


def get_dex_raydium_clmm_pairs():
    pools = []
    for q in ["raydium%20clmm", "raydium%20usdc%20clmm", "raydium%20sol%20clmm"]:
        url = f"https://api.dexscreener.com/latest/dex/search?q={q}"
        try:
            d = http_get_json(url, timeout=20)
        except Exception as e:
            print(f"  DS error: {e}")
            continue
        for p in d.get("pairs", []):
            if p.get("dexId", "").lower() != "raydium_clmm" and "raydium" not in p.get("dexId", "").lower():
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
    print("== Stage E: Raydium CLMM candidate collection ==")
    print("fetching GeckoTerminal raydium-clmm (3 pages)...")
    gecko = get_gecko_raydium_clmm_pools(pages=3)
    print(f"  GeckoTerminal: {len(gecko)}")
    print("fetching DexScreener Raydium pairs...")
    ds = get_dex_raydium_clmm_pairs()
    print(f"  DexScreener: {len(ds)}")

    # dedupe
    seen = set()
    all_pools = []
    for src in (gecko, ds):
        for p in src:
            a = p["pool_address"]
            if a in seen:
                continue
            seen.add(a)
            all_pools.append(p)

    print(f"total unique: {len(all_pools)}")

    # Select strategy: high-volume + has anchor
    high_vol = [p for p in all_pools if p.get("vol24h_usd", 0) >= 100_000]
    has_anchor = [p for p in all_pools if p.get("quote_symbol") in ("USDC", "USDT", "SOL", "WSOL") or p.get("base_symbol") in ("USDC", "USDT", "SOL", "WSOL")]
    print(f"  high_vol (vol24h >= $100k): {len(high_vol)}")
    print(f"  has anchor USDC/SOL: {len(has_anchor)}")

    # Select up to 80
    selected = []
    seen_addr = set()
    # priority: high_vol + has_anchor
    for p in sorted(high_vol, key=lambda x: -(x.get("vol24h_usd") or 0)):
        if p["pool_address"] not in seen_addr and p["pool_address"] in {h["pool_address"] for h in has_anchor}:
            p["selected_for_chain_verify"] = True
            selected.append(p)
            seen_addr.add(p["pool_address"])
            if len(selected) >= 60:
                break
    # rest
    for p in sorted(all_pools, key=lambda x: -(x.get("vol24h_usd") or 0)):
        if p["pool_address"] not in seen_addr:
            p["selected_for_chain_verify"] = True
            selected.append(p)
            seen_addr.add(p["pool_address"])
            if len(selected) >= 80:
                break

    # mark unselected
    for p in all_pools:
        if p["pool_address"] not in seen_addr:
            p["selected_for_chain_verify"] = False

    # write JSON
    out_json = f"{REPORT_DIR}/raydium_clmm_candidate_source_collection.json"
    with open(out_json, "w") as f:
        json.dump(all_pools, f, indent=2)
    print(f"wrote {out_json}: {len(all_pools)} total")

    # CSV
    out_csv = f"{REPORT_DIR}/raydium_clmm_candidate_source_collection.csv"
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "pool_address", "name", "base_symbol", "quote_symbol",
            "vol24h_usd", "reserve_usd",
            "source_type", "source_url", "source_confidence",
            "selected_for_chain_verify",
        ])
        for p in all_pools:
            w.writerow([
                p.get("pool_address", ""),
                p.get("name", ""),
                p.get("base_symbol", ""),
                p.get("quote_symbol", ""),
                f"{p.get('vol24h_usd', 0):.2f}",
                f"{p.get('reserve_usd', 0):.2f}",
                p.get("source_type", ""),
                p.get("source_url", ""),
                p.get("source_confidence", ""),
                p.get("selected_for_chain_verify", False),
            ])
    print(f"wrote {out_csv}")

    from collections import Counter
    src_counter = Counter(p["source_type"] for p in all_pools)
    summary = {
        "stage": "LP_RAYDIUM_CLMM_READONLY_CONNECTOR_V1",
        "run_id": os.environ.get("RUN_ID", ""),
        "candidate_raw_count": len(all_pools),
        "selected_for_chain_verify_count": len(selected),
        "source_count_by_type": dict(src_counter),
        "high_volume_candidate_count": len(high_vol),
        "has_anchor_count": len(has_anchor),
        "duplicate_count": (len(gecko) + len(ds)) - len(all_pools),
    }
    with open(f"{REPORT_DIR}/data/collection_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"summary: {summary}")


if __name__ == "__main__":
    main()
