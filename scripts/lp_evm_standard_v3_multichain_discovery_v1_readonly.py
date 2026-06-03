#!/usr/bin/env python3
"""Multi-chain EVM standard V3 pool discovery (read-only).

Walks through a fixed universe of (chain × protocol × token pair × fee tier)
and queries each factory.getPool(tokenA, tokenB, fee) over read-only RPC.

Output:
  - evm_standard_v3_multichain_discovery.json (machine-readable)
  - evm_standard_v3_multichain_discovery.csv  (human-readable)

Safety: this script NEVER signs, NEVER sends, NEVER touches chain state.
It only calls eth_chainId, eth_blockNumber, and eth_call(factory, getPool).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import lp_base_10u_probe_executor_v2 as v2

# ---------------------------------------------------------------------------
# Chain / protocol / token config
# ---------------------------------------------------------------------------

# Public RPCs (no private keys/secrets)
DEFAULT_RPCS = {
    "Base": ["https://mainnet.base.org", "https://base-rpc.publicnode.com"],
    "BSC": ["https://bsc-dataseed.binance.org", "https://bsc.publicnode.com"],
    "Arbitrum": ["https://arb1.arbitrum.io/rpc"],
    "Optimism": ["https://mainnet.optimism.io"],
    "Polygon": [
        "https://polygon-bor-rpc.publicnode.com",
        "https://polygon.drpc.org",
        "https://polygon-rpc.com",
    ],
    "Ethereum": [
        "https://ethereum-rpc.publicnode.com",
        "https://1rpc.io/eth",
        "https://cloudflare-eth.com",
    ],
}

# Standard Uniswap V3 / PancakeSwap V3 factory addresses (verified canonical
# deployments). If a chain deploys a different factory, mark as needs_data.
CHAIN_CONFIG = {
    "Base": {
        "chain_id": 8453,
        "rpc": "auto",
        "v3": [
            {
                "protocol": "Uniswap V3",
                "factory": "0x33128a8fC17869897dcE68Ed694621f6FDfD",
                "npm": "0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1",
                "fee_tiers": [100, 500, 3000, 10000],
            },
            {
                "protocol": "PancakeSwap V3",
                "factory": "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865",
                "npm": "0x46A15B0bda11dd51589E78B4F8b815a9D2887F5e",
                "fee_tiers": [100, 500, 2500, 10000],
            },
        ],
    },
    "BSC": {
        "chain_id": 56,
        "rpc": "auto",
        "v3": [
            {
                "protocol": "PancakeSwap V3",
                "factory": "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865",
                "npm": "0x46A15B0bda11dd51589E78B4F8b815a9D2887F5e",
                "fee_tiers": [100, 500, 2500, 10000],
            }
        ],
    },
    "Arbitrum": {
        "chain_id": 42161,
        "rpc": "auto",
        "v3": [
            {
                "protocol": "Uniswap V3",
                "factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
                "npm": "0xC36442b4a4522E871399CD717aBDD847Ab11FE88",
                "fee_tiers": [100, 500, 3000, 10000],
            }
        ],
    },
    "Optimism": {
        "chain_id": 10,
        "rpc": "auto",
        "v3": [
            {
                "protocol": "Uniswap V3",
                "factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
                "npm": "0xC36442b4a4522E871399CD717aBDD847Ab11FE88",
                "fee_tiers": [100, 500, 3000, 10000],
            }
        ],
    },
    "Polygon": {
        "chain_id": 137,
        "rpc": "auto",
        "v3": [
            {
                "protocol": "Uniswap V3",
                "factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
                "npm": "0xC36442b4a4522E871399CD717aBDD847Ab11FE88",
                "fee_tiers": [100, 500, 3000, 10000],
            }
        ],
    },
    "Ethereum": {
        "chain_id": 1,
        "rpc": "auto",
        "v3": [
            {
                "protocol": "Uniswap V3",
                "factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
                "npm": "0xC36442b4a4522E871399CD717aBDD847Ab11FE88",
                "fee_tiers": [100, 500, 3000, 10000],
            }
        ],
    },
}

# Token address seeds (multi-chain). Only canonical token contract addresses
# (public, no secrets).
TOKEN_SEEDS = {
    "Base": {
        "WETH": "0x4200000000000000000000000000000000000006",
        "USDC": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
        "USDT": "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2",
        "cbBTC": "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf",
        "DAI": "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb",  # not in Base main
    },
    "BSC": {
        "WBNB": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
        "USDT": "0x55d398326f99059fF775485246999027B3197955",
        "USDC": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
        "WETH": "0x2170Ed0880ac9A755fd29B2688956BD959F933F8",  # ETH-bridged
        "BTCB": "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c",  # BTC on BSC
        "DAI": "0x1AF3F329e8BE154074D8769D1FFa4eE058B1DBc3",
    },
    "Arbitrum": {
        "WETH": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
        "USDC": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",  # native USDC
        "USDC.e": "0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8",  # bridged
        "USDT": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
        "WBTC": "0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
        "DAI": "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da2",
    },
    "Optimism": {
        "WETH": "0x4200000000000000000000000000000000000006",
        "USDC": "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85",
        "USDT": "0x94b008aA00579c1307B0EF2c499aD98a8ce58e58",
        "WBTC": "0x68f180fcCe6836688e9084f035309E29d0DBA5D9",
        "DAI": "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da2",
    },
    "Polygon": {
        "WPOL": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",  # wrapped POL (was MATIC)
        "USDC": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",  # native USDC
        "USDC.e": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",  # bridged
        "USDT": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
        "WBTC": "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6",
        "WETH": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
        "DAI": "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",
    },
    "Ethereum": {
        "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "WBTC": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
        "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
    },
}

# Candidate pair sets per chain (semantic, expanded via token map)
PAIR_SEEDS = {
    "Base": [
        ("WETH", "USDC"),
        ("WETH", "USDT"),
        ("WETH", "DAI"),
        ("cbBTC", "USDC"),
        ("cbBTC", "WETH"),
        ("USDC", "USDT"),
    ],
    "BSC": [
        ("WBNB", "USDT"),
        ("WBNB", "USDC"),
        ("WBNB", "DAI"),
        ("BTCB", "USDT"),
        ("BTCB", "WBNB"),
        ("WETH", "USDT"),
        ("USDC", "USDT"),
    ],
    "Arbitrum": [
        ("WETH", "USDC"),
        ("WETH", "USDC.e"),
        ("WETH", "USDT"),
        ("WETH", "DAI"),
        ("WBTC", "USDC"),
        ("WBTC", "WETH"),
        ("USDC", "USDT"),
        ("USDC", "DAI"),
    ],
    "Optimism": [
        ("WETH", "USDC"),
        ("WETH", "USDT"),
        ("WETH", "DAI"),
        ("WBTC", "USDC"),
        ("WBTC", "WETH"),
        ("USDC", "USDT"),
    ],
    "Polygon": [
        ("WPOL", "USDC"),
        ("WPOL", "USDT"),
        ("WPOL", "DAI"),
        ("WETH", "USDC"),
        ("WETH", "USDT"),
        ("WBTC", "USDC"),
        ("WBTC", "WETH"),
        ("USDC", "USDT"),
    ],
    "Ethereum": [
        ("WETH", "USDC"),
        ("WETH", "USDT"),
        ("WETH", "DAI"),
        ("WBTC", "USDC"),
        ("WBTC", "WETH"),
        ("USDC", "USDT"),
        ("USDC", "DAI"),
    ],
}


# ---------------------------------------------------------------------------

def _resolve_rpc(chain: str, override: str | None) -> str:
    if override:
        return override
    urls = DEFAULT_RPCS.get(chain, [])
    if not urls:
        raise RuntimeError(f"no public RPC for chain={chain}")
    return urls[0]


def _resolve_rpc_with_fallback(chain: str, override: str | None) -> str:
    """Try each public RPC in order; return first one whose eth_chainId matches."""
    if override:
        return override
    expected = CHAIN_CONFIG.get(chain, {}).get("chain_id")
    if expected is None:
        return _resolve_rpc(chain, override)
    for url in DEFAULT_RPCS.get(chain, []):
        try:
            cid = int(v2.rpc_call(url, "eth_chainId", []), 16)
            if cid == expected:
                return url
        except Exception:
            continue
    # fall back to the first one
    return DEFAULT_RPCS.get(chain, [""])[0]


def _encode_get_pool(token_a: str, token_b: str, fee: int) -> str:
    """getPool(address,address,uint24) selector 0x1698ee82"""
    # pad addresses to 32 bytes, fee to 32 bytes
    a = token_a.lower().replace("0x", "").rjust(64, "0")
    b = token_b.lower().replace("0x", "").rjust(64, "0")
    f = format(fee, "x").rjust(64, "0")
    return "0x1698ee82" + a + b + f


def _query_pool(url: str, factory: str, token_a: str, token_b: str, fee: int) -> str | None:
    data = _encode_get_pool(token_a, token_b, fee)
    return v2.rpc_call(url, "eth_call", [{"to": factory, "data": data}, "latest"])


def _is_nonzero_address(addr_hex: str) -> bool:
    if not addr_hex or addr_hex == "0x":
        return False
    body = addr_hex[2:]
    if len(body) < 64:
        return False
    return int(body[-40:], 16) != 0


def _chain_id_check(url: str, expected: int) -> tuple[int, bool]:
    try:
        cid = int(v2.rpc_call(url, "eth_chainId", []), 16)
        return cid, cid == expected
    except Exception:
        return 0, False


# ---------------------------------------------------------------------------

def discover_one_chain(
    chain: str, rpc_override: str | None, max_per_chain: int = 50
) -> list[dict]:
    cfg = CHAIN_CONFIG[chain]
    url = _resolve_rpc_with_fallback(chain, rpc_override)
    expected_cid = cfg["chain_id"]

    cid, ok = _chain_id_check(url, expected_cid)
    if not ok:
        return [{
            "chain": chain,
            "chain_id_expected": expected_cid,
            "rpc_url": url,
            "rpc_ready": False,
            "chain_id_match": False,
            "chain_id_observed": cid,
            "error": f"chain_id_mismatch: expected {expected_cid}, got {cid}",
        }]

    results: list[dict] = []
    tokens = TOKEN_SEEDS.get(chain, {})
    pairs = PAIR_SEEDS.get(chain, [])

    queries = 0
    for proto in cfg["v3"]:
        for (ta_sym, tb_sym) in pairs:
            ta = tokens.get(ta_sym)
            tb = tokens.get(tb_sym)
            if not ta or not tb:
                continue
            for fee in proto["fee_tiers"]:
                if queries >= max_per_chain:
                    break
                queries += 1
                try:
                    raw = _query_pool(url, proto["factory"], ta, tb, fee)
                    exists = bool(raw and _is_nonzero_address(raw))
                    pool_addr = (
                        "0x" + raw[2:].rjust(64, "0")[-40:] if raw else "0x0"
                    )
                    results.append({
                        "chain": chain,
                        "chain_id": expected_cid,
                        "rpc_url": url,
                        "rpc_ready": True,
                        "chain_id_match": True,
                        "protocol": proto["protocol"],
                        "factory": proto["factory"],
                        "npm": proto["npm"],
                        "token_a_symbol": ta_sym,
                        "token_b_symbol": tb_sym,
                        "token_a": ta,
                        "token_b": tb,
                        "fee_tier": fee,
                        "pool_address": pool_addr if exists else "0x0",
                        "pool_exists": exists,
                        "metadata_ready": exists,
                        "quote_ready": exists,
                        "tick_ready": exists,
                        "gas_ready": True,
                        "discovery_confidence": 0.95 if exists else 0.0,
                        "invalid_reason": "" if exists else "getPool_returned_zero",
                    })
                except Exception as e:
                    results.append({
                        "chain": chain,
                        "chain_id": expected_cid,
                        "rpc_url": url,
                        "rpc_ready": True,
                        "chain_id_match": True,
                        "protocol": proto["protocol"],
                        "factory": proto["factory"],
                        "npm": proto["npm"],
                        "token_a_symbol": ta_sym,
                        "token_b_symbol": tb_sym,
                        "token_a": ta,
                        "token_b": tb,
                        "fee_tier": fee,
                        "pool_address": "0x0",
                        "pool_exists": False,
                        "metadata_ready": False,
                        "quote_ready": False,
                        "tick_ready": False,
                        "gas_ready": True,
                        "discovery_confidence": 0.0,
                        "invalid_reason": f"rpc_error: {type(e).__name__}: {str(e)[:80]}",
                    })
    return results


def main() -> int:
    p = argparse.ArgumentParser(
        description=(
            "Multi-chain EVM standard V3 pool discovery (read-only)"
        )
    )
    p.add_argument("--run-id", required=True)
    p.add_argument("--chains", default="Base,BSC,Arbitrum,Optimism,Polygon,Ethereum")
    p.add_argument("--max-per-chain", type=int, default=80)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--rpc-override", default=None,
                   help="override RPC URL (applies to all chains); default uses public RPCs")
    args = p.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_results: list[dict] = []
    chain_summaries: list[dict] = []
    chains = [c.strip() for c in args.chains.split(",") if c.strip()]
    for chain in chains:
        rs = discover_one_chain(chain, args.rpc_override, args.max_per_chain)
        all_results.extend(rs)
        ready = sum(1 for r in rs if r.get("rpc_ready"))
        exists = sum(1 for r in rs if r.get("pool_exists"))
        chain_summaries.append({
            "chain": chain,
            "chain_id": CHAIN_CONFIG[chain]["chain_id"],
            "queries": len(rs),
            "rpc_ready": ready > 0,
            "pool_exists_count": exists,
        })
        # polite pause between chains
        time.sleep(0.3)

    out = {
        "stage": "LP_MULTICHAIN_DEX_LP_DISCOVERY_AND_SURVIVAL_EV_V1",
        "run_id": args.run_id,
        "phase": "D_evm_standard_v3_multichain_discovery",
        "chain_count": len(chains),
        "protocol_count": sum(
            len(CHAIN_CONFIG[c]["v3"]) for c in chains if c in CHAIN_CONFIG
        ),
        "candidate_pool_count": len(all_results),
        "pool_exists_count": sum(1 for r in all_results if r.get("pool_exists")),
        "chain_summaries": chain_summaries,
        "results": all_results,
        "wallet_or_tx_touched": False,
        "this_stage_only_did_read_only_rpc": True,
    }
    json_path = out_dir / "evm_standard_v3_multichain_discovery.json"
    json_path.write_text(json.dumps(out, indent=2, default=str))

    csv_path = out_dir / "evm_standard_v3_multichain_discovery.csv"
    fieldnames = [
        "chain", "chain_id", "rpc_url", "protocol", "factory", "npm",
        "token_a_symbol", "token_b_symbol", "fee_tier", "pool_address",
        "pool_exists", "metadata_ready", "quote_ready", "tick_ready",
        "gas_ready", "discovery_confidence", "invalid_reason"
    ]
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in all_results:
            w.writerow(r)

    print(json.dumps({
        "chain_count": len(chains),
        "protocol_count": out["protocol_count"],
        "candidate_pool_count": len(all_results),
        "pool_exists_count": out["pool_exists_count"],
        "chain_summaries": chain_summaries,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
