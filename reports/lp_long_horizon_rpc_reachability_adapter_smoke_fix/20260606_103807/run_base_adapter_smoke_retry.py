#!/usr/bin/env python3
"""Retry Base adapter smoke with the selected Base endpoint (from reachability matrix).

Honest: if Base is unreachable (403 Forbidden in this env), all pool_snapshot_rows=0,
no fake success.

Outputs:
- reports/lp_long_horizon_rpc_reachability_adapter_smoke_fix/20260606_103807/base_adapter_smoke_retry.json
- reports/lp_long_horizon_rpc_reachability_adapter_smoke_fix/20260606_103807/BASE_ADAPTER_SMOKE_RETRY_CN.md
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path("/opt/lpbot/lp-bot-v3-origin-check")
sys.path.insert(0, str(ROOT / "scripts"))
from lp_long_horizon.adapters.evm_base_uniswap_v3 import (  # noqa: E402
    BaseUniV3ReadOnlyAdapter, NOTIONAL_LEVELS_USD,
)
from lp_long_horizon.adapters.evm_base_aerodrome import (  # noqa: E402
    BaseAerodromeReadOnlyAdapter,
)
from lp_long_horizon.rpc_registry import select_best_endpoint  # noqa: E402

OUT_DIR = ROOT / "reports" / "lp_long_horizon_rpc_reachability_adapter_smoke_fix" / "20260606_103807"

# 1 verified Base UniV3 pool + 1 placeholder
BASE_UNIV3_POOLS = [
    "0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38",  # WETH/USDC 0.01% verified
    "0x0000000000000000000000000000000000000a01",  # placeholder
]
# 1 Aerodrome classic + 1 Aerodrome slipstream
BASE_AERODROME_POOLS = [
    ("0x0000000000000000000000000000000000000b01", "classic"),
    ("0x0000000000000000000000000000000000000b02", "slipstream"),
]


def main() -> int:
    selected_base = select_best_endpoint("base")
    base_endpoint = selected_base.endpoint if selected_base else None
    base_rpc_reachable = selected_base is not None

    summaries = []

    if not base_rpc_reachable:
        # Honest: skip smoke, record all failures
        for addr in BASE_UNIV3_POOLS:
            summaries.append({
                "adapter": "evm_base_uniswap_v3",
                "pool_address": addr,
                "snapshot_error": "rpc_unavailable_base_all_endpoints_failed",
                "quote_count": 0,
                "quote_errors": 0,
            })
        for addr, subtype in BASE_AERODROME_POOLS:
            err = "slipstream_not_supported_in_this_stage" if subtype == "slipstream" else "rpc_unavailable_base_all_endpoints_failed"
            summaries.append({
                "adapter": "evm_base_aerodrome",
                "pool_address": addr,
                "pool_subtype": subtype,
                "snapshot_error": err,
                "quote_count": 0,
                "quote_errors": 0,
            })
        pool_snapshot_rows = 0
        quote_snapshot_rows = 0
        error_count = len(summaries)
    else:
        # Run smoke with selected endpoint
        univ3_adapter = BaseUniV3ReadOnlyAdapter(timeout_s=5.0, endpoint=base_endpoint)
        aerodrome_adapter = BaseAerodromeReadOnlyAdapter(timeout_s=5.0, endpoint=base_endpoint)
        for addr in BASE_UNIV3_POOLS:
            summary = univ3_adapter.fetch_pool_summary(addr)
            if summary.snapshot.error:
                error_count_inc = 1
                pool_snapshot_rows_inc = 0
                quote_snapshot_rows_inc = 0
            else:
                error_count_inc = 0
                pool_snapshot_rows_inc = 1
                quote_snapshot_rows_inc = sum(1 for q in summary.quotes if not q.error)
            summaries.append({
                "adapter": "evm_base_uniswap_v3",
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
            pool_snapshot_rows += pool_snapshot_rows_inc
            quote_snapshot_rows += quote_snapshot_rows_inc
            error_count += error_count_inc
        for addr, subtype in BASE_AERODROME_POOLS:
            summary = aerodrome_adapter.fetch_pool_summary(addr, pool_subtype=subtype)
            if subtype == "slipstream":
                err = summary.snapshot.error or "slipstream_not_supported_in_this_stage"
                pool_snapshot_rows_inc = 0
                quote_snapshot_rows_inc = 0
            elif summary.snapshot.error:
                err = summary.snapshot.error
                pool_snapshot_rows_inc = 0
                quote_snapshot_rows_inc = 0
            else:
                err = ""
                pool_snapshot_rows_inc = 1
                quote_snapshot_rows_inc = sum(1 for q in summary.quotes if not q.error)
            summaries.append({
                "adapter": "evm_base_aerodrome",
                "pool_address": addr,
                "pool_subtype": subtype,
                "snapshot_error": err,
                "reserve0": summary.snapshot.reserve0,
                "reserve1": summary.snapshot.reserve1,
                "stable": summary.snapshot.stable,
                "token0": summary.snapshot.token0,
                "token1": summary.snapshot.token1,
                "quote_count": len(summary.quotes),
                "quote_errors": sum(1 for q in summary.quotes if q.error),
            })
            pool_snapshot_rows += pool_snapshot_rows_inc
            quote_snapshot_rows += quote_snapshot_rows_inc
            error_count += (1 if err else 0)

    out = {
        "stage": "LP_LONG_HORIZON_COLLECTOR_RPC_REACHABILITY_AND_ADAPTER_SMOKE_FIX_V1",
        "section": "base_adapter_smoke_retry",
        "run_id": "20260606_103807",
        "branch": "feat/supabase-postgres-deployment",
        "base_rpc_reachable": base_rpc_reachable,
        "base_rpc_selected": base_endpoint,
        "uniswap_v3_smoke_success_count": sum(1 for s in summaries if s["adapter"] == "evm_base_uniswap_v3" and not s["snapshot_error"]),
        "aerodrome_classic_smoke_success_count": sum(1 for s in summaries if s["adapter"] == "evm_base_aerodrome" and s.get("pool_subtype") == "classic" and not s["snapshot_error"]),
        "aerodrome_slipstream_supported": False,  # per spec: marked unsupported
        "slipstream_supported": False,
        "pool_snapshot_rows": pool_snapshot_rows,
        "quote_snapshot_rows": quote_snapshot_rows,
        "error_count": error_count,
        "summaries": summaries,
        "no_touch_invariants": {
            "no_wallet_keypair_signer": True,
            "no_tx_send_approve_mint": True,
            "no_production_write": True,
            "no_collector_started": True,
            "no_12h_retry_started": True,
        }
    }
    (OUT_DIR / "base_adapter_smoke_retry.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))

    cn = f"""# Base Adapter Smoke Retry

- stage: `LP_LONG_HORIZON_COLLECTOR_RPC_REACHABILITY_AND_ADAPTER_SMOKE_FIX_V1`
- section: base_adapter_smoke_retry
- run_id: `20260606_103807`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T10:43:00Z`

## 0. 总结

{'✅' if base_rpc_reachable else '⚠️'} **Base RPC {'reachable' if base_rpc_reachable else 'unreachable'}** ({base_endpoint or 'no endpoint'}). {'Smoke ran with selected endpoint.' if base_rpc_reachable else 'Honest 记录: 4 个 Base public endpoint 全部 403 Forbidden / Connection reset, 不能 reach Base 链. Smoke 跳到 honest 状态.'}

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `base_rpc_reachable` | **{str(base_rpc_reachable).lower()}** |
| `base_rpc_selected` | `{base_endpoint or 'none'}` |
| `uniswap_v3_smoke_success_count` | {out['uniswap_v3_smoke_success_count']} / 2 |
| `aerodrome_classic_smoke_success_count` | {out['aerodrome_classic_smoke_success_count']} / 1 |
| `aerodrome_slipstream_supported` | **false** (per spec, marked unsupported) |
| `slipstream_supported` | **false** |
| `pool_snapshot_rows` | {pool_snapshot_rows} |
| `quote_snapshot_rows` | {quote_snapshot_rows} |
| `error_count` | {error_count} |

## 2. 4 个测试池

| # | Adapter | Subtype | Pool Address | Status |
|---|---|---|---|---|
| 1 | BaseUniV3 | (default) | `0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38` (verified WETH/USDC 0.01%) | {'OK' if summaries[0].get('sqrt_price_x96') else 'rpc_unavailable'} |
| 2 | BaseUniV3 | (default) | `0x0000000000000000000000000000000000000a01` (placeholder) | {'OK' if summaries[1].get('sqrt_price_x96') else 'rpc_unavailable'} |
| 3 | Aerodrome | classic | `0x0000000000000000000000000000000000000b01` | {'OK' if summaries[2].get('reserve0') else 'rpc_unavailable'} |
| 4 | Aerodrome | slipstream | `0x0000000000000000000000000000000000000b02` | slipstream_not_supported_in_this_stage (per spec, marked unsupported) |

## 3. Slipstream adapter gap (per spec)

**Slipstream (V3 fork, custom tick math)**: 标记 `slipstream_not_supported_in_this_stage` honestly. **不** 假装 V3 standard layout.

## 4. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `long_run_started` | `false` |

## 5. 严禁

- ❌ 不启动 Base collector
- ❌ 不启动 12h / 24h retry
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer
- ❌ 不发送 transaction
- ❌ 不接 paid RPC / paid indexer
"""
    (OUT_DIR / "BASE_ADAPTER_SMOKE_RETRY_CN.md").write_text(cn)

    print(f"wrote: {OUT_DIR / 'base_adapter_smoke_retry.json'}")
    print(f"wrote: {OUT_DIR / 'BASE_ADAPTER_SMOKE_RETRY_CN.md'}")
    print(f"base_rpc_reachable: {base_rpc_reachable}, pool_snapshot_rows: {pool_snapshot_rows}, error_count: {error_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
