# 历史报告结论有效性只读审计报告（基于三层经济缺陷证伪）

**审计日期**：2026-09-09  
**审计执行**：只读独立审计员  
**正确基准**：`reports/ECONOMICS_corrected_20260909.md` 及独立参考实现 `reports/golden_reference_20260909.py`  
**审计范围**：`reports/` 根目录下全部 67 个 `.md` 文件（不进行子目录扫描，不改动任何既有文件）

---

## 背景：三层经济缺陷复核基准

1. **手续费量纲错误（虚高 1022 倍）**：  
   `accrued += position_usd * (d0+d1) / 2**128`。将每单位流动性的 token 原始增量直接乘 USD 名义值，且混加了 18-dec 与 6-dec 整数。实测年化费率从虚高的 **29,076%** 骤降至真实的 **26.68%~34.09%**（commit `12efd38` 已修代码，但历史 DB 未重算）。
2. **HODL 基准规模与窗口失真（放大 2.485 倍）**：  
   使用虚拟 `1 token0 + 1 token1`（约 $2485）对比 $1000 仓位，且 NAV 与 HODL 首尾取步未对齐。
3. **NAV 从不市价重估（结构性假正）**：  
   `lp_principal` 恒为 `position_usd`，NAV 唯一变动项是只增不减的手续费，屏蔽了占同期手续费 **81 倍** 的价格波动损失，使回放数学上不可能报亏。
4. **数据库历史污染**：  
   `reports/lp_rh/shadow.db` 的 `rh_shadow_episodes` 表 **87 个 episode 全部建立在上述错误逻辑之上**，任何直接引用该表统计产出的指标均失真。

---

# 一、结论摘要

全量 67 份顶级报告审计分类：**完全作废 9 份，部分受影响 15 份，不受影响 43 份**。

| 文件名 | 判定 | 受影响的具体章节与数字 / 核心依据 |
|---|---|---|
| `CLEAN_PROOF_SURFACE_CN.md` | **完全作废** | 全文作废。表格中 6h/24h 的 `median_net_pnl_pct` (0.158153, 0.160851)、`p10` 及 `pct_signal=better` 均建立在未扣减价格重估及错误累费逻辑之上。 |
| `CLEAN_PROOF_SURFACE_V2_CN.md` | **完全作废** | 全文作废。表格中 `median_net_pnl_pct` (0.110705, 0.118443)、`top20 p10` (0.233600, 3.591802) 严重虚高，策略有 edge 的结论无效。 |
| `COHORT_PNL_PROOF_CN.md` | **完全作废** | 全文作废。`future_clean 24h top20 median = 5.289953`、`combined_clean` 各项百分位收益全表失真。 |
| `FULL_STRATEGY_CLEAN_PROOF_CN.md` | **完全作废** | 全文作废。宣称 24h 胜率 82.85%、平均收益 0.92%、top20 中位数 4.126% 的核心绩效表彻底作废。 |
| `POOL_POSITION_QUARANTINE_SIM_CN.md` | **完全作废** | 全文作废。以错误 PnL 为基底模拟的剔除仓位/池子后 median、p10~p1 收益全表无效。 |
| `POSITION_LEVEL_CLEAN_PROOF_CN.md` | **完全作废** | 全文作废。仓位级聚合胜率 90.0%~96.8%、avg (0.045%~0.419%)、median 均依赖错误收益底座。 |
| `POSITION_LEVEL_PROOF_V1_CN.md` | **完全作废** | 全文作废。核心 23 列表格中所有 win_rate (81.25%~83.33%)、avg_net_pnl_pct、median、top20_median 全部失真。 |
| `POSITION_LEVEL_QUARANTINE_SIM_CN.md` | **完全作废** | 全文作废。隔离模拟产生的 median (0.021%~0.069%) 及分位数收益全表无效。 |
| `POSITION_LEVEL_QUARANTINE_V2_CN.md` | **完全作废** | 全文作废。全表胜率 (80%~100%)、median、p10~p1 数据基底错误。 |
| `AUDIT_stage_a_prd_reconciliation_20260909.md` | **部分受影响** | §1 #3、§2 #3、§3、§5 中指出“仅最近 4 小时有有效费用数据”的表述需更正：这 4 小时在 runner 中同样因量纲与未重估而失真，**实际有效经济回放时长为 0 小时**。其阻断 Stage A 毕业的总体判定依然完全有效。 |
| `AUDIT_hodl_scale_20260909.md` | **部分受影响** | §2 表格中“等比例缩放值（-39.10 缩至 -15.73）”仅为诊断性线性缩放，未包含 V3 非对称两腿修正与窗口对齐；其指出 HODL 尺度失真与手续费量纲错误的审计结论有效。 |
| `CLEAN_REMOTE_VS_DIRTY_CHECKPOINT_CN.md` | **部分受影响** | Horizon metrics 中引用的 `pct_signal = better` 及收益评价受影响；数据质量门与 invalid_rate 清零部分不受影响。 |
| `ENTRY_UNTRUSTED_EXCLUSION_IMPACT_CN.md` | **部分受影响** | 表格中 top20/bottom20 median pct (如 4.255168) 失真需重算；血缘断裂归因于少数池/仓位的结论有效。 |
| `TERMINAL_CLEAN_24H_WORSE_ROOT_CAUSE_CN.md` | **部分受影响** | 摘要表及各仓位/退出原因中的收益数值（如 `fees +78.43, fees +24.62`）失真；但归因于样本极度集中与真实退出亏损的定性有效。 |
| `TERMINAL_EXIT_PNL_AUDIT_CN.md` | **部分受影响** | Summary 表中的 median/p10/p90 及 Exit Reason 中记载的手续费/盈亏字符串数值需重算；退出动作与可审计性覆盖率不受影响。 |
| `TERMINAL_TAIL_CLEAN_V2_CN.md` | **部分受影响** | 表格中 terminal_clean 的 median、p10~p1 收益分位数值需重算。 |
| `TERMINAL_TAIL_CLUSTER_ATTRIBUTION_CN.md` | **部分受影响** | 亏损绝对美金金额（如 $7,174, $5,827）及排除后模拟 PnL 需重算；关于亏损高度集中在少数池/仓位的结论有效。 |
| `TERMINAL_TAIL_CONCENTRATION_CN.md` | **部分受影响** | worst_position_loss_usd 等具体亏损数值受 trace 乘积与旧估值影响需重算；集中度高 (HHI~0.3) 的结论有效。 |
| `TERMINAL_TAIL_RISK_AFTER_ZERO_BUG_CN.md` | **部分受影响** | 表格中 p10 (-2.37%)、p5、p1 及 worst 50 的 net_pnl_pct 数字需重算；zero-bug 不是唯一负尾部原因的定性有效。 |
| `TERMINAL_WORST_CLUSTER_AUDIT_CN.md` | **部分受影响** | Worst Positions/Pools 表中的 `net_pnl_pct` 和 `terminal_value_usd` 需重算；归因为真实持仓亏损与重复污染的结论有效。 |
| `TERMINAL_ZERO_BUG_EXCLUSION_AUDIT_CN.md` | **部分受影响** | 表格中 p10 (-2.370946) 与 median 需重算；zero-bug 独立可剔除的定性有效。 |
| `WORST_POOL_LIFECYCLE_DEEPDIVE_CN.md` | **部分受影响** | 表格中 median_net_pnl_pct、p10、p5 需重算；池子结构性风险定性有效。 |
| `WORST_POSITION_LIFECYCLE_AUDIT_CN.md` | **部分受影响** | 表格中 entry_value_usd、terminal_value_usd、net_pnl_pct 需重算；trace 重复污染定性有效。 |
| `WORST_POSITION_LIFECYCLE_DEEPDIVE_CN.md` | **部分受影响** | 表格中 net_pnl_pct 需重算；`loss_real=yes` 与 `root_cause=TRACE_DUPLICATION_ARTIFACT` 定性有效。 |
| `AUDIT_duplicate_v3_inventory_20260909.md` | **不受影响** | 纯底层数学公式与精度推导，确认了 canonical 规范实现，揭露了各处重复实现的量纲与 quote 缺陷。 |
| `AUDIT_gas_stagea_20260909.md` | **不受影响** | 纯链上 Gas 观测与采样时间跨度推算，与收益公式无关。 |
| `AUDIT_silent_failure_hunt_20260909.md` | **不受影响** | 针对脚本代码逻辑中的 8 类静默假绿缺陷进行的静态与变异审计。 |
| `AUDIT_silent_failure_hunt2_20260909.md` | **不受影响** | 针对 BSC/Base 边界与默认值逻辑进行的第二轮猎杀审计。 |
| `AUDIT_three_uncertainties_20260909.md` | **不受影响** | 针对多资产覆盖率高估、V4 池哈希碰撞、`size_interval` 接受 Infinity 的边界审计。 |
| `CLEAN_REMOTE_REPAIRED_V2_READINESS_CN.md` | **不受影响** | 纯环境、代码分支、RPC 与测试套件就绪检查。 |
| `CURRENT_FULL_STRATEGY_FAIL_FREEZE_CN.md` | **不受影响** | 策略冻结决定（判为 FAIL，禁止 canary），否决判定依然完全有效。 |
| `DECISION_TRACE_DUPLICATION_AUDIT_CN.md` | **不受影响** | 审计 trace 采样重复率（32 仓位产生 2.4 万次决策），为纯血缘与结构审计。 |
| `ECONOMICS_corrected_20260909.md` | **不受影响** | 本次纠偏的基准源文件，真实记录了 34% 手续费与短窗口价格波动主导事实。 |
| `ENTRY_UNTRUSTED_ROOT_CAUSE_CN.md` | **不受影响** | 针对缺失 position_id 的血缘断裂根因审计。 |
| `ENTRY_UNTRUSTED_TOP20_DEEPDIVE_CN.md` | **不受影响** | 针对 entry_untrusted 在 top20 中的样本分布与分类审计。 |
| `FINAL_VERDICT.json` | **不受影响** | 终审裁定 `status: FAIL`、`tiny_canary_allowed: no`，否决依然有效且不可推翻。 |
| `FIXED_HORIZON_COUNTERFACTUAL_CN.md` | **不受影响** | 概念性分析，明确指出 fixed-horizon 仅为假说，未证明策略成立。 |
| `GATE_CONCLUSION_CN.md` | **不受影响** | 闸门结论判定 `FAIL`，明令禁止在 OOS 期间讨论 canary。 |
| `GATE_SQL_CONSISTENCY_AUDIT_CN.md` | **不受影响** | 报表间 SQL 查询口径一致性核账。 |
| `NEXT_ACTION_DECISION_CN.md` | **不受影响** | 裁定 `tiny_canary_allowed: no`，维持 OOS 采集阶段。 |
| `OVERNIGHT_CONTROL_STATE_CN.md` | **不受影响** | 运行进程与环境系统状态快照。 |
| `OVERNIGHT_FINAL_VERDICT_CN.md` | **不受影响** | 裁定 `FAIL` 与 `tiny_canary_allowed = no`。 |
| `POSITION_LIFECYCLE_MATERIALIZATION_CN.md` | **不受影响** | 纯 68 行仓位物化行数记录。 |
| `POSITION_MARK_GAP_CAUSAL_AUDIT_CN.md` | **不受影响** | 证明 pool_mark_only 主因为持仓在目标时间前已终止，属生命周期时间戳因果审计。 |
| `POSITION_MARK_REALITY_AUDIT_CN.md` | **不受影响** | 仓位未来 mark 缺失的时间窗口因果审计。 |
| `POSITION_MARK_REPAIR_PLAN_CN.md` | **不受影响** | 数据库研究层表结构与 DDL 设计方案。 |
| `PROOF_EXCLUSION_POLICY_CN.md` | **不受影响** | 污染样本排除政策与方法论定义。 |
| `PROOF_SURFACE_POLICY_CN.md` | **不受影响** | 证据层级治理规范，明文要求 `tiny_canary_allowed 保持 no`。 |
| `RECENT_MARK_GAP_CAUSAL_CN.md` | **不受影响** | 近期样本 mark 缺失的时间因果统计（100% 为提前退出）。 |
| `RECENT_OOS_POSITION_LEVEL_PROOF_CN.md` | **不受影响** | 认定样本量极度不足（只有 2 个仓位）的阻断性审计。 |
| `RECENT_POSITION_MARK_COVERAGE_CN.md` | **不受影响** | 时间覆盖率指标统计。 |
| `REPAIRED_V2_SCHEMA_CHECK_CN.md` | **不受影响** | PostgreSQL 表存在性与 Goose 版本检查。 |
| `REVIEW_tonight_fixes_20260909.md` | **不受影响** | 今晚代码提交与变异测试有效性审查报告。 |
| `SHADOW_TERMINAL_POSITION_MARKS_REPAIRED_V1_CN.md` | **不受影响** | 终端标线研究表模式与语义设计。 |
| `SHADOW_TERMINAL_POSITION_MARKS_REPAIRED_V1_MATERIALIZATION_CN.md` | **不受影响** | 物化时间戳与行数有效性分布。 |
| `STRATEGY_BOUNDARY_FINAL_CN.md` | **不受影响** | 策略边界裁决 `FAIL`。 |
| `STRATEGY_HYPOTHESIS_SPLIT_CN.md` | **不受影响** | 明确拆分全策略与假说，维持 canary 禁用。 |
| `STRATEGY_PROOF_BOUNDARY_CN.md` | **不受影响** | 边界定义，明文禁止 canary。 |
| `SYNC_RECOVERY_ARTIFACT_INDEX.md` | **不受影响** | 文档索引，确认未触碰任何交易钱包或实盘广播。 |
| `TERMINAL_CLEAN_SQL_DIAG_CN.md` | **不受影响** | 纯数据库字段存在性与数据类型诊断。 |
| `TERMINAL_INCLUSIVE_RESIDUAL_AUDIT_CN.md` | **不受影响** | 非严格有效样本行数与占比审计。 |
| `TERMINAL_LINEAGE_JOIN_AUDIT_CN.md` | **不受影响** | 发现 `id` 与 `trace_id` 字段名不一致的纯 SQL 连接缺陷审计。 |
| `TERMINAL_MATERIALIZER_FEASIBILITY_CN.md` | **不受影响** | 数据源可靠性与物化可行性技术评审。 |
| `TERMINAL_NEAR_EXIT_MARK_AUDIT_CN.md` | **不受影响** | 标线与退出时间绝对时间差分析（0 秒精确对齐）。 |
| `TERMINAL_NEGATIVE_TAIL_AUDIT_CN.md` | **不受影响** | 诊断出 27 条 -100% 记录为 zero-bug 的错误归因报告。 |
| `TERMINAL_OUTCOME_AVAILABILITY_CN.md` | **不受影响** | 退出决策与动作数据完备率统计。 |
| `TERMINAL_POSITION_MARK_SOURCE_AUDIT_CN.md` | **不受影响** | 标线来源统计（确认均为 pool_mark_only）。 |

---

# 二、★指导真钱决策的文档（重点专项核查）

用户是实盘操盘者，一个虚高三个数量级的收益率会把资金分配与仓位规模彻底带偏。本节对 67 份文件中所有触及资金、准入、实盘风控与规模的文档进行专项穿透核查。

### 1. 核心结论：有没有任何一份文件在批准或指导「上真钱 / micro-live」？
**结论是明确的：绝对没有。没有任何一份报告批准了真钱执行。**

- 全仓库顶层裁决文档（`FINAL_VERDICT.json`、`OVERNIGHT_FINAL_VERDICT_CN.md`、`NEXT_ACTION_DECISION_CN.md`、`GATE_CONCLUSION_CN.md`、`CURRENT_FULL_STRATEGY_FAIL_FREEZE_CN.md`、`PROOF_SURFACE_POLICY_CN.md`、`STRATEGY_PROOF_BOUNDARY_CN.md`、`SYNC_RECOVERY_ARTIFACT_INDEX.md`）全部执行了 **死锁级的一票否决**：
  ```json
  "tiny_canary_allowed": "no",
  "tiny_canary_candidate": "no",
  "current_full_strategy": "FAIL",
  "edge_proven": "no"
  ```
- **关键事实**：系统此前之所以全面冻结真钱，**是因为在持仓生命周期审计中发现了不可接受的尾部亏损（p10 为 -2.24%~-2.37%，极端亏损达 -2.54%~-3.41%），以及严重的数据采样重复污染**。
- **也就是说：在旧公式手续费虚高 1022 倍、NAV 结构性恒正的巨大“假绿”掩盖下，真实退出的持仓依然发生了严重亏损，风控机制在未察觉收益虚高前，仅凭真实的尾部亏损就将实盘通道完全锁死，成功避免了资金灾难。**

### 2. 有没有文件在指导「资金政策 / 仓位规模 (position sizing)」？
在 67 份文件中，有 3 份触及了资金策略与准入闸门的代码缺陷分析，但**其结论均是指出了危险漏洞，而非给出放行建议**：
1. **`AUDIT_three_uncertainties_20260909.md`（疑点三）**：
   - 审计了仓位规模计算模块 `scripts/lp_rh_size_interval_v1_readonly.py`。
   - 揭露该模块接受 `Infinity`，当输入 `q_max="Infinity"` 时返回 `q_max = Decimal('Infinity')` 且判定 `is_actionable=True`。
   - **风险揭示**：若该代码未来被用于资金政策，仓位上限将被解除，导致实盘开出无限大仓位。该报告已将此列为高危缺陷。
2. **`AUDIT_silent_failure_hunt_20260909.md`（第 3 条）**：
   - 审计了 `scripts/lp_rh_readiness_v1_readonly.py` 中的 `live_allowed` 闸门。
   - 揭露当签名、广播、密钥计数为 `None` 时，代码宽容地将其布尔化为 0，导致原本未知的状态被放行为 `live_allowed=True`。该漏洞已被当晚修复。
3. **`AUDIT_stage_a_prd_reconciliation_20260909.md`**：
   - 严格依据 PRD §21.1 核对 Stage A 准出条件，对 9 项准出标准逐条比对，给出了 **FAIL** 的阻断结论，禁止进入 Stage B 及后续 live 阶段。

### 3. 若操盘者轻信了那 9 份作废报告中的收益指标，会发生什么？
在 9 份完全作废的报告中，曾出现以下极度诱人但完全荒谬的虚假繁荣数据：
- `FULL_STRATEGY_CLEAN_PROOF_CN.md`：声称 24h 胜率 **82.85%**，平均收益 **+0.92%**，top20 收益中位数 **+4.126%**（年化超 1,500%）。
- `COHORT_PNL_PROOF_CN.md`：声称 `future_clean 24h top20 median` 达到 **+5.2899%**（单日超 5%！）。
- `CLEAN_PROOF_SURFACE_V2_CN.md`：声称 top20 p10 达到 **+3.59%**。

**操盘灾难推演**：
- 如果实盘操盘者根据这套虚假数据制定仓位规模（例如凯利公式推导出的激进头寸比例），会误以为策略单日有数个百分点的无风险套利收益。
- 但根据今晚修正后的金标实测（`reports/ECONOMICS_corrected_20260909.md`）：
  - 真实手续费年化仅 **34.09%**（单日约 0.093%），而非年化 29,076%。
  - 在仅仅 3.95 小时内，价格波动 1.085% 导致无常损失 $0.30、仓位价值缩水 $5.46，而同期真实累积手续费仅 **$0.154**！
  - 短窗口内，**未被旧代码重估的价格波动损失是手续费收入的 35~81 倍**，真实 net_pnl 为 **-$5.31**（跑输持币 $0.148）。
- **结论**：旧收益模型制造了一个“只要开仓就能稳赚年化千倍手续费”的幻觉，一旦依据该收益配置资金或放大仓位，实盘在数小时内就会被正常的市场价格波动与无常损失彻底击穿本金。

---

# 三、逐份详述（受影响与作废报告）

### 1. 完全作废的 9 份报告

#### (1) `CLEAN_PROOF_SURFACE_CN.md`
- **作废原因**：整篇文档旨在论证经过清洗后的样本呈现正向策略信号。文档表格中列出的 6h `median_net_pnl_pct=0.158153`、24h `median_net_pnl_pct=0.160851`、`top20 vs bottom20 pct_signal=better`，完全来自未做 NAV 市价重估与虚高手续费累加的修复前标线表。核心结论彻底失效。

#### (2) `CLEAN_PROOF_SURFACE_V2_CN.md`
- **作废原因**：依据排除策略生成的 v2 表现表，全表展示了各分位数净收益。24h 的 `top20 p10=3.591802` 属于天文数字级的虚高假象。策略具备显著统计 edge 的论据不成立。

#### (3) `COHORT_PNL_PROOF_CN.md`
- **作废原因**：文档横向对比 `combined_clean`、`future_clean`、`terminal_clean` 三个队列的收益分位数。其中 `future_clean` 队列完全由未重估持仓构成，其 24h `top20 median=5.289953` 严重误导。全表数据不可信。

#### (4) `FULL_STRATEGY_CLEAN_PROOF_CN.md`
- **作废原因**：全策略清洗收益证明报告。表格宣称 6h 胜率 94.28%、24h 胜率 82.85%，top20 中位数分别为 2.05% 和 4.13%。整张绩效表完全依赖旧收益公式，该策略在实盘中绝无可能达到此胜率与收益。

#### (5) `POOL_POSITION_QUARANTINE_SIM_CN.md`
- **作废原因**：在清洗数据基础上模拟剔除表现最差的 1/3/5 个仓位或池子后的收益表现。由于模拟输入的单仓收益本身就是错误的，导致剔除后的 median 与分位数全属虚构推演。

#### (6) `POSITION_LEVEL_CLEAN_PROOF_CN.md`
- **作废原因**：将 trace 聚合到 position 维度的收益证明报告。文档报告的胜率（6h: 96.88%, 24h: 90.00%）和平均收益均失真，仓位级具备稳定正收益的结论不成立。

#### (7) `POSITION_LEVEL_PROOF_V1_CN.md`
- **作废原因**：文档主体为一张 23 列的大型仓位级核算表，涵盖多种打分模式下的胜率与分位数。所有核心指标（avg_net_pnl_pct、median、win_rate、top20_median）均依赖错误公式，全表作废。

#### (8) `POSITION_LEVEL_QUARANTINE_SIM_CN.md`
- **作废原因**：仓位级隔离模拟推演报告，全表 12 组模拟场景下的 median、p10~p1 收益全部源自错误底层数据。

#### (9) `POSITION_LEVEL_QUARANTINE_V2_CN.md`
- **作废原因**：v2 仓位隔离模拟，全表列出剔除极端仓位后的胜率（80%~100%）与分位数。模拟基底彻底失真，无法提供任何策略优化参考。

---

### 2. 部分受影响的 15 份报告

#### (10) `AUDIT_stage_a_prd_reconciliation_20260909.md`
- **有效部分**：全文对 PRD §21.1 九大毕业条件的逐条核账完全有效；指出时间不足、覆盖率未达标、7 项指标未接线、合约 attestation 缺失等结论均属铁证，成功阻断了 Stage A 假毕业。
- **受影响部分**：§1 条目 3、§2 条目 3、§3 表格、§5 B.1 中记载“核心经济回放依赖的 fee_growth 仅在最近约 4 小时有值”、“有效数据仅 4 小时”。**事实是：这 4 小时内的数据在 shadow runner 中同样遭遇了 1022 倍量纲错误和 NAV 不重估，因此真实可信的经济回放数据不是 4 小时，而是 0 小时**。

#### (11) `AUDIT_hodl_scale_20260909.md`
- **有效部分**：揭露 HODL 使用固定 `1 token0 + 1 token1` 导致规模放大 2.485 倍、指出 USDG 强制等于 $1 的缺陷、揭露时间窗口未对齐，以及预警 `net_pnl` 存在手续费量纲错误。
- **受影响部分**：§2 表格中将 10 条 episode 的 `hodl_delta` 乘以 `1000/2485` 算出的缩放后数值（如合计 -15.737251）。该计算仅为机械比例缩减，未考虑 V3 实际两腿非对称分布，不得作为对账最终数字。

#### (12) `CLEAN_REMOTE_VS_DIRTY_CHECKPOINT_CN.md`
- **有效部分**：对 dirty 与 clean remote 之间的元数据信任、position_id join 修复的对比分析有效。
- **受影响部分**：Horizon metrics 表格中引用的 `pct_signal = better` 和 `reality_auditable_count` 受旧标线影响，需在重算后校正。

#### (13) `ENTRY_UNTRUSTED_EXCLUSION_IMPACT_CN.md`
- **有效部分**：证明 `entry_untrusted` 高度集中于少数特定池/仓位血缘断裂的结论有效。
- **受影响部分**：Impact Summary 表格中剔除前后的收益数值（如 top20 median pct 0.596% -> 4.255%）严重虚高，需重算。

#### (14) `TERMINAL_CLEAN_24H_WORSE_ROOT_CAUSE_CN.md`
- **有效部分**：分析 24h 表现劣于 6h 的根因在于样本极度集中（前 4 个池承载大部分样本）以及真实退出亏损的归因完全有效。
- **受影响部分**：Summary 表格中 avg (0.2036%)、median 以及 Worst Exit Reasons 中提取的字符串手续费（如 fees +78.4308, fees +24.6220）需重算。

#### (15) `TERMINAL_EXIT_PNL_AUDIT_CN.md`
- **有效部分**：退出原因分布、退出动作（shadow_close 99.8%）、标线时间距离审计有效。
- **受影响部分**：Summary 表中的 median_net_pnl_pct、p10、p90 及 Exit Reason 中记载的手续费、无常损失数字失真。

#### (16) `TERMINAL_TAIL_CLEAN_V2_CN.md`
- **有效部分**：确认剔除 zero-bug 后的样本行数统计有效。
- **受影响部分**：表格中的 median (0.007%~0.021%)、p10 (-2.37%) 等分位数值需重算。

#### (17) `TERMINAL_TAIL_CLUSTER_ATTRIBUTION_CN.md`
- **有效部分**：亏损集中度归因于少数池（0xb2cc..., 0x72ab...）与仓位（shadow-pos-c5e8...）的结构性结论有效。
- **受影响部分**：归因的具体亏损美金数额（如 $7,398, $5,827）及模拟排除后的分位数收益需重算。

#### (18) `TERMINAL_TAIL_CONCENTRATION_CN.md`
- **有效部分**：集中度指标 HHI~0.3、`judgment = concentrated_in_few_positions_or_pools` 定性有效。
- **受影响部分**：worst_position_loss_usd ($7,174) 等具体亏损金额需重算。

#### (19) `TERMINAL_TAIL_RISK_AFTER_ZERO_BUG_CN.md`
- **有效部分**：证明排除 zero-bug 后尾部风险依然显著存在的结论有效。
- **受影响部分**：Summary 表中的 p10 (-2.37%) 及 worst 50 表中的 net_pnl_pct 需重算。

#### (20) `TERMINAL_WORST_CLUSTER_AUDIT_CN.md`
- **有效部分**：最差 4 个仓位和 3 个池子的 trace 重复污染与真实退出亏损因果分析有效。
- **受影响部分**：表格中的 `net_pnl_pct`（如 -2.544%）及 `terminal_value_usd` 需重算。

#### (21) `TERMINAL_ZERO_BUG_EXCLUSION_AUDIT_CN.md`
- **有效部分**：准确识别并排除了 27 个由于 terminal_value_usd=0 导致的 -100% 异常 bug 样本。
- **受影响部分**：表格中排除后的 p10 与 median 需在收益底座修正后重新计算。

#### (22) `WORST_POOL_LIFECYCLE_DEEPDIVE_CN.md`
- **有效部分**：识别出三大劣质池（Aerodrome 0xb2cc..., Uniswap 0x6c56..., Pancake 0x72ab...）并判定为结构性风险的结论有效。
- **受影响部分**：表格中的 median_net_pnl_pct、p10、p5 需重算。

#### (23) `WORST_POSITION_LIFECYCLE_AUDIT_CN.md`
- **有效部分**：识别最差 4 个仓位及其重复 trace 污染生命周期证明的结论有效。
- **受影响部分**：表格中的 entry_value_usd、terminal_value_usd、net_pnl_pct 需重算。

#### (24) `WORST_POSITION_LIFECYCLE_DEEPDIVE_CN.md`
- **有效部分**：定性裁定 `loss_real = yes` 与 `root_cause = TRACE_DUPLICATION_ARTIFACT` 有效。
- **受影响部分**：表格中的 net_pnl_pct 需重算。

---

### 3. 不受影响的 43 份报告（一行摘要）

1. `AUDIT_duplicate_v3_inventory_20260909.md`：数学公式与规范实现推导，已在代码层严格对账，不受影响。
2. `AUDIT_gas_stagea_20260909.md`：基于链上 RPC Gas 观测值与时间戳分析，不受收益公式影响。
3. `AUDIT_silent_failure_hunt_20260909.md`：Python 代码静默假绿逻辑审计，不受影响。
4. `AUDIT_silent_failure_hunt2_20260909.md`：多链与默认值边界代码审计，不受影响。
5. `AUDIT_three_uncertainties_20260909.md`：覆盖率相加、V4 合成碰撞、Infinity 漏洞审计，不受影响。
6. `CLEAN_REMOTE_REPAIRED_V2_READINESS_CN.md`：环境 DSN、RPC 与 Go 单测就绪状态，不受影响。
7. `CURRENT_FULL_STRATEGY_FAIL_FREEZE_CN.md`：策略冻结与 Canary 禁用行政裁决，不受影响。
8. `DECISION_TRACE_DUPLICATION_AUDIT_CN.md`：纯采样重叠率（750:1）统计，不受影响。
9. `ECONOMICS_corrected_20260909.md`：今晚建立的纠偏黄金基准存档，不受影响。
10. `ENTRY_UNTRUSTED_ROOT_CAUSE_CN.md`：SQL 连接外键与血缘缺失归因，不受影响。
11. `ENTRY_UNTRUSTED_TOP20_DEEPDIVE_CN.md`：缺失 position_id 的结构性分类分析，不受影响。
12. `FINAL_VERDICT.json`：总终审裁定 FAIL 与禁止 Canary，否决有效，不受影响。
13. `FIXED_HORIZON_COUNTERFACTUAL_CN.md`：假说边界划分与未获证明裁定，不受影响。
14. `GATE_CONCLUSION_CN.md`：闸门否决结论与禁止 Canary 禁令，不受影响。
15. `GATE_SQL_CONSISTENCY_AUDIT_CN.md`：报表 SQL 跨表行数一致性审计，不受影响。
16. `NEXT_ACTION_DECISION_CN.md`：行动决策 FAIL 与维持 OOS 采集，不受影响。
17. `OVERNIGHT_CONTROL_STATE_CN.md`：进程与系统状态快照，不受影响。
18. `OVERNIGHT_FINAL_VERDICT_CN.md`：隔夜终审裁决 FAIL，不受影响。
19. `POSITION_LIFECYCLE_MATERIALIZATION_CN.md`：物化写入 68 行记录，不受影响。
20. `POSITION_MARK_GAP_CAUSAL_AUDIT_CN.md`：退出时间早于目标时间的生命周期分析，不受影响。
21. `POSITION_MARK_REALITY_AUDIT_CN.md`：时间窗口过窄的结构性归因，不受影响。
22. `POSITION_MARK_REPAIR_PLAN_CN.md`：独立研究表结构 DDL 设计，不受影响。
23. `PROOF_EXCLUSION_POLICY_CN.md`：污染样本排除规范，不受影响。
24. `PROOF_SURFACE_POLICY_CN.md`：证据分级与 Canary 强行锁定规范，不受影响。
25. `RECENT_MARK_GAP_CAUSAL_CN.md`：近期标线缺失因果分类，不受影响。
26. `RECENT_OOS_POSITION_LEVEL_PROOF_CN.md`：样本量不足判定，不受影响。
27. `RECENT_POSITION_MARK_COVERAGE_CN.md`：标线时间覆盖率百分比，不受影响。
28. `REPAIRED_V2_SCHEMA_CHECK_CN.md`：Postgres 表与 Goose 版本检查，不受影响。
29. `REVIEW_tonight_fixes_20260909.md`：今晚修复代码审查报告，不受影响。
30. `SHADOW_TERMINAL_POSITION_MARKS_REPAIRED_V1_CN.md`：研究层模式设计规范，不受影响。
31. `SHADOW_TERMINAL_POSITION_MARKS_REPAIRED_V1_MATERIALIZATION_CN.md`：物化处理时间与行数统计，不受影响。
32. `STRATEGY_BOUNDARY_FINAL_CN.md`：策略不可行边界裁定，不受影响。
33. `STRATEGY_HYPOTHESIS_SPLIT_CN.md`：全策略与假说隔离定义，不受影响。
34. `STRATEGY_PROOF_BOUNDARY_CN.md`：策略未获证明与禁用 Canary 裁定，不受影响。
35. `SYNC_RECOVERY_ARTIFACT_INDEX.md`：归档索引与安全核查，不受影响。
36. `TERMINAL_CLEAN_SQL_DIAG_CN.md`：SQL 字段存在性与数据字典，不受影响。
37. `TERMINAL_INCLUSIVE_RESIDUAL_AUDIT_CN.md`：非严格有效行数统计，不受影响。
38. `TERMINAL_LINEAGE_JOIN_AUDIT_CN.md`：发现 id 与 trace_id 混淆缺陷，不受影响。
39. `TERMINAL_MATERIALIZER_FEASIBILITY_CN.md`：物化数据源可行性研究，不受影响。
40. `TERMINAL_NEAR_EXIT_MARK_AUDIT_CN.md`：标线与退出时间绝对时间差分析，不受影响。
41. `TERMINAL_NEGATIVE_TAIL_AUDIT_CN.md`：定位 zero-bug 的错误归因报告，不受影响。
42. `TERMINAL_OUTCOME_AVAILABILITY_CN.md`：退出字段完备率统计，不受影响。
43. `TERMINAL_POSITION_MARK_SOURCE_AUDIT_CN.md`：标线来源分类统计，不受影响。

---

# 四、建议处置（按优先级）

### P0（最高优先级，立即执行）：全面冻结基于旧收益模型的讨论与引用
1. **显式标记作废**：主脑应在索引或元数据中，将上述 9 份“完全作废”报告明确标记为 `DEPRECATED_STALE_ECONOMICS`。严禁任何后续决策、交接文档或策略讨论引用其中的胜率（82%~94%）和超额收益（0.9%~5.2%）。
2. **锁死实盘通道**：确认现有的所有 `tiny_canary_allowed = no`、`edge_proven = no`、`status = FAIL` 保持严格生效。即使未来数据清洗完成，若未经过新版金标经济模型的重新核算，绝不允许翻转为 `yes`。
3. **隔离 `rh_shadow_episodes` 历史表**：`reports/lp_rh/shadow.db` 中的 87 条历史 episode 数据全部包含量纲错误与未重估缺陷，应重命名为 `rh_shadow_episodes_legacy_corrupt` 或新增 `is_repaired = false` 字段，防止新脚本再次读入该表进行错误统计。

### P1（关键工程任务）：在修复代码合并后，重放纯净经济回测
1. **等待 RH-02al（完整经济模型接线）就绪**：
   - 确保 `inventory_for_position` 计算实际两腿与 liquidity；
   - 确保 `compute_nav` 实施每步市价重估（NAV 必须包含价格变动带来的 LP 资产贬值与无常损失）；
   - 确保 `hodl_benchmark` 严格使用相同初始两腿、相同资金规模、相同起止时间戳；
   - 确保 token1 USD 价格具备链上时点证据，禁止全局 fallback 到 $1。
2. **对 15 份部分受影响的报告实施数据重算**：
   - 重点重算 `TERMINAL_EXIT_PNL_AUDIT_CN.md`、`TERMINAL_TAIL_RISK_AFTER_ZERO_BUG_CN.md`、`TERMINAL_WORST_CLUSTER_AUDIT_CN.md` 中的实际盈亏与回撤数值。

### P2（数据沉淀）： Stage A 真实数据累积
1. **重新校准 Stage A 经济数据时长**：
   - 明确 Stage A 目前的 40 小时仅为采样链路的存活与覆盖时间，真实的有效经济费率数据截至 2026-09-09 20:03 UTC 仅有 **3.95 小时**。
   - 必须在修复后的代码守护下，重新稳定运行累积至少 72 小时的完整费率与价格序列，方可对该池是否具备手续费 Alpha 做出初审结论。
