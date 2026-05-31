# INPUT_ARTIFACT_AUDIT_CN

- audit_time_utc: 2026-05-31T03:47:58.066410+00:00
- run_id: 20260531_034610

## 输入文件
- reports/fixed_horizon_periodic_loop/20260531_032608/FINAL_VERDICT.json
- reports/fixed_horizon_periodic_loop/20260531_032608/fixed_horizon_24h_trend.json
- reports/fixed_horizon_periodic_loop/20260531_032608/fixed_horizon_review_gate_24h.json
- reports/fixed_horizon_periodic_loop/20260531_032608/fixed_horizon_24h_root_cause.json
- reports/fixed_horizon_policy/20260530_145208/FINAL_VERDICT.json
- reports/shadow_health/20260530_142032/FINAL_VERDICT.json

## 抽取结果
- periodic_stage=FIXED_HORIZON_24H_OOS_ACCUMULATION_MONITOR_V1, status=WARN, fixed_horizon_gate=INSUFFICIENT, canonical_proof=v2_strict_fixed_horizon
- periodic_position_count: 6h=68, 12h=68, 24h=68
- periodic_completed_count: 6h=42, 12h=40, 24h=8
- periodic_root_cause: HORIZONS_NOT_MATURE, FUTURE_MARK_COVERAGE_LOW, SHADOW_POSITION_REUSE_DOMINANT, TAIL_NEGATIVE_SEVERE
- trend_stage=FIXED_HORIZON_PERIODIC_OOS_MONITOR_24H_MONITOR_V1, trend_status=INSUFFICIENT, sample sufficiency 6h=EARLY, 12h=EARLY, 24h=INSUFFICIENT
- root_cause_stage=None, db_writes_freshness=assumed_fresh_from prior shadow checks, shadow_daemon_status=healthy
- policy_stage=FIXED_HORIZON_PROOF_POLICY_FREEZE_AND_OOS_ACCUMULATION_PLAN_V1, status=PASS, recommended_next_stage=FIXED_HORIZON_CONTINUE_OOS_ACCUMULATION
- health_stage=SHADOW_INTENT_POSITION_AND_MARK_COVERAGE_AUDIT_V1, status=PASS, data_source=vps_postgres, materializer_semantics_status=OVER_STRICT_RESEARCH_FALLBACK_POSSIBLE, recommended_next_stage=MATERIALIZER_SEMANTICS_FIX

## 约束校验
- edge_proven: periodic=no, policy=no, health=no
- tiny_canary_allowed: periodic=no, policy=no, health=no

## 任务先决条件结论
- 输入链路已齐，当前卡点为可持续样本不足与 mark 覆盖/尾部风险，符合继续做 stalled 阶段复盘前提。
