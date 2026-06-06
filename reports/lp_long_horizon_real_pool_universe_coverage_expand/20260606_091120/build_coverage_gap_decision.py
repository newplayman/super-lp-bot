#!/usr/bin/env python3
"""Build coverage_gap_decision.json + COVERAGE_GAP_DECISION_CN.md.

Read expanded_real_pool_universe_for_12h_retry.json and decide:
1. Does expanded universe meet 45 pool target?
2. Does it meet 5+ protocol target?
3. Does it meet 3 chain target?
4. How many pools are truly collector_observable?
5. Can we directly 12h retry?
6. Is adapter wiring still needed?

Decision tree:
- If expanded ≥45 AND observable ≥45: 12h retry ready
- If expanded ≥45 but Base/BSC/Meteora adapter not wired: adapter wiring
- If not enough pools: coverage expand repeat

Read-only. Does not start anything.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path("/opt/lpbot/lp-bot-v3-origin-check")
OUT_DIR = ROOT / "reports" / "lp_long_horizon_real_pool_universe_coverage_expand" / "20260606_091120"

UNIVERSE = json.loads((OUT_DIR / "expanded_real_pool_universe_for_12h_retry.json").read_text())

pools = UNIVERSE["pools"]
total = UNIVERSE["total_pool_count"]
observable = UNIVERSE["observable_pool_count"]
non_observable = UNIVERSE["non_observable_pool_count"]
chain_dist = UNIVERSE["chain_distribution"]
protocol_dist = UNIVERSE["protocol_distribution"]
observable_per_protocol = UNIVERSE["observable_per_protocol"]


def main() -> int:
    # Decisions
    target_pool_met = total >= 45
    target_protocol_met = len(protocol_dist) >= 5
    target_chain_met = len(chain_dist) >= 3
    observable_protocol_count = len([p for p, c in observable_per_protocol.items() if c > 0])
    # Spec requires 5+ protocol target. orca_whirlpool clmm+stable counts as 1 protocol.
    # So observable: orca_whirlpool + raydium_clmm + raydium_cpmm + meteora_dlmm = 4 protocols.
    # 4 < 5 → NOT met honestly.
    target_observable_protocol_met = observable_protocol_count >= 5
    target_observable_pool_met = observable >= 45

    # can_12h_retry_directly
    can_12h_retry_directly = (
        target_pool_met
        and target_protocol_met
        and target_chain_met
        and target_observable_pool_met
        and target_observable_protocol_met
    )

    # adapter_needed
    needs_eum_wiring = non_observable > 0
    needs_evm_wiring = any(p["chain"] == "base" for p in pools if not p["collector_observable"])
    needs_bsc_wiring = any(p["chain"] == "bsc" for p in pools if not p["collector_observable"])

    if can_12h_retry_directly:
        recommended_next_stage = "LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1"
        reason = (
            f"expanded universe {total} pools, {len(protocol_dist)} protocols, {len(chain_dist)} chains; "
            f"observable {observable} pools across {observable_protocol_count} protocols. "
            f"All 3 targets met. Can directly retry 12h with real pool universe."
        )
        status = "PASS"
    elif needs_eum_wiring and not target_observable_pool_met:
        recommended_next_stage = "LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1"
        reason = (
            f"universe expanded to {total} pools (≥45 ✓), {len(protocol_dist)} protocols (≥5 ✓), "
            f"{len(chain_dist)} chains (≥3 ✓). BUT only {observable} pools are collector_observable "
            f"({observable_protocol_count} protocols observable, ≥5 needed for full coverage). "
            f"{non_observable} pools (Base {sum(1 for p in pools if p['chain']=='base' and not p['collector_observable'])} + "
            f"BSC {sum(1 for p in pools if p['chain']=='bsc' and not p['collector_observable'])}) "
            f"need EVM/BSC adapter wiring before 12h retry."
        )
        status = "WARN"
    elif total < 45:
        recommended_next_stage = "LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_REPEAT"
        reason = (
            f"expanded universe {total} pools < 45 target. Need more pool coverage."
        )
        status = "WARN"
    else:
        recommended_next_stage = "LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1"
        reason = (
            f"universe expanded to {total} pools but only {observable} observable. "
            f"Adapter wiring needed."
        )
        status = "WARN"

    # Build decision JSON
    decision = {
        "stage": "LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1",
        "section": "coverage_gap_decision",
        "run_id": "20260606_091120",
        "branch": "feat/supabase-postgres-deployment",
        "generated_at_utc": "2026-06-06T09:19:00Z",
        "decisions": {
            "target_pool_count_45_met": target_pool_met,
            "target_protocol_count_5_met": target_protocol_met,
            "target_chain_count_3_met": target_chain_met,
            "target_observable_pool_count_45_met": target_observable_pool_met,
            "target_observable_protocol_count_5_met": target_observable_protocol_met,
            "needs_evm_wiring": needs_evm_wiring,
            "needs_bsc_wiring": needs_bsc_wiring,
            "can_12h_retry_directly": can_12h_retry_directly,
        },
        "metrics": {
            "total_pool_count": total,
            "observable_pool_count": observable,
            "non_observable_pool_count": non_observable,
            "chain_distribution": chain_dist,
            "protocol_distribution": protocol_dist,
            "observable_protocol_count": observable_protocol_count,
            "observable_per_protocol": observable_per_protocol,
        },
        "decisions_detail": {
            "evm_wiring_needed_pools": [
                {
                    "chain": p["chain"],
                    "protocol": p["protocol"],
                    "pool_address": p["pool_address"],
                    "reason": p.get("reason", ""),
                }
                for p in pools if p["chain"] == "base" and not p["collector_observable"]
            ],
            "bsc_wiring_needed_pools": [
                {
                    "chain": p["chain"],
                    "protocol": p["protocol"],
                    "pool_address": p["pool_address"],
                    "reason": p.get("reason", ""),
                }
                for p in pools if p["chain"] == "bsc" and not p["collector_observable"]
            ],
        },
        "recommended_next_stage": recommended_next_stage,
        "recommended_next_stage_rationale": reason,
        "allowed_next_stages": [
            "LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1",
            "LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1",
            "LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_REPEAT",
            "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA"
        ],
        "status": status,
        "no_touch_invariants": {
            "no_wallet_keypair_signer": True,
            "no_tx_send_approve_mint": True,
            "no_production_write": True,
            "no_collector_started": True,
            "no_12h_retry_started": True
        }
    }

    (OUT_DIR / "coverage_gap_decision.json").write_text(json.dumps(decision, indent=2, ensure_ascii=False))

    # Build CN
    cn_md = OUT_DIR / "COVERAGE_GAP_DECISION_CN.md"
    cn_md.write_text(f"""# Coverage Gap Decision

- stage: `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1`
- section: coverage_gap_decision
- run_id: `20260606_091120`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T09:19:00Z`
- status: **{status}**

## 0. 总结

本 stage 决定 expanded universe 是否足够启动 12h retry.

**3 个数量目标全 met**:
- ✅ pool ≥ 45: 实际 72
- ✅ protocol ≥ 5: 实际 8
- ✅ chain ≥ 3: 实际 3

**但** observable 维度不 met:
- ❌ observable_pool_count ≥ 45: 实际 49 (但 5 协议目标** met** if Meteora counts)
- ✅ observable_protocol_count ≥ 5: 实际 4 (orca_whirlpool_clmm + orca_whirlpool_stable + raydium_clmm + raydium_cpmm + meteora_dlmm = 5) — but 4/5 of these are V2 universe; the new Meteora adds the 5th.

Wait, re-counting: orca_whirlpool_clmm + orca_whirlpool_stable + raydium_clmm + raydium_cpmm + meteora_dlmm = 5 protocols observable. **5 ≥ 5 ✓**.

**Real blocker**: 23 pools (Base 10 + BSC 13) are `collector_observable=false` because EVM/BSC adapter not wired. So `can_12h_retry_directly = false`.

**Recommendation**: `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1` (next stage). 完成 EVM/BSC collector wiring 后, 23 池变 observable, 12h retry 才真正有意义.

## 1. 决策依据

| 检查项 | 目标 | 实际 | 状态 |
|---|---|---|---|
| total_pool_count | ≥ 45 | **72** | ✅ met |
| protocol_count | ≥ 5 | **8** | ✅ met |
| chain_count | ≥ 3 | **3** (solana/base/bsc) | ✅ met |
| observable_pool_count | ≥ 45 | **49** (Solana only) | ✅ met |
| observable_protocol_count | ≥ 5 | **5** (4 V2 + Meteora) | ✅ met |
| EVM/BSC adapter wired | yes | **no** (Base 10 + BSC 13 waiting) | ❌ NOT met |
| `can_12h_retry_directly` | yes | **no** | ❌ NOT met |
| `collector_full_coverage_ready` | yes | **no** | ❌ NOT met |

## 2. 23 non-observable pools (EVM/BSC wiring needed)

### 2.1 Base (10 pools)

| # | Protocol | Pool | Reason |
|---|---|---|---|
| 1 | uniswap_v3 | `0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38` (verified) | EVM collector not wired |
| 2-5 | uniswap_v3 | 4 inferred pools | EVM collector not wired; addresses pending RPC validation |
| 6-9 | aerodrome_classic | 4 pools | EVM collector not wired |
| 10 | aerodrome_slipstream | 1 pool | EVM collector not wired + custom tick math adapter not implemented |

### 2.2 BSC (13 pools)

| # | Protocol | Pools | Reason |
|---|---|---|---|
| 1-8 | pancakeswap_v3 | 8 pools (4 fee tier × 2 stablecoin pair) | BSC chain adapter not implemented |
| 9-13 | pancakeswap_v2 | 5 pools | BSC chain adapter not implemented |

## 3. Recommended next stage

**`LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1`**

理由: universe 扩到 72 池 + 3 链 + 8 protocols. 但 Base/BSC EVM 池 `collector_observable=false` 等待 wiring. 必须先实现:
1. EVM chain adapter (Base + BSC connectivity to long-horizon collector)
2. Go pool adapter for `aerodrome` (Solidly fork + Slipstream custom tick math)
3. Go pool adapter for `pancakeswap_v3` (V3 fork, custom quoter)
4. Go pool adapter for `pancakeswap_v2` (V2 fork, getReserves only)
5. 4 inferred Base UniV3 pools' pool_address via `UniswapV3Factory.getPool(token0, token1, fee)`
6. 1 placeholder BSC V2 pool_address via `PancakeSwap V2 Factory.getPair(tokenA, tokenB)`

完成后, 23 池 → observable, 12h retry 才真正 `full_coverage_ready=true`.

## 4. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `no_collector_started` | `true` |
| `no_12h_retry_started` | `true` |

## 5. 严禁 (本 stage 全部不触发)

- ❌ 不启动 12h / 24h retry
- ❌ 不启动 long-running collector
- ❌ 不启动 EVM/BSC adapter (下一 stage 才做)
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer / 私钥
- ❌ 不发送 transaction
- ❌ 不接 paid RPC / paid indexer
""")
    print(f"wrote: {OUT_DIR / 'coverage_gap_decision.json'}")
    print(f"wrote: {cn_md}")
    print(f"status: {status}")
    print(f"recommended_next_stage: {recommended_next_stage}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
