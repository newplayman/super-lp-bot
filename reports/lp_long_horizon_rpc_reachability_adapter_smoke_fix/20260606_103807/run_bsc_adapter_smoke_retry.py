#!/usr/bin/env python3
"""Retry BSC adapter smoke with the selected BSC endpoint.

For V2, use PancakeSwap V2 Factory.getPair(tokenA, tokenB) to discover real pairs
(WBNB/USDT, WBNB/USDC, USDT/USDC) and then getReserves on those addresses.

Outputs:
- reports/lp_long_horizon_rpc_reachability_adapter_smoke_fix/20260606_103807/bsc_adapter_smoke_retry.json
- reports/lp_long_horizon_rpc_reachability_adapter_smoke_fix/20260606_103807/BSC_ADAPTER_SMOKE_RETRY_CN.md
"""
from __future__ import annotations
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path("/opt/lpbot/lp-bot-v3-origin-check")
sys.path.insert(0, str(ROOT / "scripts"))
from lp_long_horizon.adapters.evm_bsc_pancakeswap_v3 import (  # noqa: E402
    BSCPancakeV3ReadOnlyAdapter,
)
from lp_long_horizon.adapters.evm_bsc_pancakeswap_v2 import (  # noqa: E402
    BSCPancakeV2ReadOnlyAdapter, PANCAKE_V2_FACTORY, PANCAKE_V2_FEE_BPS,
    cpmm_amount_out,
)
from lp_long_horizon.rpc_registry import select_best_endpoint  # noqa: E402
from lp_long_horizon.utils.retry import retry_with_backoff, classify_429, with_timeout, TimeoutError_  # noqa: E402

OUT_DIR = ROOT / "reports" / "lp_long_horizon_rpc_reachability_adapter_smoke_fix" / "20260606_103807"

# 4 known V3 pools (from bsc_quote_target_candidates.csv)
BSC_V3_POOLS = [
    "0x172fcD41E0913e95784454622d1c3724f546f849",  # WBNB/USDT 0.01%
    "0x36696169C63e42cd08ce11f5deeBbCeBae652050",  # WBNB/USDT 0.05% (verified in prior stage)
    "0xf2688Fb5B81049DFB7703aDa5e770543770612C4",  # WBNB/USDC 0.01%
    "0x81A9b5F18179cE2bf8f001b8a634Db80771F1824",  # WBNB/USDC 0.05%
]
# V2 candidate pairs to discover via factory.getPair
WBNB = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
USDT = "0x55d398326f99059fF775485246999027B3197955"
USDC = "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d"
V2_CANDIDATE_PAIRS = [
    (WBNB, USDT, "WBNB/USDT"),
    (WBNB, USDC, "WBNB/USDC"),
    (USDT, USDC, "USDT/USDC"),
]

# Factory.getPair selector
GET_PAIR_SELECTOR = "0x0d4b2384"


def _encode_address(addr: str) -> str:
    """Encode address as 32-byte left-padded hex."""
    raw = addr[2:].lower() if addr.startswith("0x") else addr.lower()
    return "0x" + raw.rjust(64, "0")


def factory_getpair(endpoint: str, factory: str, token_a: str, token_b: str, timeout_s: float = 5.0) -> dict:
    """Call factory.getPair(tokenA, tokenB) and return the pair address or 0x0..0."""
    data = GET_PAIR_SELECTOR + _encode_address(token_a)[2:] + _encode_address(token_b)[2:]
    body = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "eth_call",
        "params": [{"to": factory, "data": data}, "latest"],
    }).encode("utf-8")
    try:
        def _do():
            req = urllib.request.Request(endpoint, data=body, method="POST",
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                return json.loads(resp.read().decode("utf-8"))
        data = retry_with_backoff(
            _do, max_retries=1, base_delay_s=0.3,
            is_retryable=lambda e: classify_429(e) or isinstance(e, (TimeoutError_, urllib.error.URLError)),
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:80]}
    return data


def main() -> int:
    selected = select_best_endpoint("bsc")
    bsc_endpoint = selected.endpoint if selected else None
    bsc_rpc_reachable = selected is not None

    summaries = []
    pool_snapshot_rows = 0
    quote_snapshot_rows = 0
    error_count = 0

    if not bsc_rpc_reachable:
        for addr in BSC_V3_POOLS:
            summaries.append({
                "adapter": "evm_bsc_pancakeswap_v3",
                "pool_address": addr,
                "snapshot_error": "rpc_unavailable_bsc_no_endpoint",
                "quote_count": 0,
            })
            error_count += 1
        for ta, tb, label in V2_CANDIDATE_PAIRS:
            summaries.append({
                "adapter": "evm_bsc_pancakeswap_v2",
                "pair_label": label,
                "factory_getpair": "rpc_unavailable",
                "getReserves": "n/a",
                "snapshot_error": "rpc_unavailable",
            })
            error_count += 1
    else:
        # V3 smoke
        v3_adapter = BSCPancakeV3ReadOnlyAdapter(timeout_s=5.0, endpoint=bsc_endpoint)
        for addr in BSC_V3_POOLS:
            summary = v3_adapter.fetch_pool_summary(addr)
            if summary.snapshot.error:
                error_count += 1
                pool_inc = 0
                quote_inc = 0
            else:
                pool_inc = 1
                quote_inc = sum(1 for q in summary.quotes if not q.error)
                pool_snapshot_rows += pool_inc
                quote_snapshot_rows += quote_inc
                error_count += sum(1 for q in summary.quotes if q.error)
            summaries.append({
                "adapter": "evm_bsc_pancakeswap_v3",
                "pool_address": addr,
                "snapshot_error": summary.snapshot.error,
                "sqrt_price_x96": summary.snapshot.sqrt_price_x96,
                "tick": summary.snapshot.tick,
                "liquidity": summary.snapshot.liquidity,
                "fee": summary.snapshot.fee,
                "token0": summary.snapshot.token0,
                "token1": summary.snapshot.token1,
                "quote_count": len(summary.quotes),
                "quote_errors": sum(1 for q in summary.quotes if q.error),
            })

        # V2: factory.getPair first, then getReserves
        v2_adapter = BSCPancakeV2ReadOnlyAdapter(timeout_s=5.0, endpoint=bsc_endpoint)
        factory_getpair_success = 0
        getreserves_success = 0
        for ta, tb, label in V2_CANDIDATE_PAIRS:
            gp = factory_getpair(bsc_endpoint, PANCAKE_V2_FACTORY, ta, tb)
            if "error" in gp or "result" not in gp:
                pair_addr = "0x" + "0" * 40  # zero address
                getpair_status = gp.get("error", "no result")[:60]
                getpair_success = False
            else:
                result = gp.get("result", "")
                # last 20 bytes (40 hex chars) is the address
                if len(result) >= 66:
                    pair_addr = "0x" + result[-40:]
                else:
                    pair_addr = "0x" + "0" * 40
                # zero address = 0x0000...0000
                if pair_addr == "0x" + "0" * 40:
                    getpair_status = "pair_not_found"
                    getpair_success = False
                else:
                    getpair_status = "pair_found"
                    getpair_success = True
                    factory_getpair_success += 1

            if getpair_success:
                # Try getReserves on the discovered pair
                v2_summary = v2_adapter.fetch_pool_summary(pair_addr)
                if v2_summary.snapshot.error:
                    getreserves_status = v2_summary.snapshot.error[:60]
                else:
                    getreserves_status = "ok"
                    getreserves_success += 1
                    pool_snapshot_rows += 1
                    quote_snapshot_rows += sum(1 for q in v2_summary.quotes if not q.error)
                error_count += (1 if v2_summary.snapshot.error else 0)
                summaries.append({
                    "adapter": "evm_bsc_pancakeswap_v2",
                    "pair_label": label,
                    "factory_getpair": getpair_status,
                    "discovered_pair_address": pair_addr,
                    "getReserves": getreserves_status,
                    "reserve0": v2_summary.snapshot.reserve0,
                    "reserve1": v2_summary.snapshot.reserve1,
                    "token0": v2_summary.snapshot.token0,
                    "token1": v2_summary.snapshot.token1,
                    "quote_count": len(v2_summary.quotes),
                    "quote_errors": sum(1 for q in v2_summary.quotes if q.error),
                })
            else:
                error_count += 1
                summaries.append({
                    "adapter": "evm_bsc_pancakeswap_v2",
                    "pair_label": label,
                    "factory_getpair": getpair_status,
                    "discovered_pair_address": pair_addr,
                    "getReserves": "skipped_no_pair",
                    "snapshot_error": "factory_getpair_failed",
                })

    # CPMM formula test (independent of RPC)
    cpmm_test = cpmm_amount_out(1000 * 10**18, 1_000_000 * 10**18, 1_000_000 * 10**18, 20)

    out = {
        "stage": "LP_LONG_HORIZON_COLLECTOR_RPC_REACHABILITY_AND_ADAPTER_SMOKE_FIX_V1",
        "section": "bsc_adapter_smoke_retry",
        "run_id": "20260606_103807",
        "branch": "feat/supabase-postgres-deployment",
        "bsc_rpc_reachable": bsc_rpc_reachable,
        "bsc_rpc_selected": bsc_endpoint,
        "pancakeswap_v3_smoke_success_count": sum(1 for s in summaries if s["adapter"] == "evm_bsc_pancakeswap_v3" and not s.get("snapshot_error")),
        "pancakeswap_v2_factory_getpair_success_count": factory_getpair_success if bsc_rpc_reachable else 0,
        "pancakeswap_v2_getreserves_success_count": getreserves_success if bsc_rpc_reachable else 0,
        "pool_snapshot_rows": pool_snapshot_rows,
        "quote_snapshot_rows": quote_snapshot_rows,
        "error_count": error_count,
        "pancake_v2_factory_address": PANCAKE_V2_FACTORY,
        "pancake_v2_fee_bps": PANCAKE_V2_FEE_BPS,
        "cpmm_formula_test_output": cpmm_test,
        "summaries": summaries,
        "no_touch_invariants": {
            "no_wallet_keypair_signer": True,
            "no_tx_send_approve_mint": True,
            "no_production_write": True,
            "no_collector_started": True,
            "no_12h_retry_started": True,
        }
    }
    (OUT_DIR / "bsc_adapter_smoke_retry.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))

    cn = f"""# BSC Adapter Smoke Retry

- stage: `LP_LONG_HORIZON_COLLECTOR_RPC_REACHABILITY_AND_ADAPTER_SMOKE_FIX_V1`
- section: bsc_adapter_smoke_retry
- run_id: `20260606_103807`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T10:44:00Z`

## 0. 总结

{'✅' if bsc_rpc_reachable else '⚠️'} **BSC RPC {'reachable' if bsc_rpc_reachable else 'unreachable'}** ({bsc_endpoint or 'no endpoint'}). Smoke ran with selected endpoint.

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `bsc_rpc_reachable` | **{str(bsc_rpc_reachable).lower()}** |
| `bsc_rpc_selected` | `{bsc_endpoint or 'none'}` |
| `pancakeswap_v3_smoke_success_count` | {out['pancakeswap_v3_smoke_success_count']} / 4 |
| `pancakeswap_v2_factory_getpair_success_count` | {out['pancakeswap_v2_factory_getpair_success_count']} / 3 |
| `pancakeswap_v2_getreserves_success_count` | {out['pancakeswap_v2_getreserves_success_count']} / 3 |
| `pool_snapshot_rows` | {pool_snapshot_rows} |
| `quote_snapshot_rows` | {quote_snapshot_rows} |
| `error_count` | {error_count} |

## 2. BSC V3 smoke (4 pools)

| # | Pool | Status |
|---|---|---|
""" + "".join(
        f"| {i+1} | `{s.get('pool_address', '?')}` | {'OK' if not s.get('snapshot_error') else s.get('snapshot_error', 'err')[:60]} |\n"
        for i, s in enumerate(s for s in summaries if s["adapter"] == "evm_bsc_pancakeswap_v3")
    ) + f"""

## 3. BSC V2 smoke (3 candidate pairs via factory.getPair)

| # | Pair | factory.getPair | discovered address | getReserves |
|---|---|---|---|---|
""" + "".join(
        f"| {i+1} | {s.get('pair_label', '?')} | {s.get('factory_getpair', '?')} | `{s.get('discovered_pair_address', '0x0...0')}` | {s.get('getReserves', 'n/a')} |\n"
        for i, s in enumerate(s for s in summaries if s["adapter"] == "evm_bsc_pancakeswap_v2")
    ) + f"""

## 4. CPMM formula test (independent of RPC)

`cpmm_amount_out(1000 * 10^18, 1_000_000 * 10^18, 1_000_000 * 10^18, 20)` = `{cpmm_test}`

## 5. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `long_run_started` | `false` |

## 6. 严禁

- ❌ 不启动 BSC collector
- ❌ 不启动 12h / 24h retry
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer
- ❌ 不发送 transaction
"""
    (OUT_DIR / "BSC_ADAPTER_SMOKE_RETRY_CN.md").write_text(cn)

    print(f"wrote: {OUT_DIR / 'bsc_adapter_smoke_retry.json'}")
    print(f"wrote: {OUT_DIR / 'BSC_ADAPTER_SMOKE_RETRY_CN.md'}")
    print(f"V3 success: {out['pancakeswap_v3_smoke_success_count']}/4, V2 factory.getPair: {out['pancakeswap_v2_factory_getpair_success_count']}/3, V2 getReserves: {out['pancakeswap_v2_getreserves_success_count']}/3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
