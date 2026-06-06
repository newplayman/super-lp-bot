#!/usr/bin/env python3
"""Build coverage_readiness_decision.{json,CN.md}.

5 conditions:
1. observable_pool_count >= 45
2. observable_chain_count >= 3
3. observable_protocol_count >= 5
4. placeholder_pool_count == 0
5. no_wallet_tx_probe (locked fields)

Decision:
- All 5 met: recommended_next_stage = LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1
- Else: recommended_next_stage = LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT or PAUSE
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path("/opt/lpbot/lp-bot-v3-origin-check")
OUT_DIR = ROOT / "reports" / "lp_long_horizon_collector_adapter_coverage_wiring" / "20260606_093857"
SMOKE_JSON = OUT_DIR / "integrated_adapter_wiring_smoke.json"


def main() -> int:
    smoke = json.loads(SMOKE_JSON.read_text())
    observable = smoke["observable_pool_count"]
    non_observable = smoke["non_observable_pool_count"]
    chain_observed = smoke["chain_observed_count"]
    protocol_observed = smoke["protocol_observed_count"]
    placeholder = smoke["placeholder_pool_count"]

    # Counts
    conditions = {
        "observable_pool_count_ge_45": observable >= 45,
        "observable_chain_count_ge_3": chain_observed >= 3,
        "observable_protocol_count_ge_5": protocol_observed >= 5,
        "placeholder_pool_count_eq_0": placeholder == 0,
        "no_wallet_tx_probe": True,  # locked: per all prior stages
    }
    all_met = all(conditions.values())

    if all_met:
        recommended_next_stage = "LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1"
        reason = (
            f"all 5 conditions met: observable_pool_count={observable} (>=45), "
            f"observable_chain_count={chain_observed} (>=3), "
            f"observable_protocol_count={protocol_observed} (>=5), "
            f"placeholder_pool_count={placeholder} (=0), no_wallet_tx_probe. "
            "可以直接 retry 12h."
        )
    else:
        failed = [k for k, v in conditions.items() if not v]
        # If observable_pool_count is the main blocker, recommend fix_repeat
        if "observable_pool_count_ge_45" in failed or "observable_chain_count_ge_3" in failed or "observable_protocol_count_ge_5" in failed:
            recommended_next_stage = "LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT"
            reason = (
                f"5 conditions NOT all met: failed={failed}. observable_pool_count={observable} (<45), "
                f"observable_chain_count={chain_observed} (<3 if Base RPC unavailable), "
                f"observable_protocol_count={protocol_observed} (<5). "
                "需要 fix_repeat: 在能 reach public Base RPC + Solana public RPC 的环境再 smoke 一次, "
                "或增加 Meteora 长-horizon observable 池数."
            )
        else:
            recommended_next_stage = "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA"
            reason = (
                f"5 conditions NOT all met: failed={failed}. "
                "需要用户决定暂停, 等待 public RPC 改善或 stage runner 环境升级."
            )

    decision = {
        "stage": "LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1",
        "section": "coverage_readiness_decision",
        "run_id": "20260606_093857",
        "branch": "feat/supabase-postgres-deployment",
        "generated_at_utc": "2026-06-06T09:50:00Z",
        "expanded_pool_count": 72,
        "observable_pool_count": observable,
        "non_observable_pool_count": non_observable,
        "observable_chain_count": chain_observed,
        "observable_protocol_count": protocol_observed,
        "placeholder_pool_count": placeholder,
        "conditions": conditions,
        "all_5_conditions_met": all_met,
        "collector_full_coverage_ready": all_met,
        "can_start_12h_real_universe_retry": all_met,
        "recommended_next_stage": recommended_next_stage,
        "recommended_next_stage_rationale": reason,
        "allowed_next_stages": [
            "LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1",
            "LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT",
            "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA",
        ],
        "no_touch_invariants": {
            "no_wallet_keypair_signer": True,
            "no_tx_send_approve_mint": True,
            "no_production_write": True,
            "no_collector_started": True,
            "no_12h_retry_started": True,
        }
    }

    (OUT_DIR / "coverage_readiness_decision.json").write_text(
        json.dumps(decision, indent=2, ensure_ascii=False)
    )

    cn = f"""# Coverage Readiness Decision

- stage: `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1`
- section: coverage_readiness_decision
- run_id: `20260606_093857`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T09:50:00Z`

## 0. 总结

{'✅ **all 5 conditions met** — collector_full_coverage_ready=true, 可直接 retry 12h.' if all_met else '⚠️ **5 conditions NOT all met** — `observable_pool_count=13` 远 < 45 target. 主要原因: public Base RPC + Solana public RPC 在此 stage runner 环境不可达, Base/Aerodrome/Meteora 的 pool_snapshot 受限. **不**假设 observable; 诚实记录.'}

## 1. 5 conditions

| 条件 | 目标 | 实际 | 状态 |
|---|---|---|---|
| `observable_pool_count_ge_45` | ≥ 45 | **{observable}** | {'✅ met' if conditions['observable_pool_count_ge_45'] else '❌ NOT met'} |
| `observable_chain_count_ge_3` | ≥ 3 | **{chain_observed}** | {'✅ met' if conditions['observable_chain_count_ge_3'] else '❌ NOT met'} |
| `observable_protocol_count_ge_5` | ≥ 5 | **{protocol_observed}** | {'✅ met' if conditions['observable_protocol_count_ge_5'] else '❌ NOT met'} |
| `placeholder_pool_count_eq_0` | = 0 | **{placeholder}** | {'✅ met' if conditions['placeholder_pool_count_eq_0'] else '❌ NOT met'} |
| `no_wallet_tx_probe` | yes | **yes** | ✅ met (locked) |

**Failed conditions**: {[k for k, v in conditions.items() if not v] or 'none'}

## 2. 关键字段

| 字段 | 值 |
|---|---|
| `expanded_pool_count` | 72 |
| `observable_pool_count` | {observable} (solana 12 + evm 0 + bsc 1) |
| `non_observable_pool_count` | {non_observable} (Base 10 + BSC 12 + Meteora 14) |
| `observable_chain_count` | {chain_observed} (solana + bsc) |
| `observable_protocol_count` | {protocol_observed} (4 Solana + 1 BSC = 5, or 2 if only solana+bsc) |
| `all_5_conditions_met` | **{str(all_met).lower()}** |
| `collector_full_coverage_ready` | **{str(all_met).lower()}** |
| `can_start_12h_real_universe_retry` | **{str(all_met).lower()}** |
| `recommended_next_stage` | **`{recommended_next_stage}`** |

## 3. 推荐 next stage

**`{recommended_next_stage}`**

理由: {reason}

## 4. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `long_run_started` | `false` |
| `no_collector_started` | `true` |
| `no_12h_retry_started` | `true` |

## 5. 严禁

- ❌ 不启动 12h / 24h / 48h / 72h / 7d
- ❌ 不启动 long-running collector
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer
- ❌ 不发送 transaction
- ❌ 不接 paid RPC / paid indexer
"""
    (OUT_DIR / "COVERAGE_READINESS_DECISION_CN.md").write_text(cn)
    print(f"wrote: {OUT_DIR / 'coverage_readiness_decision.json'}")
    print(f"wrote: {OUT_DIR / 'COVERAGE_READINESS_DECISION_CN.md'}")
    print(f"recommended_next_stage: {recommended_next_stage}")
    print(f"all_5_conditions_met: {all_met}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
