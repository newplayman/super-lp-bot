#!/usr/bin/env python3
"""Build targeted Meteora DLMM candidate list from GeckoTerminal + DexScreener.

Stage D — collect 30-80 candidates with high-fee / high-volume signals.
Chain verification comes in Stage E. Source level is GeckoTerminal
(direct DLMM pools from Meteora dex) + DexScreener search.
"""
import json
import csv
import os
import urllib.request
import urllib.error
import re
from datetime import datetime, timezone

REPORT_DIR = os.environ["REPORT_DIR"]
os.makedirs(REPORT_DIR, exist_ok=True)
os.makedirs(f"{REPORT_DIR}/data", exist_ok=True)

METEORA_DLMM_PROGRAM = "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"

# Public RPC fallback chain (read-only)
RPC_URLS = [
    "https://solana-rpc.publicnode.com",
    "https://api.mainnet-beta.solana.com",
]


def http_get_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "lpbot-research-readonly/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def http_post_json(url, payload, timeout=15):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "lpbot-research-readonly/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def rpc_get_account_info(pubkey, rpc_url):
    """Read-only getAccountInfo via public RPC."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getAccountInfo",
        "params": [pubkey, {"encoding": "base64", "commitment": "confirmed"}],
    }
    return http_post_json(rpc_url, payload, timeout=12)


def get_geckoterminal_meteora_pools(pages=3):
    """Fetch top Meteora DLMM pools from GeckoTerminal."""
    pools = []
    for p in range(1, pages + 1):
        url = f"https://api.geckoterminal.com/api/v2/networks/solana/dexes/meteora/pools?page={p}"
        try:
            d = http_get_json(url, timeout=15)
        except Exception as e:
            print(f"  GT page {p} error: {e}")
            continue
        for entry in d.get("data", []):
            rel = entry.get("relationships", {})
            dex = rel.get("dex", {}).get("data", {}).get("id", "")
            if dex != "meteora":
                continue
            attrs = entry.get("attributes", {})
            addr = attrs.get("address", "")
            if not addr:
                continue
            name = attrs.get("name", "")
            pair = [s.strip() for s in name.split("/")]
            base_sym = pair[0] if len(pair) > 0 else "?"
            quote_sym = pair[1] if len(pair) > 1 else "?"
            # keep only USDC / SOL / USDT quote
            if quote_sym not in ("USDC", "SOL", "USDT", "WSOL"):
                continue
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
                "price_usd": float(attrs.get("base_token_price_usd", 0) or 0),
                "source_type": "GeckoTerminal",
                "source_url": f"https://www.geckoterminal.com/solana/pools/{addr}",
                "source_confidence": "B",
            })
    return pools


def get_dexscreener_meteora_pairs():
    """Search DexScreener for Meteora + USDC/SOL/USDT pairs."""
    queries = [
        "https://api.dexscreener.com/latest/dex/search?q=meteora%20solana",
        "https://api.dexscreener.com/latest/dex/search?q=meteora%20usdc",
        "https://api.dexscreener.com/latest/dex/search?q=meteora%20sol",
    ]
    seen = set()
    out = []
    for url in queries:
        try:
            d = http_get_json(url, timeout=15)
        except Exception as e:
            print(f"  DS error: {e}")
            continue
        for p in d.get("pairs", []):
            if p.get("dexId", "").lower() != "meteora":
                continue
            if p.get("chainId") != "solana":
                continue
            addr = p.get("pairAddress", "")
            if not addr or addr in seen:
                continue
            seen.add(addr)
            q = p.get("quoteToken", {}).get("symbol", "")
            if q not in ("USDC", "SOL", "USDT", "WSOL"):
                continue
            base = p.get("baseToken", {}).get("symbol", "?")
            vol = p.get("volume", {})
            v24 = float(vol.get("h24", 0) or 0)
            liq = p.get("liquidity", {})
            liq_usd = float(liq.get("usd", 0) or 0) if isinstance(liq, dict) else 0
            out.append({
                "pool_address": addr,
                "name": f"{base}/{q}",
                "base_symbol": base,
                "quote_symbol": q,
                "vol24h_usd": v24,
                "reserve_usd": liq_usd,
                "price_usd": float(p.get("priceUsd", 0) or 0),
                "source_type": "DexScreener",
                "source_url": f"https://dexscreener.com/solana/{addr}",
                "source_confidence": "B",
            })
    return out


def main():
    print("== Stage D: targeted Meteora DLMM candidate collection ==")
    pools = []
    print("fetching GeckoTerminal Meteora DLMM pages 1-3...")
    pools.extend(get_geckoterminal_meteora_pools(pages=3))
    print(f"  GT Meteora DLMM (filtered): {len(pools)}")
    print("fetching DexScreener Meteora pairs...")
    ds = get_dexscreener_meteora_pairs()
    print(f"  DexScreener Meteora (filtered): {len(ds)}")
    pools.extend(ds)

    # dedupe by pool_address; keep first (GT first, DS second)
    seen = set()
    deduped = []
    for p in pools:
        a = p["pool_address"]
        if a in seen:
            continue
        seen.add(a)
        deduped.append(p)

    # sort by vol24h desc
    deduped.sort(key=lambda x: x["vol24h_usd"], reverse=True)

    # annotate: high_fee_hint, target selection
    for p in deduped:
        # volume signals
        if p["vol24h_usd"] >= 1_000_000:
            p["high_volume_candidate"] = True
        else:
            p["high_volume_candidate"] = False
        # fee is unknown at source level; we use SDK decode in Stage F.
        # the "high_fee" flag is set ONLY if we got it from chain in stage F;
        # at collection stage mark fee as unknown.
        p["fee_hint_bps"] = None
        p["selected_for_chain_verify"] = True  # we verify all collected

    # cap at 60 (max from spec)
    if len(deduped) > 60:
        deduped = deduped[:60]

    # write JSON
    out_json = f"{REPORT_DIR}/meteora_targeted_candidate_source_collection.json"
    with open(out_json, "w") as f:
        json.dump(deduped, f, indent=2)
    print(f"wrote {out_json}: {len(deduped)} candidates")

    # write CSV
    out_csv = f"{REPORT_DIR}/meteora_targeted_candidate_source_collection.csv"
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "pool_address", "name", "base_symbol", "quote_symbol",
            "vol24h_usd", "reserve_usd", "price_usd",
            "source_type", "source_url", "source_confidence",
            "high_volume_candidate", "selected_for_chain_verify", "fee_hint_bps",
        ])
        for p in deduped:
            w.writerow([
                p["pool_address"], p["name"], p["base_symbol"], p["quote_symbol"],
                f"{p['vol24h_usd']:.2f}", f"{p['reserve_usd']:.2f}",
                f"{p['price_usd']:.8f}",
                p["source_type"], p["source_url"], p["source_confidence"],
                p["high_volume_candidate"], p["selected_for_chain_verify"],
                p["fee_hint_bps"] if p["fee_hint_bps"] is not None else "",
            ])
    print(f"wrote {out_csv}")

    # summary
    from collections import Counter
    src_counter = Counter(p["source_type"] for p in deduped)
    quote_counter = Counter(p["quote_symbol"] for p in deduped)
    high_vol = sum(1 for p in deduped if p["high_volume_candidate"])

    summary = {
        "stage": "LP_METEORA_DLMM_TARGETED_TOP_POOL_FEED_EXPANSION_V1",
        "run_id": os.environ.get("RUN_ID", ""),
        "candidate_raw_count": len(deduped),
        "source_count_by_type": dict(src_counter),
        "high_volume_candidate_count": high_vol,
        "high_fee_candidate_count": 0,  # cannot determine at collection stage
        "duplicate_count": len(pools) - len(deduped),
        "invalid_count": 0,
        "quote_token_distribution": dict(quote_counter),
        "note": "fee_hint_bps is None at collection; will be set in Stage F (SDK decode).",
    }
    with open(f"{REPORT_DIR}/data/collection_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"summary: {summary}")


if __name__ == "__main__":
    main()
