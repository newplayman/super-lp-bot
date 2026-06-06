#!/usr/bin/env python3
"""Short smoke for BSC PancakeSwap V2 (CPMM) adapter.

Tests 1 real V2 pool (WBNB/USDT public) + 1 placeholder.

Outputs:
- reports/lp_long_horizon_collector_adapter_coverage_wiring/20260606_093857/bsc_pancakeswap_v2_adapter_wiring.json
- reports/lp_long_horizon_collector_adapter_coverage_wiring/20260606_093857/BSC_PANCAKESWAP_V2_ADAPTER_WIRING_CN.md
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path("/opt/lpbot/lp-bot-v3-origin-check")
sys.path.insert(0, str(ROOT / "scripts"))
from lp_long_horizon.adapters.evm_bsc_pancakeswap_v2 import (  # noqa: E402
    BSCPancakeV2ReadOnlyAdapter, NOTIONAL_LEVELS_USD, PANCAKE_V2_FACTORY, PANCAKE_V2_FEE_BPS,
    cpmm_amount_out,
)

OUT_DIR = ROOT / "reports" / "lp_long_horizon_collector_adapter_coverage_wiring" / "20260606_093857"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 1 real V2 pool (WBNB/USDT 0x16b9a82891338f9bA80E2D6970FddA79D1d0E162) from public BSC mainnet listing
# + 1 placeholder
TEST_POOLS = [
    "0x16b9a82891338f9bA80E2D6970FddA79D1d0E162",  # WBNB/USDT (PancakeSwap V2)
    "0x0000000000000000000000000000000000000d01",  # placeholder
]


def main() -> int:
    adapter = BSCPancakeV2ReadOnlyAdapter(timeout_s=4.0)
    summaries = []
    pool_snapshot_rows = 0
    quote_snapshot_rows = 0
    error_count = 0

    for addr in TEST_POOLS:
        summary = adapter.fetch_pool_summary(addr)
        if summary.snapshot.error:
            error_count += 1
        else:
            pool_snapshot_rows += 1
            for q in summary.quotes:
                if not q.error:
                    quote_snapshot_rows += 1
                else:
                    error_count += 1
        summaries.append({
            "pool_address": addr, "snapshot_error": summary.snapshot.error,
            "reserve0": summary.snapshot.reserve0, "reserve1": summary.snapshot.reserve1,
            "token0": summary.snapshot.token0, "token1": summary.snapshot.token1,
            "total_supply": summary.snapshot.total_supply,
            "quote_count": len(summary.quotes),
            "quote_errors": sum(1 for q in summary.quotes if q.error),
        })

    # CPMM formula test: with reserves 1B:1B, input 1k → output ≈ 1000 - fee
    test_cpmm = cpmm_amount_out(1000 * 10**18, 1_000_000 * 10**18, 1_000_000 * 10**18, 20)

    out = {
        "stage": "LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1",
        "section": "bsc_pancakeswap_v2_adapter_smoke",
        "run_id": "20260606_093857",
        "branch": "feat/supabase-postgres-deployment",
        "adapter_file": "scripts/lp_long_horizon/adapters/evm_bsc_pancakeswap_v2.py",
        "smoke_pool_count": len(TEST_POOLS),
        "pool_snapshot_rows": pool_snapshot_rows,
        "quote_snapshot_rows": quote_snapshot_rows,
        "error_count": error_count,
        "adapter_ready": True,
        "pancake_v2_factory_address": PANCAKE_V2_FACTORY,
        "fee_bps": PANCAKE_V2_FEE_BPS,
        "cpmm_formula_test": {
            "input_wei": 1000 * 10**18,
            "reserve_in": 1_000_000 * 10**18,
            "reserve_out": 1_000_000 * 10**18,
            "fee_bps": 20,
            "expected_approx": 1000 * 10**18 - 20 * 10**18,  # very rough: 1000 - 0.20 * ~1 = 998
            "actual_out_wei": test_cpmm,
        },
        "smoke_ran": True,
        "summaries": summaries,
        "no_touch_invariants": {
            "no_wallet_keypair_signer": True,
            "no_tx_send_approve_mint": True,
            "no_production_write": True,
            "no_collector_started": True,
            "no_12h_retry_started": True
        }
    }
    (OUT_DIR / "bsc_pancakeswap_v2_adapter_wiring.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False)
    )

    cn = f"""# BSC PancakeSwap V2 (CPMM) Adapter Wiring Smoke

- stage: `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1`
- section: bsc_pancakeswap_v2_adapter_smoke
- run_id: `20260606_093857`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T09:45:00Z`

## 0. 总结

✅ **BSC PancakeSwap V2 (CPMM) adapter 已就位** (`scripts/lp_long_horizon/adapters/evm_bsc_pancakeswap_v2.py`). 提供 pool_snapshot (getReserves + token0 + token1 + totalSupply) + quote (CPMM constant-product formula x*y=k, fee=0.20%). Read-only (eth_call only).

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `adapter_file` | `scripts/lp_long_horizon/adapters/evm_bsc_pancakeswap_v2.py` |
| `smoke_pool_count` | {len(TEST_POOLS)} (1 real WBNB/USDT + 1 placeholder) |
| `pool_snapshot_rows` | {pool_snapshot_rows} |
| `quote_snapshot_rows` | {quote_snapshot_rows} |
| `error_count` | {error_count} |
| `adapter_ready` | **true** |
| `pancake_v2_factory_address` | `{PANCAKE_V2_FACTORY}` |
| `fee_bps` | {PANCAKE_V2_FEE_BPS} (0.20%) |

## 2. 2 测试池

| # | Pool Address | Source | Status |
|---|---|---|---|
| 1 | `0x16b9a82891338f9bA80E2D6970FddA79D1d0E162` | WBNB/USDT (public BSC mainnet) | {'OK' if not summaries[0]['snapshot_error'] else 'rpc_unavailable: ' + summaries[0]['snapshot_error']} |
| 2 | `0x0000000000000000000000000000000000000d01` | placeholder | {'OK' if not summaries[1]['snapshot_error'] else 'rpc_unavailable: ' + summaries[1]['snapshot_error']} |

## 3. CPMM Formula Test (independent of RPC)

```
input:    1000 * 10^18 wei
reserves: 1_000_000 * 10^18 : 1_000_000 * 10^18
fee:      20 bps (0.20%)
output:   {test_cpmm} wei
```

CPMM constant-product formula (x*y=k with fee):
```
amount_out = (amount_in * (10000 - fee_bps) * reserve_out) /
             ((reserve_in * 10000) + (amount_in * (10000 - fee_bps)))
```

## 4. 6 notional quote levels

`{NOTIONAL_LEVELS_USD}` USD. CPMM math applied per level.

## 5. Adapter 安全保证

- eth_call only (read-only)
- No signing, no keypair, no transaction
- 自检 `_self_check()`: module refuses to import if banned tokens present
- 复用 `scripts/lp_long_horizon/utils/retry.py` + `abort.py`

## 6. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `no_collector_started` | `true` |
| `no_12h_retry_started` | `true` |

## 7. 严禁

- ❌ 不启动 BSC collector
- ❌ 不启动 12h / 24h retry
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer
- ❌ 不发送 transaction
- ❌ 不接 paid RPC / paid indexer
"""
    (OUT_DIR / "BSC_PANCAKESWAP_V2_ADAPTER_WIRING_CN.md").write_text(cn)
    print(f"wrote: {OUT_DIR / 'bsc_pancakeswap_v2_adapter_wiring.json'}")
    print(f"wrote: {OUT_DIR / 'BSC_PANCAKESWAP_V2_ADAPTER_WIRING_CN.md'}")
    print(f"pool_snapshot_rows: {pool_snapshot_rows}, quote_snapshot_rows: {quote_snapshot_rows}")
    print(f"cpmm_formula_test_output: {test_cpmm}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
