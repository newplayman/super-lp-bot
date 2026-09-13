# REQUIREMENT_TRACEABILITY.md — V3 CORE Paper 发布候选

**基线 SHA**: `18a8f39744af2d61d16737b7311d88cd88accea9`
**日期**: 2026-09-13
**审计目标仓库**: `newplayman/super-lp-bot`
**审计目标分支**: `feat/prd-v2.1-m0-shadow`

---

## 0. 设计依据与适用版本

| 文档 | 角色 | 检索路径 |
|---|---|---|
| PRD v1.1 `LP_Bot_Robinhood_Chain_增量转向_PRD_v1.1_CN.md` | 本轮工程落地修订（§6/§7/§8/§11–16/§19–22） | `/opt/lpbot/` |
| `PROJECT_STATE_AND_ARCHITECTURE_20260907_CN.md` | 历史工程/权限基线（不是今日进程实测） | `/opt/lpbot/` |
| `RISK_INVARIANTS.md` | 不变量 | `/opt/lpbot/` |
| `Robinhood_Chain_LP_Bot_50_30_20_全面转向设计文档_v1.0.md` | 业务愿景；与 v1.1 冲突按 v1.1 | `/opt/lpbot/` |
| PRD 通用 v2.1（本轮未取得完整原件） | 上位 PRD | 见 B1 引用 |

**不在本轮范围**：v1.1 通用 PRD 的 STOCK 独立毕业细则、MEME 可闲置策略细节、V4 接入、未知 Hook 适配。

---

## 1. V2 已修复且 V3 保留的 6 项 P1

| ID | 缺陷（V2 审计） | V2 修复 commit | V3 复检结果 |
|---|---|---|---|
| CA-01 | readiness `failed=0` 即 PASS，未看 inconclusive；pytest 退 0 当成功；counters 缺位默认填 0 后 PASS | `6cab3e5` | 保留；V3 W3 进一步接 producer/consumer 真实契约 |
| CA-02 | `verify_intent` 返回 `(False, reasons)` 被吞掉 | `4901f1f` | 保留；V3 W1 接入真实 RH 合法正例 |
| CA-03 | daemon 默认路径写 `SIMULATED_OK` 但 wrapper+simulator 未跑（false-positive） | `5849624` | 保留；V3 W1 "白名单通过不等于模拟成功" |
| CA-04 | writer 自动 `self.conn.commit()` 破坏 caller 事务；IntegrityError 一刀切走 idempotency；admission 后置导致 journal/reservation 不一致 | `1329c78` | 保留；V3 W1 验证事务/第二连接/trigger |
| CA-05 | `run_one_round` 漏传 `capital_usd` → `nav_start=None` → "首末 mark 抵消成本"，round-trip cost 被吞 | `d1dfd03` | 保留；V3 W2 用合法部分仓位真实开关仓验完整 NAV/PnL 勾稽 |
| CA-06 | CI 518 fail 排查；audit-regression YAML/HEAD 校验 | `18a8f39`（仅文档） | 保留；V3 W4 修两个 Go 根因 |

---

## 2. v1.1 PRD T-ID 与代码映射（已实现）

| T-ID | 来源 | 生产者 | Schema | Writer/存储 | Consumer/终闸 | 真实测试 | 当前状态 |
|---|---|---|---|---|---|---|---|
| T01 | 池能力清单 | `lp_rh_capabilities_v1_readonly.py` | `rh_pool_capabilities` | 同上 | `lp_rh_shadow_runner_v1_readonly.py` admission | `test_lp_rh_capabilities_v1_readonly.py` | REQUIRED for CORE |
| T05 | 池注册表 | `lp_rh_registry_v1_readonly.py` | `rh_pool_registry` | 同上 | admission decision | `test_lp_rh_registry_v1_readonly.py` | REQUIRED for CORE |
| T06 | 池身份链上核验 | `lp_rh_pool_probe_v1_readonly.py` | `rh_pool_probe` | 同上 | whitelist gate | `test_lp_rh_pool_probe_v1_readonly.py` | REQUIRED for CORE（V3 W1 强化 RH 适配） |
| T07 | token0/token1 顺序 | `lp_rh_pool_probe_v1_readonly.py` | 同上 | 同上 | decoder | `test_lp_rh_pool_probe_v1_readonly.py` | REQUIRED for CORE |
| T08 | 报价输入 | `lp_rh_netcover_inputs_v1_readonly.py` / `lp_rh_premium_guard_v1_readonly.py` | `rh_quote_snapshot` | 同上 | risk gate | `test_lp_rh_premium_guard_v1_readonly.py` | REQUIRED for CORE |
| T09 | 未知 Hook 隔离 | `lp_rh_pool_probe_v1_readonly.py` | 同上 | 同上 | admission fail-close | `test_lp_rh_pool_probe_v1_readonly.py` | REQUIRED（unknown hook → UNSUPPORTED） |
| T10 | pool state freshness | `lp_rh_pool_probe_v1_readonly.py` | `rh_pool_state` | 同上 | admission | `test_lp_rh_pool_probe_v1_readonly.py` | REQUIRED for CORE |
| T11 | 数据时效 | `lp_rh_capabilities_v1_readonly.py` / `lp_rh_reference_freshness_v1_readonly.py` / `lp_rh_reorg_rollback_v1_readonly.py` | `rh_reference_freshness` | 同上 | adapter | `test_lp_rh_reference_freshness_v1_readonly.py` | REQUIRED for CORE |
| T12 | 双源 quote | `lp_rh_collector_v1_readonly.py` / `lp_rh_capabilities_v1_readonly.py` | `rh_quote_collector` / `rh_rpc_health` | 同上 | admission + readiness | `test_lp_rh_collector_v1_readonly.py` | REQUIRED for live；advisory for paper |
| T13 | quote collector 行为 | `lp_rh_capabilities_v1_readonly.py` / `lp_rh_fault_injection_v1_readonly.py` | 同上 | 同上 | readiness g11 | `test_lp_rh_fault_injection_v1_readonly.py` | 同 T12 |
| T14 | 计划窗口覆盖率 | `lp_rh_fault_injection_v1_readonly.py` / `lp_rh_coverage_report_v1_readonly.py` | `rh_coverage_window` | 同上 | coverage report | `test_lp_rh_fault_injection_v1_readonly.py` | REQUIRED for Stage A |
| T18 | STOCK reference（独立 research） | `lp_rh_stock_reference_v1_readonly.py` | `rh_stock_reference` | 同上 | STOCK admission | `test_lp_rh_stock_reference_v1_readonly.py` | NOT_ACTIVATED（V3 仅 CORE） |
| T19 | STOCK on-chain | 同上 | 同上 | 同上 | 同上 | `test_lp_rh_stock_reference_v1_readonly.py` | NOT_ACTIVATED |
| T20 | STOCK funding/treasury | 同上 | 同上 | 同上 | 同上 | 同上 | NOT_ACTIVATED |
| T21 | STOCK 风险独立参数 | 同上 | 同上 | 同上 | 同上 | 同上 | NOT_ACTIVATED |
| T23 | STOCK 退出 | 同上 | 同上 | 同上 | 同上 | 同上 | NOT_ACTIVATED |
| T24 | STOCK 报告 | 同上 | 同上 | 同上 | daily report | 同上 | NOT_ACTIVATED |
| T26 | MEME 聚合 | `lp_rh_meme_aggregation_v1_readonly.py` | `rh_meme_aggregates` | 同上 | MEME view（research only） | `test_lp_rh_meme_aggregation_v1_readonly.py` | NOT_ACTIVATED（V3 不开 MEME 仓） |
| T27 | 预算预占 | `lp_rh_bucket_ledger_v1_readonly.py` | `rh_bucket_reservations` | TxIntentWriter（`lp_rh_tx_intents_writer_v1.py`） | admission | `test_lp_rh_bucket_ledger_v1_readonly.py` + CA-04 测试 | REQUIRED for CORE |
| T29 | gas reserve | `lp_rh_gas_reserve_v1_readonly.py` | `rh_gas_reserve` | 同上 | admission | `test_lp_rh_gas_reserve_v1_readonly.py` | REQUIRED for CORE |
| T31 | size 区间 | `lp_rh_size_interval_v1_readonly.py` | `rh_size_interval` | 同上 | risk gate | `test_lp_rh_size_interval_v1_readonly.py` | REQUIRED for CORE |
| T33 | runner episode | `lp_rh_shadow_runner_v1_readonly.py` | `rh_shadow_episodes` / `rh_shadow_steps` / `rh_position_marks` / `rh_journal` / `rh_bucket_reservations` | 同上 | episode_summary | `test_lp_rh_shadow_runner_v1_readonly.py`（39 fail = A 类） | REQUIRED；A 类 39 fail 待 W1/W2 修复 |
| T34 | gas estimator | `lp_rh_gas_estimator_v1_readonly.py` / `lp_rh_gas_refresh_v1_readonly.py` | `rh_gas_history` | 同上 | admission | `test_lp_rh_gas_estimator_v1_readonly.py` | REQUIRED for CORE |
| T35 | NetCover 输入 | `lp_rh_netcover_inputs_v1_readonly.py` | `rh_netcover_inputs` | 同上 | terminal gate | `test_lp_rh_netcover_inputs_v1_readonly.py` | REQUIRED for CORE |
| T41 | HODL lots | `lp_rh_shadow_runner_v1_readonly.py` | `rh_hodl_lots` | 同上 | episode_summary | `test_lp_rh_shadow_runner_v1_readonly.py::test_hodl_initial_legs_constant_t41`（fail） | REQUIRED；A 类 fail |
| T51 | 幂等 + reservation 释放 | `lp_rh_bucket_ledger_v1_readonly.py` | `rh_bucket_reservations` | 同上 | admission | `test_lp_rh_bucket_ledger_v1_readonly.py` | REQUIRED for CORE |

---

## 3. v1.1 PRD T-ID 当前未实现或部分实现

| T-ID | 范围 | 当前状态 | V3 计划 |
|---|---|---|---|
| T02 | fault injection 多场景 | 部分实现 | W1 端到端故障注入 |
| T03 | 边界/异常输入 | 部分 | W1 + W2 |
| T04 | NetCover 校准 | 部分 | 不在 V3 范围（已有 `lp_netcover_calibration_v1_readonly.py`） |
| T58 | 退出压力测试 | 部分 | W2 强化 |
| T59 | 报告 schema | 部分 | W3 readiness 契约 |
| T60 | 资本政策与未知 Hook 隔离 | 未实现 | W0-W5 协调；不在 V3 内改阈值 |

---

## 4. RH 不变量（RH-INV-01–18）

| ID | 名称 | 代码出处 | V3 验收路径 |
|---|---|---|---|
| RH-INV-01 | 十向终闸合取（terminal gate） | `lp_rh_terminal_gate_v1_readonly.py:4` PRD v1.1 §11.5 | W3 readiness gate |
| RH-INV-04 | 同上定义位置 | 同上 | W3 |
| RH-INV-12 | wallet balance 变化已计入不再扣 | `lp_rh_pnl_v1_readonly.py:6` | W2 NAV 公式 |
| RH-INV-13 | 资金流不重复记账（IntegrityError 必冒泡） | `lp_rh_pnl_v1_readonly.py:30`/`:291`；`lp_rh_shadow_runner_v1_readonly.py:1452`；`lp_rh_shadow_daemon_v1_readonly.py:344` | W1 + W2 事务/幂等 |
| RH-INV-14 ~ 18 | 推断存在但代码未引用 | — | 在 v1.1 PRD 文档中查找（V3 不逐一验证） |

> 仅核实代码引用的不变量；其余在 PRD 内未在 v3 范围内单独测试。

---

## 5. 6 受保护常量（CLAUDE.md 冻结）

```text
STABLE_MIN_FRAC          = 0.7
NETCOVER_SHADOW          = 1.0
NETCOVER_TINY_LIVE       = 1.5
POSITION_TVL_SHARE       = 0.0005
HARD_POSITION_TVL_SHARE  = 0.001
LVR_COEFFICIENT_MODEL   = 0.50
```

V3 范围内**禁止修改**这六个常量。

---

## 6. V3 最小验收矩阵（V3R-01–12）

| ID | 必须证明 | PRD 关联 | V3 work package | 当前复核状态 | 下一阶段验证 |
|---|---|---|---|---|---|
| V3R-01 | 同一固定 SHA 下真实 producer 输出能被真实 readiness 消费；错配/缺证据失败 | T55/T59；CA-01 | W3 | BLOCKED_BY_SCHEMA_MISMATCH | producer/consumer 版本化 schema + 真实运行 |
| V3R-02 | chain+role+ABI+code 绑定，RH 合法 rawcall 通过；Base/错误链/recipient 被拒 | T01/T06/T07/T48/T49；CA-02 | W1 | BLOCKED_BY_CHAIN_AND_CONTEXT_WIRING | RH manifest + 合法正例 + 单因素负控制 |
| V3R-03 | 合法控制实际 grant，单因素拒绝无新仓财务副作用 | T27/T48/T55；CA-03/04 | W1 | BLOCKED_BY_ADMISSION_ORDER | admission-precede + 真实 grant + 单因素拒绝 |
| V3R-04 | 文件 SQLite / 真实 writer / trigger 故障 / 第二连接 / 幂等不同 payload 拒绝 | T27/T51/T52；CA-04 | W1 | NOT_FULLY_VERIFIED | 故障注入 + 第二连接 + IntegrityError 分类 |
| V3R-05 | 合法 size 的实际开关仓使组合 1000→990、PnL−10；不以零仓位替代 | T35/T38–42；CA-05 | W2 | NOT_PROVEN_BY_CURRENT_CA05_TEST | 真实 part-size 100 + round-trip cost 10 + 完整持久化勾稽 |
| V3R-06 | 跨轮、重启、重叠/迟到样本不重置本金/基准或重复费用 | T11/T36/T41/T52 | W2 | NOT_VERIFIED_IN_THIS_AUDIT | 持续 portfolio + 事件 cursor + 重启 E2E |
| V3R-07 | collect/注资不造利、退出残余库存仍有风险与清算估值 | T38–46 | W2 | NOT_FULLY_VERIFIED | collect/remove/残余库存测试矩阵 |
| V3R-08 | 配置真实解析、严格计数、外部 run 绑定、全 skip/UNKNOWN 不放行 | T47/T55/T58；CA-01 | W3 | BLOCKED_BY_EVIDENCE_VALIDATION_GAPS | 真实 TOML 解析 + 严格计数 + UNKNOWN fail-close |
| V3R-09 | 计划窗口覆盖分母不删坏样本；缺输入不同于经济失败 | T14/T32/T36/T59 | W3 | RUNTIME_EVIDENCE_NOT_REVIEWED | 实际窗口覆盖与缺输入分类 |
| V3R-10 | 原始 CI/JUnit/退出码与报告一致；Go 两根因分别处理 | RH-08；CA-06 | W4 | FAILED_CI | Dexscreener tag 修 + quality-gate linter 固定 + 实际 Govulncheck 完成 |
| V3R-11 | 独立 Paper 入口/状态/日志预算/退出信号/恢复经过受控端到端测试 | T52/T57/T58 | W5 | NOT_VERIFIED_IN_THIS_AUDIT | preflight/status/--once + PID 锁 + 资源预算 + E2E |
| V3R-12 | 资本政策冲突不阻离线研究但阻 live；未知 Hook 及未毕业 profile 不放行 | T09/T25/T60 | W0-W5 | LIVE_APPROVAL_NOT_ESTABLISHED | 100U 旧政策与 CORE 42.5% 上限冲突显式登记；MEME/STOCK/V4 不开仓 |

---

## 7. STOCK / MEME / V4 / 未知 Hook 状态

| Profile | 状态 | V3 是否进入准入 | 禁止/允许原因 |
|---|---|---|---|
| CORE V3 | REQUIRED | 是 | v3.1 第一个发布候选；RH 主线 |
| STOCK | NOT_ACTIVATED | 否 | 独立研究；毕业前不进 CORE 仓；T18–T24 仅 reference 数据 |
| MEME | NOT_ACTIVATED | 否 | 默认仅观察；T26 仅作聚合视图 |
| V4 | NOT_ACTIVATED | 否 | 未知钩子 + 未实现 ABI；T09 → UNSUPPORTED |
| 未知 Hook（Core 之外的任何未登记 hook） | NOT_ACTIVATED | 否 | T09 fail-close；写 `UNSUPPORTED_HOOK` 拒绝 |
| Base/Aerodrome（旧实现） | NOT_ACTIVATED for V3 | 否 | V3 目标链是 RH（chain_id=4663），Base 路径隔离 |

---

## 8. 受冻结的运行时参数（绝对禁止修改）

来源：CLAUDE.md `Project Status` 段、`ProjectState` 文档 §1/§3/§5/§6/§7/§11：

```text
live_allowed                        = false        # 不可放宽
tiny_live_authorized                = false        # 不可设 true
edge_proven                         = no           # 不可改
tiny_canary_allowed                 = no           # 不可改
recommended_next_action             = STOP_LP_RESEARCH_NOW
```

V3 不启动 paper/live/canary daemon，不创建/导入私钥，不签名，不广播，不修改 main 分支。

---

## 9. 真理来源（仅 SHA + 实际跑过产物）

| 项 | 值 |
|---|---|
| 仓库 | `newplayman/super-lp-bot` |
| 分支 | `feat/prd-v2.1-m0-shadow` |
| reviewed SHA | `18a8f39744af2d61d16737b7311d88cd88accea9` |
| CI run | 34742810457（run_attempt=1） |
| CI python job | 103685283999 |
| 本地 pytest 基线 | 5126 tests / 53 fail / 5059 pass / 14 skip / 58.51s |
| CI pytest 实测 | 5126 tests / 415 fail / 4676 pass / 30 skip / 5 err / 60.52s |
| 本地 JUnit | `reports/paper_closeout_v3_rev1/baseline_18a8f39/junit.xml` |
| 失败明细 JSON | `reports/paper_closeout_v3_rev1/baseline_18a8f39/failures.json` |
| 失败分类 | `reports/paper_closeout_v3_rev1/FAILURE_INVENTORY.json` |

---

## 10. W0 验收

- [x] 已读原件：PRD v1.1 / PROJECT_STATE / RISK_INVARIANTS / v3 taskpack
- [x] HEAD/dirty/路径核实：18a8f39，0 tracked 改动
- [x] 实际 CI 计数登记：415/4676/30/5 撤回 V2 的 405/4724
- [x] V2 五类修复保留（CA-01 ~ CA-05 + CA-06 文档）
- [x] FAILURE_INVENTORY.json：local 53 categorized + CI-only 362 estimated
- [x] REQUIREMENT_TRACEABILITY.md：本文件
- [x] 不重复旧 V2 摘要
