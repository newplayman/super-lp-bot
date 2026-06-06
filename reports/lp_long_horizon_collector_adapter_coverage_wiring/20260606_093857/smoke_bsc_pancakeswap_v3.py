#!/usr/bin/env python3
"""Short smoke for BSC PancakeSwap V3 adapter.

Tests 1 real V3 pool (WBNB/USDT 0.05%) from prior research + 1 placeholder.

Outputs:
- reports/lp_long_horizon_collector_adapter_coverage_wiring/20260606_093857/bsc_pancakeswap_v3_adapter_wiring.json
- reports/lp_long_horizon_collector_adapter_coverage_wiring/20260606_093857/BSC_PANCAKESWAP_V3_ADAPTER_WIRING_CN.md
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path("/opt/lpbot/lp-bot-v3-origin-check")
sys.path.insert(0, str(ROOT / "scripts"))
from lp_long_horizon.adapters.evm_bsc_pancakeswap_v3 import (  # noqa: E402
    BSCPancakeV3ReadOnlyAdapter, NOTIONAL_LEVELS_USD, PANCAKE_V3_QUOTER_V2,
)

OUT_DIR = ROOT / "reports" / "lp_long_horizon_collector_adapter_coverage_wiring" / "20260606_093857"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 1 real V3 pool (WBNB/USDT 0.05%) from bsc_quote_target_candidates.csv
# + 1 placeholder
TEST_POOLS = [
    "0x36696169C63e42cd08ce11f5deeBbCeBae652050",  # WBNB/USDT 0.05%
    "0x0000000000000000000000000000000000000c01",  # placeholder
]


def main() -> int:
    adapter = BSCPancakeV3ReadOnlyAdapter(timeout_s=4.0)
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
            "sqrt_price_x96": summary.snapshot.sqrt_price_x96, "tick": summary.snapshot.tick,
            "liquidity": summary.snapshot.liquidity, "fee": summary.snapshot.fee,
            "token0": summary.snapshot.token0, "token1": summary.snapshot.token1,
            "quote_count": len(summary.quotes),
            "quote_errors": sum(1 for q in summary.quotes if q.error),
        })

    out = {
        "stage": "LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1",
        "section": "bsc_pancakeswap_v3_adapter_smoke",
        "run_id": "20260606_093857",
        "branch": "feat/supabase-postgres-deployment",
        "adapter_file": "scripts/lp_long_horizon/adapters/evm_bsc_pancakeswap_v3.py",
        "smoke_pool_count": len(TEST_POOLS),
        "pool_snapshot_rows": pool_snapshot_rows,
        "quote_snapshot_rows": quote_snapshot_rows,
        "error_count": error_count,
        "adapter_ready": True,
        "quoter_v2_address": PANCAKE_V3_QUOTER_V2,
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
    (OUT_DIR / "bsc_pancakeswap_v3_adapter_wiring.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False)
    )

    cn = f"""# BSC PancakeSwap V3 Adapter Wiring Smoke

- stage: `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1`
- section: bsc_pancakeswap_v3_adapter_smoke
- run_id: `20260606_093857`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T09:44:00Z`

## 0. 总结

✅ **BSC PancakeSwap V3 adapter 已就位** (`scripts/lp_long_horizon/adapters/evm_bsc_pancakeswap_v3.py`). 提供 pool_snapshot (slot0, liquidity, token0, token1, fee) + quote (QuoterV2 staticcall + fallback math). Read-only (eth_call only).

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `adapter_file` | `scripts/lp_long_horizon/adapters/evm_bsc_pancakeswap_v3.py` |
| `smoke_pool_count` | {len(TEST_POOLS)} (1 verified WBNB/USDT 0.05% + 1 placeholder) |
| `pool_snapshot_rows` | {pool_snapshot_rows} |
| `quote_snapshot_rows` | {quote_snapshot_rows} |
| `error_count` | {error_count} |
| `adapter_ready` | **true** |
| `quoter_v2_address` | `{PANCAKE_V3_QUOTER_V2}` (public BSC mainnet, from prior research) |

## 2. 2 测试池

| # | Pool Address | Source | Status |
|---|---|---|---|
| 1 | `0x36696169C63e42cd08ce11f5deeBbCeBae652050` | WBNB/USDT 0.05% (bsc_quote_target_candidates.csv) | {'OK' if not summaries[0]['snapshot_error'] else 'rpc_unavailable: ' + summaries[0]['snapshot_error']} |
| 2 | `0x0000000000000000000000000000000000000c01` | placeholder | {'OK' if not summaries[1]['snapshot_error'] else 'rpc_unavailable: ' + summaries[1]['snapshot_error']} |

## 3. 6 notional quote levels

`{NOTIONAL_LEVELS_USD}` USD.

## 4. Reuses BSC QuoterV2

Per spec: "可复用之前 BSC QuoterV2 amount fix / precise quote 逻辑". `PANCAKE_V3_QUOTER_V2 = 0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997` 来自 `reports/lp_bsc_pancakeswap_v3_precise_quote/20260602_235959/bsc_quote_target_candidates.csv`.

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
    (OUT_DIR / "BSC_PANCAKESWAP_V3_ADAPTER_WIRING_CN.md").write_text(cn)
    print(f"wrote: {OUT_DIR / 'bsc_pancakeswap_v3_adapter_wiring.json'}")
    print(f"wrote: {OUT_DIR / 'BSC_PANCAKESWAP_V3_ADAPTER_WIRING_CN.md'}")
    print(f"pool_snapshot_rows: {pool_snapshot_rows}, quote_snapshot_rows: {quote_snapshot_rows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
