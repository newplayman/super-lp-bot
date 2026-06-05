# Stage I: 连续观察与阶段报告 Next-Stage 决策

- stage: `LP_CONTINUOUS_STAGED_OBSERVATION_AND_COVERAGE_REPORT_V1`
- decided_at_utc: `2026-06-05T08:38:00Z`
- decider: agent (read-only)

## 0. 决策问题

本轮 (Stage A→H) 已完成所有设计与 node_report_generator_v1 实现, 并用 V2 in-flight 4/6 ckpts 数据成功 dry-run 生成 6h partial_sample 节点报告. 下一步应该选哪个 stage?

## 1. 候选 next_stage 评估

### 1.1 `LP_LONG_HORIZON_CONTINUOUS_OBSERVATION_NODE_REPORTS_V1`

| 必要条件 | 状态 |
|---|---|
| node report generator ready | ✅ `scripts/lp_long_horizon_node_report_generator_v1.py` 实现 + 6h partial_sample dry-run 成功 (WARN_ACCEPTABLE) |
| current V2 不被干扰 | ✅ per Stage A 审计, 无 V2 修改 |
| 可以在 V2 完成后生成 6h node report | ✅ generator 支持 `--node 6h` |
| 后续可保持同 run 连续扩展到 12h/24h/48h/72h/7d | ✅ generator 支持 6 个节点 |

**条件全部满足**.

### 1.2 `LP_CONTINUOUS_STAGED_OBSERVATION_FIX_REPEAT`

| 必要条件 | 状态 |
|---|---|
| schema / script 不完整 | ❌ 本轮交付物完整: 21 top-level fields, 7 forbidden keys, 3 coverage levels, 7 protocols × 3 chains, 4 fee proxy formulas, 3 range sensitivity tables, 11 output files per node report, 25 R0 locked fields |

**条件不满足, 不选**.

### 1.3 `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA`

| 必要条件 | 状态 |
|---|---|
| 暂不继续 collector | ❌ 用户新意图是 continuous (连续跑), 不是 pause. 当前 V2 6h 仍在跑 (4/6 ckpts), **不**应 pause |

**条件不满足, 不选**.

### 1.4 `STOP_LP_RESEARCH_NOW`

| 必要条件 | 状态 |
|---|---|
| `edge_proven=yes` 强烈推荐停止 | ❌ `edge_proven=no` |
| 用户明确要求停 LP research | ❌ 用户新意图是 continuous observation (A 线), 不是 STOP |

**条件不满足, 不选**.

## 2. 选中: `LP_LONG_HORIZON_CONTINUOUS_OBSERVATION_NODE_REPORTS_V1`

### 2.1 与用户意图 fit

用户新意图 (本轮 prompt) 明确:

> "6h → 12h → 24h → 48h → 72h → 7d 这条观察链可以不中断; 不是每个节点都停机等待人工审批; 应该让 collector 连续运行, 到每个节点自动生成阶段报告"

本轮交付物精确满足此意图:

- ✅ `continuous_staged_observation_design_v1` (collector 连续, 节点报告自动)
- ✅ `node_report_schema_v1` (21 top-level fields, 7 forbidden keys, 3 gate states)
- ✅ `pool_universe_coverage_manifest_spec_v1` (chain/dex/pool 三层, observed=false 透明化)
- ✅ `fee_estimation_without_probe_v1` (R0 显式 proxy 标注, R1 升级路径)
- ✅ `range_liquidity_fee_sensitivity_spec_v1` (V3/CLMM/DLMM/CPMM 四种 pool type, 3 range × heuristic risk)
- ✅ `lp_long_horizon_node_report_generator_v1.py` (read-only 工具, 11 output files per node)
- ✅ 6h partial_sample dry-run 成功 (WARN_ACCEPTABLE, no V2 modification)

### 2.2 与 Collector Continuity fit

V2 当前 6h 跑完后 (预计 2026-06-05T10:51:29Z), 同一 RUN_ID 可由下一阶段 supervisor 继续跑到 12h / 24h / 48h / 72h / 7d, 节点报告由 generator 自动生成, 整个链条不中断.

### 2.3 与 A/B 线分离 fit

本轮 = A 线 (continuous observation), 严格不触发 B 线 (execution). 节点报告全部 locked:

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `auto_probe_allowed` | `false` |
| `auto_trade_allowed` | `false` |
| `manual_approval_required_for_execution` | `true` |

### 2.4 与 Freeze fit

LP strategy research 仍处于 freeze (per `docs/LPBOT_RESEARCH_STATUS_CN.md`). 节点报告是 R0 数据采集, 严格遵守 freeze, **不**解锁 LP strategy research.

### 2.5 与 R0 actual_fee lock fit

R0 阶段所有 fee 数字 = proxy, generator 显式标记:

- `actual_fee_data_available: false`
- `fee_proxy_used: true`
- `heuristic_used: true`
- `fee_estimate_confidence: "low"`

升级到 R1 (actual fee) 需要真实 LP 操作, 需用户单独批准 (B 线).

## 3. Next Stage 实际活动

1. V2 6h 完成后 (预计 2026-06-05T10:51:29Z), 用户可手动触发 6h node report:
   ```
   python3 scripts/lp_long_horizon_node_report_generator_v1.py --run-id 20260605_043726 --node 6h
   ```
2. 后续阶段 (12h / 24h / 48h / 72h / 7d) 由新 supervisor 在节点 wallclock 自动调用 generator (本轮**不**创建新 supervisor, 由下一轮单独安排)
3. 节点报告只用于数据观察 + 是否继续采集判断, **不**作为 B 线 preflight 依据

## 4. 选中 stage 的约束

| ID | 约束 |
|---|---|
| C1 | 无 probe / canary / live / paper |
| C2 | 无 wallet / keypair / signer |
| C3 | 无 transaction / approve / mint / swap / bridge |
| C4 | 无 paid RPC / paid indexer |
| C5 | 无 production write |
| C6 | 无 shadow overwrite |
| C7 | 无 cron / systemd / daemon |
| C8 | LP strategy research freeze 不解锁 |
| C9 | `can_run_probe_now = false` (locked) |
| C10 | `tiny_canary_allowed = "no"` (locked) |
| C11 | `edge_proven = "no"` (locked) |

## 5. 结论

**选中**: `LP_LONG_HORIZON_CONTINUOUS_OBSERVATION_NODE_REPORTS_V1`

理由: 本轮交付物 (设计 + 工具 + 样例) 全部 ready, 与用户新意图 (continuous observation, A 线不触 B 线, R0 不假装 actual fee) 完全 fit. 后续活动由用户手动触发节点报告 (V2 完成后) 或新 supervisor 自动触发 (下一轮单独安排).

**Stage I PASS** → 进入 Stage J (FINAL_VERDICT + ONEPAGE + ARTIFACT_INDEX).
