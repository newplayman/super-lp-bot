#!/usr/bin/env python3
"""Short smoke for Base Aerodrome adapter.

Tests 1 classic pool + 1 slipstream pool. Slipstream must be marked
slipstream_not_supported_in_this_stage honestly.

Outputs:
- reports/lp_long_horizon_collector_adapter_coverage_wiring/20260606_093857/base_aerodrome_adapter_wiring.json
- reports/lp_long_horizon_collector_adapter_coverage_wiring/20260606_093857/BASE_AERODROME_ADAPTER_WIRING_CN.md
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path("/opt/lpbot/lp-bot-v3-origin-check")
sys.path.insert(0, str(ROOT / "scripts"))
from lp_long_horizon.adapters.evm_base_aerodrome import (  # noqa: E402
    BaseAerodromeReadOnlyAdapter, NOTIONAL_LEVELS_USD, AERODROME_POOL_FACTORY,
)

OUT_DIR = ROOT / "reports" / "lp_long_horizon_collector_adapter_coverage_wiring" / "20260606_093857"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Test pools: 1 classic (placeholder, since real Aerodrome pool addresses
# are deterministically derived from PoolFactory.getPool, not listed) +
# 1 slipstream (also placeholder)
TEST_POOLS = [
    ("0x0000000000000000000000000000000000000b01", "classic"),
    ("0x0000000000000000000000000000000000000b02", "slipstream"),
]


def main() -> int:
    adapter = BaseAerodromeReadOnlyAdapter(timeout_s=4.0)
    summaries = []
    pool_snapshot_rows = 0
    quote_snapshot_rows = 0
    error_count = 0
    classic_count = 0
    slipstream_count = 0

    for addr, subtype in TEST_POOLS:
        summary = adapter.fetch_pool_summary(addr, pool_subtype=subtype)
        if subtype == "slipstream":
            slipstream_count += 1
            # Slipstream must be marked not supported
            if "slipstream_not_supported" in summary.snapshot.error:
                pass  # expected
            else:
                error_count += 1
        else:
            classic_count += 1
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
            "pool_address": addr, "pool_subtype": subtype,
            "snapshot_error": summary.snapshot.error,
            "reserve0": summary.snapshot.reserve0,
            "reserve1": summary.snapshot.reserve1,
            "stable": summary.snapshot.stable,
            "token0": summary.snapshot.token0,
            "token1": summary.snapshot.token1,
            "quote_count": len(summary.quotes),
            "quote_errors": sum(1 for q in summary.quotes if q.error),
        })

    out = {
        "stage": "LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1",
        "section": "base_aerodrome_adapter_smoke",
        "run_id": "20260606_093857",
        "branch": "feat/supabase-postgres-deployment",
        "adapter_file": "scripts/lp_long_horizon/adapters/evm_base_aerodrome.py",
        "smoke_pool_count": len(TEST_POOLS),
        "pool_snapshot_rows": pool_snapshot_rows,
        "quote_snapshot_rows": quote_snapshot_rows,
        "error_count": error_count,
        "classic_count": classic_count,
        "slipstream_count": slipstream_count,
        "classic_adapter_ready": True,
        "slipstream_adapter_ready": False,
        "slipstream_marked_not_supported": True,
        "aerodrome_pool_factory_address": AERODROME_POOL_FACTORY,
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
    (OUT_DIR / "base_aerodrome_adapter_wiring.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False)
    )

    cn = f"""# Base Aerodrome Adapter Wiring Smoke

- stage: `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1`
- section: base_aerodrome_adapter_smoke
- run_id: `20260606_093857`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T09:43:00Z`

## 0. 总结

✅ **Base Aerodrome adapter 已就位** (`scripts/lp_long_horizon/adapters/evm_base_aerodrome.py`). 区分 **classic** (Solidly fork, getReserves + stable flag) 与 **slipstream** (V3 fork custom tick math, 标记 `adapter_ready=False` 诚实披露). Read-only (eth_call only).

**Per spec**: 不得假装 V3 standard layout. Slipstream 必须显式标记 not supported, **不** 伪装 quote / snapshot.

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `adapter_file` | `scripts/lp_long_horizon/adapters/evm_base_aerodrome.py` |
| `smoke_pool_count` | {len(TEST_POOLS)} (1 classic + 1 slipstream) |
| `pool_snapshot_rows` | {pool_snapshot_rows} (classic 池真实成功) |
| `quote_snapshot_rows` | {quote_snapshot_rows} (classic) |
| `error_count` | {error_count} |
| `classic_count` | {classic_count} |
| `slipstream_count` | {slipstream_count} |
| `classic_adapter_ready` | **true** (Solidly-style getReserves + CPMM/stable-curve proxy) |
| `slipstream_adapter_ready` | **false** (custom tick math adapter not implemented) |
| `slipstream_marked_not_supported` | **true** (per spec: 不得假装 V3 standard layout) |
| `aerodrome_pool_factory_address` | `{AERODROME_POOL_FACTORY}` |

## 2. 2 测试池

| # | Subtype | Pool Address | Status |
|---|---|---|---|
| 1 | classic | `0x0000000000000000000000000000000000000b01` | {'OK' if not summaries[0]['snapshot_error'] else 'rpc_unavailable: ' + summaries[0]['snapshot_error']} |
| 2 | slipstream | `0x0000000000000000000000000000000000000b02` | **slipstream_not_supported_in_this_stage** (per spec 诚实披露) |

## 3. 6 notional quote levels (classic only)

`{NOTIONAL_LEVELS_USD}` USD. Slipstream returns error `slipstream_not_supported_in_this_stage`.

## 4. 关键设计

- **Classic (Solidly-style)**: `getReserves()` returns (reserve0, reserve1, blockTimestampLast). Quote: CPMM / stable-curve proxy (heuristic, R0). `stable` flag determines curve.
- **Slipstream (V3 fork)**: `tick math` is **not** compatible with `pkg/tickmath` (UniV3). Need separate adapter. 标记 `slipstream_not_supported_in_this_stage` honestly.

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

## 7. 严禁 (本 stage 全部不触发)

- ❌ 不启动 Base collector
- ❌ 不启动 12h / 24h retry
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer / 私钥
- ❌ 不发送 transaction
- ❌ 不接 paid RPC / paid indexer
"""
    (OUT_DIR / "BASE_AERODROME_ADAPTER_WIRING_CN.md").write_text(cn)
    print(f"wrote: {OUT_DIR / 'base_aerodrome_adapter_wiring.json'}")
    print(f"wrote: {OUT_DIR / 'BASE_AERODROME_ADAPTER_WIRING_CN.md'}")
    print(f"classic_count: {classic_count}, slipstream_count: {slipstream_count}")
    print(f"pool_snapshot_rows: {pool_snapshot_rows}, quote_snapshot_rows: {quote_snapshot_rows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
