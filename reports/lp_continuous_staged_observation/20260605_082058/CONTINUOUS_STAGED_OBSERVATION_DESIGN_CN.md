# Stage C: 连续 Staged Observation 设计

- stage: `LP_CONTINUOUS_STAGED_OBSERVATION_AND_COVERAGE_REPORT_V1`
- design: `continuous_staged_observation_v1`
- designed_at_utc: `2026-06-05T08:21:30Z`
- designer: agent (只读设计)

## 0. 核心目标

让 LP 只读 collector 在不中断的前提下, 在 **6h / 12h / 24h / 48h / 72h / 7d** 节点自动生成阶段报告 (node report), 节点报告用于:

1. 让用户知道"观察了什么"
2. 评估数据质量, 决定是否继续采集
3. 透明化覆盖范围 (链 / DEX / 池)
4. 解释无探针资金时手续费估算依据
5. 展示 range / tick / bin 对手续费的影响

**节点报告 ≠ 批准实盘**. 节点报告只用于数据观察 + 是否继续采集判断.

## 1. 五条核心原则

1. **数据采集连续**: collector 不在节点之间停机, 同一 RUN_ID 全程单 supervisor 进程.
2. **节点报告自动生成**: 在 6h / 12h / 24h / 48h / 72h / 7d 节点自动调用 `scripts/lp_long_horizon_node_report_generator_v1.py`.
3. **节点报告 ≠ 批准实盘**: 节点报告只回答"数据是否可信", 不回答"是否能交易".
4. **节点 gate 只决定数据质量**: PASS / WARN_ACCEPTABLE / FAIL, 但都**不**触发任何 probe / trade.
5. **FAIL 仍可继续采集**: FAIL 节点标记 `data_quality_fail` 不可作为 preflight 依据, 但不阻止后续节点采集.

## 2. Collector 连续性规则

| ID | 规则 |
|---|---|
| R1 | 同一 RUN_ID 全程只允许 1 个 collector supervisor 进程 + 1 个 tmux tail |
| R2 | 节点之间**不** kill supervisor, **不**重启, 允许 sleep 跨节点 wallclock (e.g. 6h→12h 是同一 supervisor 内的 6h 增量 sleep) |
| R3 | collector 写入路径严格限定 `data/lp_long_horizon/<RUN_ID>/` |
| R4 | node report 写入 `reports/lp_long_horizon_node_reports/<RUN_ID>/<NODE>/` |
| R5 | 禁止 canary / live / paper / sendTransaction / keypair / wallet 进程 (零容忍) |

## 3. 节点 Gate 决策矩阵

| 节点状态 | data_quality_status | can_continue_collection | can_enter_preflight_design | can_run_probe_now | recommended_next_action |
|---|---|---|---|---|---|
| **PASS** | `data_quality_ok` | ✅ | ❌ | ❌ (locked) | `continue_collection_to_next_node` |
| **WARN_ACCEPTABLE** | `data_quality_warn` | ✅ | ❌ | ❌ (locked) | `continue_collection_with_note` |
| **FAIL** | `data_quality_fail` | ✅ (允许继续采集) | ❌ | ❌ (locked) | `continue_collection_but_mark_node_invalid_for_preflight` + raise `FIX_REPEAT` 或 `PAUSE` 决策给用户 |

**任何状态都**:
- 不得自动 probe
- 不得自动 trade
- 不得自动进入 B 线
- 不得修改 `can_run_probe_now` (locked false)
- 不得修改 `tiny_canary_allowed` (locked "no")

## 4. Node Report 生命周期

| 阶段 | 描述 |
|---|---|
| **trigger** | supervisor 在 wallclock 跨过 6h/12h/24h/48h/72h/7d 节点时, 调用 `scripts/lp_long_horizon_node_report_generator_v1.py` |
| **input** | `data/lp_long_horizon/<RUN_ID>/` (从 T0 到当前 node 累计的 checkpoints + smoke_summary + 实际 fee placeholder) |
| **output** | `reports/lp_long_horizon_node_reports/<RUN_ID>/<NODE>/` (7 文件: NODE_REPORT_CN.md, NODE_REPORT.json, POOL_UNIVERSE_COVERAGE_MANIFEST.csv/json, FEE_ESTIMATION_BASIS_CN.md/json, RANGE_LIQUIDITY_FEE_SENSITIVITY.csv/json, CANDIDATE_REVIEW.csv/json, FINAL_NODE_VERDICT.json) |
| **side_effect** | 无 (read-only + write-only-to-its-own-output-dir) |
| **auto_commit** | 节点报告生成后, supervisor 自动 git add + commit (per `research: node report {NODE} for {RUN_ID}`), 推到 origin |
| **auto_advance** | 节点报告生成后, supervisor 继续运行 (sleep 下一个节点的 wallclock), 触发下一个节点报告 |

## 5. A 线 ↔ B 线 分离规则

| 维度 | A 线 (本轮) | B 线 (下一轮, 单独安排) |
|---|---|---|
| 内容 | 连续观察 + 节点报告 + 覆盖范围透明化 | 自动组/拆 LP disabled build |
| 触发 | 用户审批"本轮设计" | 用户单独审批 (R4 preflight + R5 manual probe only) |
| 执行依据 | scope_audit R0 (long readonly data) | scope_audit R1-R5 (real fee accrual / market regime / candidate review / 10U tokenId probe preflight / manual probe only) |
| 自动执行 | ❌ 不得自动 probe / trade | ❌ 仍需手动 probe (R5) |
| 节点报告价值 | 数据质量判断 + 是否继续采集 | 可作为 preflight 输入, 但**仍**需用户单独审批 |

**A 线节点报告即使全部 PASS, 也不得自动触发 B 线**. B 线需要:
- 用户单独 APPROVE 短语
- 单独审批记录
- 单独 stage FINAL_VERDICT
- 单独 frozen 状态 unfreeze 决策

## 6. 与 V2 6h Supervisor 的兼容性

- V2 6h supervisor 当前在 6h 节点自动 finalize + auto commit + auto push
- 本轮设计**不**修改 V2 supervisor, 节点报告生成器是独立工具
- 任何 supervisor (包括 V2 6h 完成后) 可独立调用 `node_report_generator_v1.py`
- V2 6h 完成后, 用户可手动调用 `python3 scripts/lp_long_horizon_node_report_generator_v1.py --run-id 20260605_043726 --node 6h` 生成 V2 的 6h 节点报告 (本轮**不**预写, 留给 V2 自然 finalize 后用户触发)
- 未来 supervisor (本轮**不**创建) 可在 12h / 24h / 48h / 72h / 7d 节点自动调用 node report generator

## 7. 设计约束 (硬性)

| ID | 约束 |
|---|---|
| C1 | 无 probe / canary / live / paper |
| C2 | 无 wallet / keypair / signer |
| C3 | 无 transaction / approve / mint / swap / bridge |
| C4 | 无 paid RPC / paid indexer |
| C5 | 无 production write |
| C6 | 无 shadow overwrite |
| C7 | 无 cron / systemd / daemon |
| C8 | LP strategy research freeze 不解锁 (per `docs/LPBOT_RESEARCH_STATUS_CN.md`) |
| C9 | `can_run_probe_now = false` (locked) |
| C10 | `tiny_canary_allowed = "no"` (locked) |
| C11 | `edge_proven = "no"` (locked) |
| C12 | 不修改 V2 supervisor |
| C13 | 不修改 V2 collector |
| C14 | 不修改 V2 data |

## 8. 开放问题 (留待后续)

- Q1: 节点报告生成器由谁调用? → 设计: 任何 supervisor 或用户手动, 独立工具
- Q2: 节点报告触发点是 wallclock 还是 RPC count? → 设计: wallclock, 简化
- Q3: node report generator 写报告后是否需要 auto commit? → 设计: 可选, supervisor 决定; 独立调用时由用户决定
- Q4: 节点 gate FAIL 时是否要 raise FIX_REPEAT 或 PAUSE 决策? → 设计: 在 recommended_next_action 中显式 raise, 但**不**自动执行, 由用户决定

## 9. 结论

连续 staged observation 设计完成. 关键:
- collector 连续运行 (单 supervisor)
- 节点报告自动生成 (本轮设计 + 工具)
- 节点 gate 只决定数据质量, 不得自动 probe / trade
- A 线 / B 线 严格分离, 节点报告**不**作为实盘批准依据

**Stage C PASS** → 进入 Stage D (节点报告 schema).
