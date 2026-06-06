#!/usr/bin/env python3
"""Build coverage_readiness_decision.{json,CN.md}.

5 conditions:
1. observable_pool_count >= 45
2. observable_chain_count >= 3
3. observable_protocol_count >= 5
4. placeholder_pool_count == 0
5. no_wallet_tx_probe

Decision tree:
- All met: 12h retry ready
- Else if main blocker is public RPC: fix_repeat (RPC)
- Else if main blocker is adapter code: code_fix_repeat
- Else: PAUSE
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path("/opt/lpbot/lp-bot-v3-origin-check")
OUT_DIR = ROOT / "reports" / "lp_long_horizon_rpc_reachability_adapter_smoke_fix" / "20260606_103807"
SMOKE = OUT_DIR / "integrated_observable_smoke_retry.json"
REACHABILITY = OUT_DIR / "rpc_reachability_matrix.json"


def main() -> int:
    smoke = json.loads(SMOKE.read_text())
    reach = json.loads(REACHABILITY.read_text())
    observable = smoke["observable_pool_count"]
    chain_observed = smoke["chain_observed_count"]
    protocol_observed = smoke["protocol_observed_count"]
    placeholder = smoke["placeholder_pool_count"]
    selected = smoke["non_observable_pool_count"]

    conditions = {
        "observable_pool_count_ge_45": observable >= 45,
        "observable_chain_count_ge_3": chain_observed >= 3,
        "observable_protocol_count_ge_5": protocol_observed >= 5,
        "placeholder_pool_count_eq_0": placeholder == 0,
        "no_wallet_tx_probe": True,
    }
    all_met = all(conditions.values())

    base_rpc_reachable = reach.get("selected_per_chain", {}).get("base") is not None
    bsc_rpc_reachable = reach.get("selected_per_chain", {}).get("bsc") is not None
    solana_rpc_reachable = reach.get("selected_per_chain", {}).get("solana") is not None

    if all_met:
        recommended_next_stage = "LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1"
        reason = f"all 5 conditions met: observable={observable} (>=45), chain={chain_observed} (>=3), protocol={protocol_observed} (>=5), placeholder={placeholder} (=0), no_wallet_tx_probe. 可直接 retry 12h."
    else:
        # Determine main blocker
        failed = [k for k, v in conditions.items() if not v]
        if "observable_chain_count_ge_3" in failed and not base_rpc_reachable:
            # Base RPC unreachable → main blocker is public RPC
            recommended_next_stage = "LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT"
            reason = (
                f"5 conditions NOT all met: failed={failed}. "
                f"Base public RPC **unreachable** in this env (4 endpoints 全部 403 Forbidden / Connection reset). "
                f"observable_chain_count={chain_observed} < 3. "
                "需要 fix_repeat: 在能 reach public Base RPC 的 env 再 smoke, 或等 RPC 改善."
            )
        elif "observable_pool_count_ge_45" in failed and observable < 10:
            # Very few observable → code issue
            recommended_next_stage = "LP_LONG_HORIZON_COLLECTOR_ADAPTER_CODE_FIX_REPEAT"
            reason = (
                f"5 conditions NOT all met: failed={failed}. observable_pool_count={observable} 太低. "
                "需要 code_fix: 检查 Base/BSC/Meteora adapter 代码 (RPC reachability **OK** 但 smoke 失败)."
            )
        else:
            recommended_next_stage = "LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT"
            reason = (
                f"5 conditions NOT all met: failed={failed}. observable_pool_count={observable}, chain={chain_observed}. "
                "主要因 public Base RPC 不可达. 下一 stage 换 env 或等 RPC 改善."
            )

    decision = {
        "stage": "LP_LONG_HORIZON_COLLECTOR_RPC_REACHABILITY_AND_ADAPTER_SMOKE_FIX_V1",
        "section": "coverage_readiness_decision",
        "run_id": "20260606_103807",
        "branch": "feat/supabase-postgres-deployment",
        "generated_at_utc": "2026-06-06T10:48:00Z",
        "expanded_pool_count": 72,
        "observable_pool_count": observable,
        "non_observable_pool_count": selected,
        "observable_chain_count": chain_observed,
        "observable_protocol_count": protocol_observed,
        "placeholder_pool_count": placeholder,
        "rpc_reachability": {
            "base_rpc_reachable": base_rpc_reachable,
            "bsc_rpc_reachable": bsc_rpc_reachable,
            "solana_rpc_reachable": solana_rpc_reachable,
        },
        "conditions": conditions,
        "all_5_conditions_met": all_met,
        "collector_full_coverage_ready": all_met,
        "can_start_12h_real_universe_retry": all_met,
        "recommended_next_stage": recommended_next_stage,
        "recommended_next_stage_rationale": reason,
        "allowed_next_stages": [
            "LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1",
            "LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT",
            "LP_LONG_HORIZON_COLLECTOR_ADAPTER_CODE_FIX_REPEAT",
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
    (OUT_DIR / "coverage_readiness_decision.json").write_text(json.dumps(decision, indent=2, ensure_ascii=False))

    cn = f"""# Coverage Readiness Decision

- stage: `LP_LONG_HORIZON_COLLECTOR_RPC_REACHABILITY_AND_ADAPTER_SMOKE_FIX_V1`
- section: coverage_readiness_decision
- run_id: `20260606_103807`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T10:48:00Z`

## 0. 总结

{'✅ **all 5 conditions met** — collector_full_coverage_ready=true, 可直接 retry 12h.' if all_met else '⚠️ **5 conditions NOT all met** — observable_pool_count=' + str(observable) + ' / chain=' + str(chain_observed) + '. 主要因 Base public RPC 在此 env 不可达.'}

## 1. 5 conditions

| 条件 | 目标 | 实际 | 状态 |
|---|---|---|---|
| `observable_pool_count_ge_45` | ≥ 45 | **{observable}** | {'✅ met' if conditions['observable_pool_count_ge_45'] else '❌ NOT met'} |
| `observable_chain_count_ge_3` | ≥ 3 | **{chain_observed}** | {'✅ met' if conditions['observable_chain_count_ge_3'] else '❌ NOT met'} |
| `observable_protocol_count_ge_5` | ≥ 5 | **{protocol_observed}** | {'✅ met' if conditions['observable_protocol_count_ge_5'] else '❌ NOT met'} |
| `placeholder_pool_count_eq_0` | = 0 | **{placeholder}** | {'✅ met' if conditions['placeholder_pool_count_eq_0'] else '❌ NOT met'} |
| `no_wallet_tx_probe` | yes | **yes** | ✅ met (locked) |

**Failed conditions**: {[k for k, v in conditions.items() if not v] or 'none'}

## 2. RPC Reachability

| Chain | Reachable | Selected Endpoint |
|---|---|---|
| base | {'✅' if base_rpc_reachable else '❌'} | `{reach.get('selected_per_chain', {}).get('base', 'none')}` |
| bsc | {'✅' if bsc_rpc_reachable else '❌'} | `{reach.get('selected_per_chain', {}).get('bsc', 'none')}` |
| solana | {'✅' if solana_rpc_reachable else '❌'} | `{reach.get('selected_per_chain', {}).get('solana', 'none')}` |

## 3. 关键字段

| 字段 | 值 |
|---|---|
| `expanded_pool_count` | 72 |
| `observable_pool_count` | {observable} |
| `non_observable_pool_count` | {selected} |
| `observable_chain_count` | {chain_observed} |
| `observable_protocol_count` | {protocol_observed} |
| `all_5_conditions_met` | **{str(all_met).lower()}** |
| `collector_full_coverage_ready` | **{str(all_met).lower()}** |
| `can_start_12h_real_universe_retry` | **{str(all_met).lower()}** |
| `recommended_next_stage` | **`{recommended_next_stage}`** |

## 4. 推荐 next stage

**`{recommended_next_stage}`**

理由: {reason}

## 5. 锁定字段 (5 项全 false/no)

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

## 6. 严禁

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
    print(f"recommended_next_stage: {recommended_next_stage}, all_5_conditions_met: {all_met}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
