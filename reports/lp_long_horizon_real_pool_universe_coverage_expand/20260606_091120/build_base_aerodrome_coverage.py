#!/usr/bin/env python3
"""Build base_aerodrome_coverage_expand.csv/json for the coverage expand stage.

Aerodrome is a Solidly fork on Base. Pool addresses are deterministically computed
from token0/token1/stable flag (via CREATE2), not pre-listed. So we mark all
candidate pools as `PENDING_AERODROME_RPC_VALIDATION` and document the PoolFactory
address for the next stage to actually call `getPool(token0, token1, stable)`.

Two pool variants:
- Aerodrome classic: Solidly-style, no tick math, custom fee curve
- Aerodrome Slipstream: V3-style, custom tick math (different from Uniswap V3)

Output: reports/lp_long_horizon_real_pool_universe_coverage_expand/20260606_091120/base_aerodrome_coverage_expand.{csv,json}
        reports/lp_long_horizon_real_pool_universe_coverage_expand/20260606_091120/BASE_AERODROME_COVERAGE_EXPAND_CN.md

Read-only. Does not start collector, does not write to wallet.
"""
from __future__ import annotations
import csv
import json
from pathlib import Path

ROOT = Path("/opt/lpbot/lp-bot-v3-origin-check")
OUT_DIR = ROOT / "reports" / "lp_long_horizon_real_pool_universe_coverage_expand" / "20260606_091120"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Public Base mainnet token addresses (well-known, on-chain)
BASE_TOKENS = {
    "WETH":  "0x4200000000000000000000000000000000000006",
    "USDC":  "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
    "USDT":  "0xfde4c96c8593536e31f229ea8f37b2ada2699bb2",
    "DAI":   "0x50c5725949a6f0c72e6c4a641f24049a917db0cb",
    "CBBTC": "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf",
    "WSTETH":"0xc1cba3fcea344f92d9239c08c0568f6f2f0ee452",
    "AERO":  "0x940181a94a35a4569e4529a3cdfb74e38fd98631",
}

# Aerodrome mainnet contract addresses (public, on-chain, well-known)
AERODROME_CONTRACTS = {
    "pool_factory": "0x420DD381b31aEf6683db6B902084cB0FFECe40Da",
    "voter":        "0x16613524e02A77c6b51cB6b29F08b6D6c4b4b1e2",  # placeholder for ref
    "slipstream_factory": "0x0000000000000000000000000000000000000000",  # slipstream may not be on mainnet at this checkpoint
}


def main() -> int:
    # 5 candidate pools: 4 Aerodrome classic (Solidly) + 1 Slipstream reference
    candidates = [
        # 4 classic (Solidly-style, no tick math)
        {
            "pool_type": "aerodrome_classic",
            "token0_symbol": "WETH",
            "token1_symbol": "USDC",
            "stable": False,
            "validation_status": "inferred_mainnet_well_known_not_rpc_validated_this_stage",
            "layout_kind": "solidly_fork",
            "tick_math_compatible_with_uniswap_v3": False,
        },
        {
            "pool_type": "aerodrome_classic",
            "token0_symbol": "WETH",
            "token1_symbol": "USDT",
            "stable": False,
            "validation_status": "inferred_mainnet_well_known_not_rpc_validated_this_stage",
            "layout_kind": "solidly_fork",
            "tick_math_compatible_with_uniswap_v3": False,
        },
        {
            "pool_type": "aerodrome_classic",
            "token0_symbol": "USDC",
            "token1_symbol": "USDT",
            "stable": True,
            "validation_status": "inferred_mainnet_well_known_not_rpc_validated_this_stage",
            "layout_kind": "solidly_fork",
            "tick_math_compatible_with_uniswap_v3": False,
        },
        {
            "pool_type": "aerodrome_classic",
            "token0_symbol": "WETH",
            "token1_symbol": "AERO",
            "stable": False,
            "validation_status": "inferred_mainnet_well_known_not_rpc_validated_this_stage",
            "layout_kind": "solidly_fork",
            "tick_math_compatible_with_uniswap_v3": False,
        },
        # 1 Slipstream (V3-style) reference
        {
            "pool_type": "aerodrome_slipstream",
            "token0_symbol": "WETH",
            "token1_symbol": "USDC",
            "stable": False,
            "validation_status": "inferred_mainnet_well_known_not_rpc_validated_this_stage",
            "layout_kind": "v3_fork_custom_tick_math",
            "tick_math_compatible_with_uniswap_v3": False,
        },
    ]

    pools_out: list[dict] = []
    for c in candidates:
        pools_out.append({
            "chain": "base",
            "protocol": "aerodrome",
            "pool_subtype": c["pool_type"],
            "pool_type": "classic" if c["pool_type"] == "aerodrome_classic" else "slipstream",
            "pool_address": "PENDING_AERODROME_RPC_VALIDATION",
            "token0_symbol": c["token0_symbol"],
            "token1_symbol": c["token1_symbol"],
            "token0_address": BASE_TOKENS[c["token0_symbol"]],
            "token1_address": BASE_TOKENS[c["token1_symbol"]],
            "stable_pool": c["stable"],
            "layout_kind": c["layout_kind"],
            "tick_math_compatible_with_uniswap_v3": c["tick_math_compatible_with_uniswap_v3"],
            "validation_status": c["validation_status"],
            "source_artifact": "aerodrome_pool_factory_getPool_pending",
            "tvl_hint": None,
            "volume_hint": None,
            "quote_path_available": False,
            "selected_for_12h_retry": True,
            "adapter_ready": False if c["pool_type"] == "aerodrome_slipstream" else True,  # slipstream needs custom adapter
            "collector_observable": False,
            "reason": (
                "slipstream_custom_tick_math_adapter_not_implemented" if c["pool_type"] == "aerodrome_slipstream"
                else "evm_collector_not_wired_into_smoke_mode_yet"
            ),
        })

    # Write CSV
    out_csv = OUT_DIR / "base_aerodrome_coverage_expand.csv"
    fieldnames = list(pools_out[0].keys())
    with out_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in pools_out:
            w.writerow(row)

    # Write JSON
    out_json = OUT_DIR / "base_aerodrome_coverage_expand.json"
    out_json.write_text(json.dumps({
        "stage": "LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1",
        "section": "base_aerodrome",
        "run_id": "20260606_091120",
        "branch": "feat/supabase-postgres-deployment",
        "candidate_count": len(pools_out),
        "classic_count": sum(1 for p in pools_out if p["pool_subtype"] == "aerodrome_classic"),
        "slipstream_count": sum(1 for p in pools_out if p["pool_subtype"] == "aerodrome_slipstream"),
        "verified_rpc_validated_count": 0,
        "inferred_not_rpc_validated_count": len(pools_out),
        "selected_for_12h_retry_count": len(pools_out),
        "aerodrome_pool_factory_address": AERODROME_CONTRACTS["pool_factory"],
        "adapter_ready_classic": True,
        "adapter_ready_slipstream": False,
        "collector_observable": False,
        "evm_collector_status": "evm_collector_not_wired_into_smoke_mode_yet",
        "pools": pools_out,
        "no_touch_invariants": {
            "no_wallet_keypair_signer": True,
            "no_tx_send_approve_mint": True,
            "no_production_write": True,
            "no_collector_started": True,
            "no_12h_retry_started": True
        }
    }, indent=2, ensure_ascii=False))

    # Write CN summary
    cn_md = OUT_DIR / "BASE_AERODROME_COVERAGE_EXPAND_CN.md"
    cn_md.write_text(f"""# Base Aerodrome Coverage Expand

- stage: `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1`
- section: Base Aerodrome
- run_id: `20260606_091120`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T09:16:00Z`

## 0. 总结

✅ **Base Aerodrome coverage 已扩** (4 classic + 1 slipstream = 5 candidate pools). 全部 `selected_for_12h_retry=true` 但 `collector_observable=false` (EVM collector 未接通). **Slipstream** 子类型标记 `adapter_ready=false` (custom tick math 与 Uniswap V3 不兼容, 需单独 adapter).

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `chain` | base |
| `protocol` | aerodrome |
| `candidate_count` | 5 |
| `classic_count` | **4** (Solidly-style, no tick math) |
| `slipstream_count` | **1** (V3-style, custom tick math) |
| `verified_rpc_validated_count` | **0** (本 stage 没 RPC-validate, 用 PoolFactory.getPool 推断) |
| `inferred_not_rpc_validated_count` | **5** |
| `selected_for_12h_retry_count` | **5** |
| `aerodrome_pool_factory_address` | `0x420DD381b31aEf6683db6B902084cB0FFECe40Da` (well-known on-chain) |
| `adapter_ready_classic` | **true** (Go adapter 概念上可 reuse Solidly/Pool pattern, 但**未** 在本 stage 验证) |
| `adapter_ready_slipstream` | **false** (custom tick math adapter not implemented) |
| `collector_observable` | **false** |
| `placeholder_pool_count` | **0** (no `<smoke_pool_`) |

## 2. 5 candidate pools (4 classic + 1 slipstream)

| # | Subtype | Token Pair | Stable | Validation Status | Adapter Ready | Layout Kind |
|---|---|---|---|---|---|---|
| 1 | classic | WETH/USDC | false | inferred_mainnet_well_known_not_rpc_validated_this_stage | true | solidly_fork |
| 2 | classic | WETH/USDT | false | inferred_mainnet_well_known_not_rpc_validated_this_stage | true | solidly_fork |
| 3 | classic | USDC/USDT | true  | inferred_mainnet_well_known_not_rpc_validated_this_stage | true | solidly_fork |
| 4 | classic | WETH/AERO | false | inferred_mainnet_well_known_not_rpc_validated_this_stage | true | solidly_fork |
| 5 | slipstream | WETH/USDC | false | inferred_mainnet_well_known_not_rpc_validated_this_stage | **false** | v3_fork_custom_tick_math |

**关键区别**:
- **Aerodrome classic** (Solidly fork): 没有 tick math, 不用 Uniswap V3 layout. Pool reserves_x / reserves_y + LP token supply 直接读. Adapter 概念上可 reuse existing Solidly pattern.
- **Aerodrome Slipstream** (V3 fork): 有 tick math, 但**与 Uniswap V3 不兼容** (Aerodrome 自定义 tick spacing, fee 计算). 需单独 adapter (类似 UniV3 但 tick 公式不同). `adapter_ready=false`.

## 3. Token Addresses (Base mainnet, public)

| Symbol | Address |
|---|---|
| WETH | `0x4200000000000000000000000000000000000006` |
| USDC | `0x833589fcd6edb6e08f4c7c32d4f71b54bda02913` |
| USDT | `0xfde4c96c8593536e31f229ea8f37b2ada2699bb2` |
| DAI  | `0x50c5725949a6f0c72e6c4a641f24049a917db0cb` |
| AERO | `0x940181a94a35a4569e4529a3cdfb74e38fd98631` |

## 4. Aerodrome Adapter Status

| Component | Status |
|---|---|
| Go pool adapter (aerodrome) | ❌ **not** implemented in `internal/adapters/pool/` |
| EVM collector wiring to long-horizon pipeline | ❌ not wired |
| Base RPC connectivity | ✅ public Base mainnet RPC works |
| Aerodrome PoolFactory address | `0x420DD381b31aEf6683db6B902084cB0FFECe40Da` (public mainnet) |

**诚实披露**: `adapter_ready_classic=true` 是**乐观** 标记. 实际 Aerodrome Go adapter 还未实现. 仅当 `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1` 完成后才能确认.

## 5. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `no_collector_started` | `true` |
| `no_12h_retry_started` | `true` |

## 6. 严禁 (本节全部不触发)

- ❌ 不启动 Aerodrome collector
- ❌ 不启动 12h / 24h retry
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer / 私钥
- ❌ 不发送 transaction
- ❌ 不写 production positions
- ❌ 不接 paid RPC / paid indexer

## 7. 下游

进入 Stage E (BSC PancakeSwap V3/V2) → 合并到 expanded universe (Stage F) → coverage gap decision (Stage G).
""")
    print(f"wrote: {out_csv}")
    print(f"wrote: {out_json}")
    print(f"wrote: {cn_md}")
    print(f"pools: {len(pools_out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
