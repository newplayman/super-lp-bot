# Stage B — 输入证据审计 (Input Evidence Audit)

- stage: `LP_LONG_HORIZON_READONLY_DATA_PIPELINE_V1`
- run_id: `20260604_062324`
- branch: `feat/supabase-postgres-deployment`
- HEAD: `82be451 research: audit lp conclusion scope 20260604_060659`

## 0. 目的

在启动"长期只读数据采集管线"之前, 把上一阶段 scope_audit 留下的核心产物逐条
read-back 验证, 锁存"哪些字段是 boundary" / "哪些字段是 build target" / "哪些字段
是硬禁止". 这是只读 audit, 不重跑任何 protocol, 不修改任何 final freeze verdict.

## 1. 必读清单与 read-back 状态

| # | 必读文件 | 路径 | 状态 | 关键字段确认 |
|---|---|---|---|---|
| 1 | FINAL_VERDICT.json (scope_audit) | `reports/lp_research_conclusion_scope_audit/20260604_060659/FINAL_VERDICT.json` | ✅ read | status=WARN, stage=LP_RESEARCH_CONCLUSION_SCOPE_AUDIT_V1, current_probe_allowed=false, global_lp_rejected=false, current_model_rejects_auto_probe=true, conclusion_scope=current_data_current_model_short_window, long_term_lp_value_judged=false, needs_longer_horizon_validation=true, needs_actual_fee_accrual=true, needs_market_regime_split=true, market_downtrend_bias_acknowledged=true, docs_updated=true, can_run_probe_now=false, tiny_canary_allowed=no, edge_proven=no, recommended_next_stage=PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA, safety.*=false, send_hard_disable_still_active=true |
| 2 | long_horizon_reopen_plan.json | `reports/lp_research_conclusion_scope_audit/20260604_060659/long_horizon_reopen_plan.json` | ✅ read | 6 phases R0-R5; R0 = long read-only data baseline; minimum_cells=210; any-phase STOP exit; hard prohibitions listed |
| 3 | model_limitation_audit.json | `reports/lp_research_conclusion_scope_audit/20260604_060659/model_limitation_audit.json` | ✅ read | 6 dimensions, 4 HIGH (data_window, fee_data, il_lvr, pool_selection), 2 MEDIUM (cost_data, capital_scale); what_must_be_verified_next 列了 R0 阶段的 4 项: 7d/14d/30d read-only baseline, paid_indexer_90d/180d/365d, precise_cost_breakdown, batch_transaction_design |
| 4 | market_regime_bias_audit.json | `reports/lp_research_conclusion_scope_audit/20260604_060659/market_regime_bias_audit.json` | ✅ read | 7 regime: uptrend, downtrend, sideways, high_volume_sideways, high_volatility_trend, incentive_period, low_volatility_stable; locked_conclusions 全 locked; regime_split_required_for = R2_market_regime_split |

## 2. 必确认项 check

### 2.1 boundary 字段 (locked, 不动)

- [x] can_run_probe_now = false (locked)
- [x] tiny_canary_allowed = "no" (locked)
- [x] edge_proven = "no" (locked)
- [x] send_hard_disable_still_active = true (locked)
- [x] global_lp_rejected = false (口径修正锁定, 不代表"所有 LP 没价值")
- [x] current_probe_allowed = false
- [x] market_downtrend_bias_acknowledged = true

### 2.2 build target 字段 (本任务目标)

- [x] needs_longer_horizon_validation = true → 本任务设计 7d/14d/30d baseline 管线
- [x] needs_actual_fee_accrual = true → 本任务设计 actual fee accrual schema (Stage G)
- [x] needs_market_regime_split = true → 本任务设计 regime classifier spec (Stage F)
- [x] long_horizon_pipeline_ready = false (本任务完成后应为 true, 标记完成度)

### 2.3 硬禁止项 (本任务全程不破)

- [x] 不读取私钥 / seed / keypair
- [x] 不创建 signer
- [x] 不发送 transaction
- [x] 不 approve / mint / add_liquidity / remove_liquidity / collect_fee
- [x] 不 swap / bridge
- [x] 不启动 live / canary / paper
- [x] 不写 production positions
- [x] 不覆盖 shadow 原始表
- [x] can_run_probe_now 必须保持 false
- [x] tiny_canary_allowed 必须保持 no
- [x] 本任务脚本默认 design mode, 不长期启动 daemon
- [x] 不自动跑 30 天
- [x] 只做 smoke 采样验证
- [x] 后续如需长期运行, 必须单独人工批准

## 3. 本任务输出 (lock from input)

- INPUT_EVIDENCE_AUDIT_CN.md / .json
- LONG_HORIZON_DATA_REQUIREMENTS_CN.md / .json
- READONLY_COLLECTOR_ARCHITECTURE_CN.md / .json
- RESEARCH_ONLY_SCHEMA_CN.md / .json
- MARKET_REGIME_CLASSIFIER_SPEC_CN.md / .json
- ACTUAL_FEE_ACCRUAL_SCHEMA_CN.md / .json
- COLLECTOR_SAFETY_AUDIT_CN.md / .json
- FINAL_VERDICT.json
- ONEPAGE_CN.md
- ARTIFACT_INDEX.md
- scripts/lp_long_horizon_readonly_collector_v1.py (design mode + smoke sample, 不长期跑)
- tests/test_lp_long_horizon_readonly_data_pipeline_v1.py (read-only assertion)

## 4. 不在本任务范围 (read 不写)

- 任何 protocol re-run
- 任何 heuristic 改动
- 任何 cost 优化实施
- 任何 paid RPC 接入
- 任何 私有池 / vault 数据采集
- 任何 bribe marketplace 集成
- 任何 90d+ backtest (R0 阶段后续任务, 需 paid indexer)
- 任何 实际 fee accrual 抓取 (R1 阶段后续任务, 需 user 提供 tokenId)
- 任何 regime split 实际跑 (R2 阶段后续任务)
- 任何 incentive / vault / managed LP 候选 review (R3 阶段后续任务)
- 任何 probe preflight (R4 阶段后续任务)
- 任何 manual probe (R5 阶段后续任务)

## 5. 与 R0 阶段的对应

本任务是 R0 阶段的设计 + smoke 验证:
- ✅ 设计 7d/14d/30d read-only baseline 管线架构
- ✅ 设计 6 类数据 (pool snapshot / quote snapshot / fee velocity / liquidity distribution /
  market regime / actual fee accrual schema) 字段
- ✅ 设计 research-only 存储 (sqlite / csv / jsonl)
- ✅ 设计 regime classifier spec
- ✅ 设计 actual fee accrual schema
- ✅ 实现 smoke collector 脚本 (设计模式 + 极小采样)
- ⏸ 长期运行 (R0 阶段后续): 需 paid indexer, 单独人工批准
- ⏸ R1 / R2 / R3 / R4 / R5: 本任务不覆盖

## 6. 结论

输入证据 read-back 通过. boundary 字段全部 locked, build target 字段清晰,
硬禁止项明确. Stage B 通过. 进入 Stage C (长期数据需求定义).
