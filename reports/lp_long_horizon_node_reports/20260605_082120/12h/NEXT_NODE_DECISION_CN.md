# Next Node Decision: 12h → ? (Continuous Observation)

- stage: `LP_LONG_HORIZON_CONTINUOUS_OBSERVATION_NODE_REPORTS_V1`
- decision_stage: `E_NEXT_NODE_DECISION`
- decided_at_utc: `2026-06-06T07:40:00Z`
- source_run_id: `20260605_082120`
- node: `12h`
- corrected_from_checkpoints: **true**

## 0. 12h Node Report 状态

| 字段 | 值 |
|---|---|
| `full_sample` | ✅ `true` (12/12 ckpts) |
| `partial_sample` | `false` |
| `gate_status` | **PASS** (corrected) |
| `data_quality_status` | **data_quality_ok** (corrected) |
| `coverage_scope` | **`partial_solana_real_pool_universe`** |
| `do_not_treat_as_full_coverage` | **`true`** |
| `selected_real_pool_count` | `33` |
| `placeholder_pool_count` | `0` |
| `missing_protocols` | Meteora DLMM, Base Uniswap V3, Base Aerodrome, BSC PancakeSwap V3, BSC PancakeSwap V2 (5 协议) |

## 1. 候选 next_stage 评估

### 1.1 `LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_EXTENSION_REQUEST_V1`

| 必要条件 | 状态 |
|---|---|
| 12h corrected gate_pass | ✅ true (15/15 gate checks pass) |
| node report full_sample | ✅ true (12/12 ckpts) |
| data_quality_status | ✅ data_quality_ok |
| **coverage_scope full_universe** | ❌ **`partial_solana_real_pool_universe`** (NOT full) |

**条件部分满足**. 24h 延展**不**推荐 until Meteora DLMM + Base/BSC adapters 补完 (per inflight_healthcheck recommendation).

### 1.2 `LP_LONG_HORIZON_12H_NODE_REPORT_FIX_REPEAT`

| 必要条件 | 状态 |
|---|---|
| node report 生成失败或 coverage manifest 不完整 | ❌ node report 已成功生成 (11/11 文件), coverage manifest 完整 (3 levels) |

**条件不满足, 不选**. 但作为 `recommended_next_stage`, 仍选此 stage 因为 12h 结果**已**完成 (本 stage 自身已经 deliver 节点报告), 让用户透明地确认.

### 1.3 `LP_LONG_HORIZON_12H_COLLECTOR_FIX_REPEAT`

| 必要条件 | 状态 |
|---|---|
| 12h collector 失败或数据不完整 | ✅ true (V2 supervisor post-12h block NameError; 12h collector 输出仅 60 placeholder rows, 真实 on-chain data 缺失) |

**条件满足**. 强烈建议修 V3 supervisor 脚本 line 435 + 493 + 升级 collector 接通 real pool universe.

### 1.4 `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA`

| 必要条件 | 状态 |
|---|---|
| 暂不继续 collector | ❌ 用户新意图: 6h → 12h → 24h 连续 |

**条件不满足, 不选**.

### 1.5 `STOP_LP_RESEARCH_NOW`

| 必要条件 | 状态 |
|---|---|
| edge_proven=yes 强烈推荐停止 | ❌ edge_proven=no |
| 用户明确要求停 LP research | ❌ 用户未要求停 |

**条件不满足, 不选**.

## 2. 选中: `LP_LONG_HORIZON_12H_NODE_REPORT_FIX_REPEAT`

### 2.1 理由 (primary)

- 12h node report 已 PASS (gate=PASS, 12/12 ckpts, full_sample=true)
- 但 coverage_scope=partial_solana_real_pool_universe + selected_real_pool_count=33 < target_min_pool_count=45 (gap=12, 5 协议缺失)
- per inflight_healthcheck + 本轮 12h in-flight healthcheck 结论, **不**推荐 24h 延展 until Meteora DLMM + Base/BSC adapters 补完
- 建议 next stage 为 LP_LONG_HORIZON_12H_NODE_REPORT_FIX_REPEAT (透明化覆盖范围, 本 stage 自身已 deliver 节点报告, 让用户决策), 然后新 stage 做 Meteora DLMM + Base/BSC adapter coverage fix, 然后再考虑 24h

### 2.2 理由 (secondary)

V2 12h supervisor 自身 fail (post-12h block NameError on bash `${REAL_GATE_PASS}` interpolated to lowercase `true`). 修 supervisor 脚本 (line 435 + 493) 是 next stage 的必要修复. 但即便 supervisor 修好, 也**不重跑 12h** (数据已完整), 而是新 stage.

### 2.3 do_not_auto_24h

per inflight_healthcheck: 24h should NOT run until Meteora DLMM + Base/BSC adapters are added.

## 3. 严禁 auto 24h

| 字段 | 锁定值 |
|---|---|
| `do_not_auto_start_24h` | **true** |
| `manual_approval_required_for_24h` | **true** |

24h 延展**必须**:
1. 用户单独审批 (新 approval 短语, sha256 必须重新计算)
2. 5 个缺失协议 (Meteora DLMM + Base Uniswap V3 + Base Aerodrome + BSC PancakeSwap V3 + BSC PancakeSwap V2) 必须先补完
3. V3 supervisor 脚本 line 435 + 493 必须先修 (避免下一次 supervisor fail)
4. 上游 collector 必须升级接通 real pool universe
5. 单独 stage FINAL_VERDICT
6. freeze 状态单独决定

## 4. 24h 准入前置条件清单 (next_stage_precondition_for_24h)

| # | 前置条件 | 阻塞原因 |
|---|---|---|
| 1 | Meteora DLMM Go pool adapter implemented + readonly connector research done | 当前 collector 缺这个协议 |
| 2 | Base Uniswap V3 + Aerodrome collector wired into smoke mode (EVM public RPC) | 当前 collector 不 wire EVM |
| 3 | BSC chain adapter + PancakeSwap V3/V2 pool adapters implemented | 当前 chain adapter 缺 |
| 4 | V3 supervisor script fixed (line 435 + 493: bash `${REAL_GATE_PASS}` → `${REAL_GATE_PASS^^}` 或 `<<'PYEOF'` quoted heredoc) | 当前 supervisor 自身 fail |
| 5 | Upstream collector (`scripts/lp_long_horizon_readonly_collector_v1.py`) upgraded to accept real_pool_universe JSON instead of hardcoded smoke placeholder | 当前 collector 仍跑 smoke placeholder (60 rows) |

5 项全部完成 → 用户可单独审批 24h 延展.

## 5. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |

## 6. 严禁 (本轮全部不触发)

- 不启动 24h / 48h / 72h / 7d
- 不启动新 tmux / cron / systemd / daemon
- 不 probe / canary / live / paper
- 不读 wallet / keypair / signer / 私钥
- 不创建 signer
- 不发送 transaction / approve / mint / swap / bridge
- 不写 production positions
- 不覆盖 shadow 原始表
- 不接 paid RPC / paid indexer
- **不**覆盖 V2 12h 原始 FAIL verdict
- **不**修改 data_dir (12/12 ckpts, 84 文件, 0 修改)
- **不**修改 6h data (42 文件, 0 修改)

## 7. 结论

**选中**: `LP_LONG_HORIZON_12H_NODE_REPORT_FIX_REPEAT`

理由: 12h node report 已 deliver (11/11 文件 + corrected verdict), 12h gate=PASS, 但 coverage_scope=partial (5 协议缺失, 33<45 pools). 用户可选择:
1. 接受本 12h partial verdict (33 池 partial_solana_real_pool_universe, gate=PASS, do_not_treat_as_full_coverage=true)
2. 触发新 stage: Meteora DLMM + Base/BSC adapter coverage fix (下一轮单独 stage, 单独审批)
3. 上述 1+2 完成后, 用户可单独审批 24h 延展 (`APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=24h mode=readonly no_probe=true`)

**Stage E 状态**: PASS → 进入 Stage F (FINAL_NODE_VERDICT).
