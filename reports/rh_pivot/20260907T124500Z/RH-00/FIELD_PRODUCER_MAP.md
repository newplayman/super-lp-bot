# FIELD_PRODUCER_MAP — 终闸字段全链路（RH-00，2026-09-07）

来源：Qwen 只读调研 `qwen/Q3.md`（effort low，只读），主脑抽核项标 `[主脑核]`。仓库 HEAD `279b047`（代码与 `0e2b6e6` 相同）。

## 终闸本体 `[主脑核]`

`scripts/lp_scanner_daemon_v1_readonly.py:1242 _enforce_fifth_gate`：

```
permanent_reason    = rec/source["permanent_fail_closed_reason"]          :1250-1251
netcover_passed     = bool(rec["netcover_pass"]) and not permanent_reason  :1253
position_cap_passed = rec["position_cap_pass"] is True                     :1254
passed              = netcover_passed and position_cap_passed              :1255
prior_vetted        = bool(source["vetted"])                               :1287
entry_eligible      = source/rec["entry_eligible"]                         :1291-1292
rec["vetted"]       = prior_vetted and passed and entry_eligible is not False :1300-1301
```
持久化侧二次合取 `_score_row :362-370`：`accepted = vetted and netcover_pass and entry_allowed and position_cap_allowed`。

**DB 落点**：`opportunity_scores`（CREATE :194，列 :127）没有 gate 布尔的独立列；全部在 `score_json`；独立列只有派生 `accepted`、`rejection_reason`、`netcover_ratio`。INSERT `ScannerStore._insert_rows :469-498` ← `write_cycle :530`。

## 逐字段

| 字段 | 生产者（文件:行） | 存储 | 读取者 | 测试 | NO_WRITER? |
|---|---|---|---|---|---|
| `vetted`（prior） | `lp_funnel_vet_v1_readonly.py:136 vet_record`（5 闸合取），终闸 :1300 覆写；Solana block :692 写 False | `score_json`；派生 `accepted` | daemon :1287/:362/:1464；`lp_funnel_vet:159`；`lp_c2_once_report:17` | `test_inv_gate_02_terminal_conjunction.py:31,105-133`；`test_lp_scanner_daemon_v1_readonly.py` 多处 | 否 |
| `netcover_pass` | `lp_netcover_engine_v1_readonly.py:382 apply_netcover_gate`；fail-closed :307/319/335/361；daemon :1321 `_fail_closed_netcover`、:693、:1257 | `score_json`；派生 `netcover_ratio`（engine :380） | daemon :1253/:363/:1465 | `test_inv_gate_02:22-26`；`test_lp_scanner_daemon` 415-800 | 否 |
| `permanent_fail_closed_reason` | `lp_pool_resolve_and_rank_v1_readonly.py:885,927,951,977,987,996`；`lp_netcover_inputs:1101,1384,1398`；daemon :1169,1189 | `score_json` | daemon :1250；`lp_rejection_reason:23`；`lp_funnel_autopsy:107`；`lp_funnel_rerank_evaluation:76` | `test_lp_scanner_daemon:555,594,614,671,789`；`test_lp_netcover_inputs:140,416,512,530` | 否 |
| `position_cap_pass` | `lp_netcover_inputs_v1_readonly.py:1040`（CLMM）、`:1359`（AMM） | `score_json` | daemon :1254/:369/:1466；`lp_funnel_autopsy:83` | `test_lp_netcover_inputs:184,196`；`test_lp_funnel_autopsy:32,62` | 否 |
| `entry_eligible` / `entry_block_reasons` | `lp_universe_screener_v1_readonly.py:185-266`（各 gate），合并 :357-361；daemon :686-687 | `score_json` | daemon :1291/:368；`lp_rejection_reason:41-68`；`lp_portfolio_allocator:63` | `test_lp_universe_screener:136,147`；`test_inv_gate_02:22,25,42` | 否 |

**结论：五个终闸字段全部有活生产者，无 NO_WRITER。** 恒 None 只出现在 fail-closed 记录的派生列上（`netcover_ratio`/`rejection_reason`），属设计内。

## A/B 档 `existing_terminal_conjunction`（B1 §9.6）`[主脑核 Q5]`

读：`lp_stock_tier_acceptance_v1_readonly.py:79`、`lp_stock_tier_policy_v1_readonly.py:142`（从 evidence 读入）。写：**无生产脚本产出该字段**，只有测试 fixture `tests/test_lp_stock_tier_policy_v1_readonly.py:95`。→ **确认 NO_WRITER**，A/B 档 `terminal_pass` 恒含一个"没算成"分量（fail-closed 方向安全）。RH 支线的股票终闸不得复制此模式。

## 两张"死表"（B1 §10.3）`[主脑核]`

| 表 | CREATE | INSERT | SELECT | 迁移库行数 | 修正后的结论 |
|---|---|---|---|---|---|
| `market_sessions` | daemon :217 | `lp_rwa_collector_daemon_v1_readonly.py:592-596`（经 `ScannerStore.write_cycle`）；scanner 管线自身 `_session_row :395-413` 恒 None | `lp_panel_server:319-326`；`lp_report_digest:179-233` | 0 | 有写入者，但该 collector daemon 从未在 VPS 运行 → 实际 0 行 |
| `rpc_severe_incidents` | `lp_shadow_gate_v1_readonly.py:86` | `lp_shadow_gate:293`（仅 state ∈ {EXIT_ONLY, KILLED} 时 INSERT OR IGNORE）、:302 UPDATE；接线 daemon :1826/:1859 | `lp_shadow_gate:314,355`；panel :160,217；`lp_c6_preflight:235,240` | 0 | 有写入者且已接入主循环，但触发条件从未满足 → 0 行 |

B1 "0 写入者"表述过时；正确表述是"**有 writer、未触发**"。对 PRD §8.5 的含义不变：RH 不得沿用这两张表当证据，须用独立实际写入的 `rh_market_states` / `rh_rpc_health`。
