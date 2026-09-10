<!-- METADATA
generated_at: 2026-09-10T20:05:11.004271Z
code_version: bc780ecda7a6
working_tree_clean: False
db_path: /opt/lpbot/lp-bot-v3-origin-check/reports/lp_rh/scanner.db
as_of: 2026-09-10T20:05:00.859144Z
-->

# RH 毕业就绪度面板 (Graduation Readiness Dashboard)

- as_of: 2026-09-10T20:05:00.859144Z
- verdict: FAIL
- next_allowed_task: resolve live-gate blockers before any LIVE action: SINGLE_PROVIDER_NOT_ALLOWED_FOR_LIVE, CAPITAL_POLICY_NOT_APPROVED
- explicitly_not_authorized: LIVE_EXECUTION

## 首页六问

- **当前模式与授权是什么？是否只有 Shadow？哪一道门阻止 LIVE？**
  - answer: NOT_MEASURED
- **三桶预算、LP 部署、钱包风险库存、预留在途资金和原生 gas 分别多少？**
  - answer: NOT_MEASURED
- **从发现到可部署剩多少池？未计算、不盈利、不支持、政策阻挡分别多少？**
  - answer: NOT_MEASURED
- **实际净值／现金流／HODL 差／净手续费分别是多少？哪些是虚拟、估计或陈旧值？**
  - answer: NOT_MEASURED
- **最近的主导成本是什么？持有／不建仓／再平衡哪个保守 EV 更好？**
  - answer: NOT_MEASURED
- **能否按当前仓位 size 退出？最近退出模拟何时完成，有没有未知交易或残余库存？**
  - answer: NOT_MEASURED

## 四阶段进度

- Stage A: [##--------] hours=11.931784367222223/72 coverage_ratio=0.9958100558659217877094972067 passed=false
  - 判定窗口: 自 2026-09-10T08:08:59Z 起 (code_version=ee98d3dd5668), 窗口内 2852 行
  - 参考(不判定): 累计 hours=62.82956213833333 coverage=0.9686318721400623383513495590 | 近72h coverage=0.9686318721400623383513495590
  - blockers: HOURS_COVERED_INSUFFICIENT, STAGE_A_SYNTHETIC_TESTS_FAILED
  - synthetic: FAILED (SYNTHETIC_EVIDENCE_STALE_CODE_VERSION)
  - key_fields:
    - reference_mid: ratio=0.9945227988497877584554292756 (窗口行数=14606) passed=true
    - sample_time: ratio=1 (窗口行数=14606) passed=true
    - session: ratio=1 (窗口行数=14606) passed=true
    - fee_growth_global_0: ratio=0.9938912645082467929138668296 (窗口自 2026-09-09T16:05:55.424357Z 起, 最近 6548/14606 行) passed=true
    - fee_growth_global_1: ratio=0.9937385461209529627367135003 (窗口自 2026-09-09T16:05:55.424357Z 起, 最近 6548/14606 行) passed=true
- Stage B: [#---------] days=2/14 passed=false
  - blockers: DAYS_COVERED_INSUFFICIENT, WEEKENDS_COVERED_INSUFFICIENT
- Stage C: [#---------] days=2/30
- Stage D (LIVE): live_allowed=false

## 终闸十项当前值 (10 项)

- legacy_required_conjunction: False
- identity_verified: True
- protocol_capabilities_sufficient: True
- data_complete_and_fresh: True
- profile_policy_pass: True
- market_and_chain_risk_pass: False
- netcover_pass: True
- absolute_profit_pass: True
- position_and_exit_depth_pass: True
- capital_policy_pass: True

## 证据新鲜度

| source | fetched_at | source_event_time | age_secs | quality |
|---|---|---|---|---|
| rh_rpc:pool_state | 2026-09-10T20:05:00.859144Z | 2026-09-10T20:05:00Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T20:04:45.858847Z | 2026-09-10T20:04:45Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T20:04:30.858350Z | 2026-09-10T20:04:30Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T20:04:15.858240Z | 2026-09-10T20:04:14Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T20:04:00.858152Z | 2026-09-10T20:04:00Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T20:03:45.857514Z | 2026-09-10T20:03:45Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T20:03:30.857191Z | 2026-09-10T20:03:30Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T20:03:15.857098Z | 2026-09-10T20:03:14Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T20:03:00.856975Z | 2026-09-10T20:03:00Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T20:02:45.856871Z | 2026-09-10T20:02:44Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T20:02:30.856770Z | 2026-09-10T20:02:30Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T20:02:15.856644Z | 2026-09-10T20:02:15Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T20:02:00.856542Z | 2026-09-10T20:02:00Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T20:01:45.856427Z | 2026-09-10T20:01:45Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T20:01:30.856331Z | 2026-09-10T20:01:30Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T20:01:15.856222Z | 2026-09-10T20:01:15Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T20:01:00.856116Z | 2026-09-10T20:01:00Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T20:00:45.855998Z | 2026-09-10T20:00:45Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T20:00:30.855899Z | 2026-09-10T20:00:30Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T20:00:15.855800Z | 2026-09-10T20:00:15Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T20:00:00.855684Z | 2026-09-10T20:00:00Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T19:59:45.855579Z | 2026-09-10T19:59:45Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T19:59:30.855483Z | 2026-09-10T19:59:30Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T19:59:15.855380Z | 2026-09-10T19:59:15Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T19:59:00.855264Z | 2026-09-10T19:59:00Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T19:58:45.855172Z | 2026-09-10T19:58:45Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T19:58:30.855054Z | 2026-09-10T19:58:30Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T19:58:15.854905Z | 2026-09-10T19:58:15Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T19:58:00.854809Z | 2026-09-10T19:57:59Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T19:57:45.854693Z | 2026-09-10T19:57:45Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T19:57:30.854578Z | 2026-09-10T19:57:30Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T19:57:15.854457Z | 2026-09-10T19:57:15Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T19:57:00.854337Z | 2026-09-10T19:57:00Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T19:56:45.854241Z | 2026-09-10T19:56:45Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T19:56:30.854151Z | 2026-09-10T19:56:30Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T19:56:15.854025Z | 2026-09-10T19:56:15Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T19:56:00.853925Z | 2026-09-10T19:56:00Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T19:55:45.853826Z | 2026-09-10T19:55:44Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T19:55:30.853719Z | 2026-09-10T19:55:30Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T19:55:15.853563Z | 2026-09-10T19:55:15Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T19:55:00.853452Z | 2026-09-10T19:55:00Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T19:54:45.853354Z | 2026-09-10T19:54:45Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T19:54:30.853234Z | 2026-09-10T19:54:30Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T19:54:15.853135Z | 2026-09-10T19:54:15Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T19:54:00.853015Z | 2026-09-10T19:53:59Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T19:53:45.852911Z | 2026-09-10T19:53:45Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T19:53:30.852774Z | 2026-09-10T19:53:29Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T19:53:15.852663Z | 2026-09-10T19:53:15Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T19:53:00.852556Z | 2026-09-10T19:52:59Z | None | OK |
| rh_rpc:pool_state | 2026-09-10T19:52:45.852411Z | 2026-09-10T19:52:45Z | None | OK |

## 预算用量

- bytes: 32823392
- soft_budget_bytes: 2147483648
- fraction: 0.01528458297252655
- state: OK
