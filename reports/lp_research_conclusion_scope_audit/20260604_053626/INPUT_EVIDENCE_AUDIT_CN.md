# Input Evidence Audit — Stage B

- stage: `LP_RESEARCH_CONCLUSION_SCOPE_AUDIT_V1`
- run_id: `20260604_053626`
- branch: `feat/supabase-postgres-deployment`
- head_before: `7940cff`

## 0. 阶段目标 (user feedback 修正)

用户提出重要质疑: 当前 LP 研究结论**不能**被解释成"所有 LP 长期没价值"。当前结论最多只能说明: "在当前短窗口数据、当前模型假设、当前没有真实 LP tokenId / actual fee accrual 的前提下, 不允许自动进入 10/20U probe, 也不建议继续自动换协议扩展"。

本轮:
- 给 final freeze 增加**结论适用范围审计 addendum**, 避免误读
- **不重跑任何协议**, **不继续找池子**, **不启动交易**
- 只修正结论口径、模型边界、重开条件和长期验证计划

## 1. 上游证据链读取清单

| # | path | 角色 | 状态 |
|---|---|---|---|
| 1 | `reports/lp_research_final_freeze/20260604_051254/FINAL_VERDICT.json` | **直接上游** — final freeze verdict | OK |
| 2 | `reports/lp_research_final_freeze/20260604_051254/WHY_STOP_LP_RESEARCH_NOW_CN.md` | 9 reasons | OK |
| 3 | `reports/lp_research_final_freeze/20260604_051254/LP_RESEARCH_REOPEN_CONDITIONS_CN.md` | 7 reopen 条件 | OK |
| 4 | `reports/lp_research_final_freeze/20260604_051254/WHAT_THIS_DOES_NOT_MEAN_CN.md` | 6 misreadings | OK |
| 5 | `docs/LPBOT_RESEARCH_STATUS_CN.md` | project status doc | OK |
| 6 | `docs/LPBOT_RESEARCH_ARTIFACT_INDEX_CN.md` | artifact index doc | OK |
| 7 | `README.md` | top-level readme | OK |
| 8 | `reports/lp_meteora_dlmm_targeted_top_pool_feed/20260604_021913/FINAL_VERDICT.json` | 5/5 reject evidence 1 | OK |
| 9 | `reports/lp_orca_whirlpool_readonly_connector/20260604_025414/FINAL_VERDICT.json` | 5/5 reject evidence 2 | OK |
| 10 | `reports/lp_raydium_clmm_readonly_connector/20260604_034503/FINAL_VERDICT.json` | 5/5 reject evidence 3 | OK |
| 11 | `reports/lp_raydium_cpmm_readonly_connector/20260604_040952/FINAL_VERDICT.json` | 5/5 reject evidence 4 | OK |
| 12 | `reports/lp_solana_stable_pool_research/20260604_044118/FINAL_VERDICT.json` | 5/5 reject evidence 5 | OK |

## 2. 关键事实确认

```text
=== Final Freeze state (5/5 reject cumulative) ===
overall_recommendation = STOP_LP_RESEARCH_NOW
edge_proven             = no
can_run_probe_now       = False (all 6 stages)
tiny_canary_allowed    = no (all 6 stages)
zero_il_lvr_positive_only = True (1898 / 28560 cells, all in zero_il_lvr only)
positive_realistic_any_protocol = False
positive_optimistic_any_protocol = False
positive_conservative_any_protocol = False
reopen_conditions_documented = True
docs_updated              = True
wallet_or_tx_touched      = False
```

```text
=== 5 protocol verdicts (all REJECT, positive_realistic=0) ===
1. Meteora DLMM V8 (20260604_021913):    can_probe=False, tiny=no, realistic=0
2. Orca Whirlpools V1 (20260604_025414): can_probe=False, tiny=no, realistic=0
3. Raydium CLMM V1 (20260604_034503):   can_probe=False, tiny=no, realistic=0
4. Raydium CPMM V1 (20260604_040952):   can_probe=False, tiny=no, realistic=0
5. Solana stable V1 (20260604_044118):  can_probe=False, tiny=no, realistic=0
```

## 3. user 质疑 (核心)

当前 final freeze 结论 `STOP_LP_RESEARCH_NOW` + `what_this_does_not_mean.md` 已经声明 6 误读, 但用户认为:

- 仍有可能被读成"所有 LP 长期没价值"
- 应该增加**明确的结论适用范围 addendum**
- 强调 `global_lp_rejected = false`
- 增加 `current_data_current_model_short_window` 范围声明
- 增加 `long_term_lp_value_judged = false` 范围声明

## 4. 本轮范围 (user feedback 修正)

| 维度 | 状态 |
|---|---|
| 启动新 research runner | ❌ 禁止 |
| 换协议 | ❌ 禁止 |
| probe / canary / live / paper | ❌ 禁止 |
| 读 keypair / 构造 tx | ❌ 禁止 |
| 重跑任何协议 | ❌ 禁止 |
| 找新池子 | ❌ 禁止 |
| **修正结论口径** | ✅ 允许 |
| **模型边界审计** | ✅ 允许 |
| **重开条件修订** | ✅ 允许 |
| **长期验证计划** | ✅ 允许 |
| **regime split 建议** | ✅ 允许 |
| **docs 口径修正** | ✅ 允许 |
| **commit / push** | ✅ 允许 |

## 5. 硬边界继承

```text
can_run_probe_now               = false (locked, all 6 stages)
tiny_canary_allowed             = no    (locked, all 6 stages)
solana_wallet_or_keypair_touched = false (locked)
transaction_sent                = false (locked)
wallet_or_tx_touched            = false (locked)
v2_line_count                   = 992 (unchanged)
send_hard_disable_still_active  = true
```

## 6. 下一阶段

进入 Stage C — 当前结论适用范围 (`CURRENT_CONCLUSION_SCOPE_CN.md`)。
