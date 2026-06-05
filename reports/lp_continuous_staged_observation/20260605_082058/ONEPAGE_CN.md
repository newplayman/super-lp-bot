# LP Continuous Staged Observation and Coverage Report V1 — One Page

- stage: `LP_CONTINUOUS_STAGED_OBSERVATION_AND_COVERAGE_REPORT_V1`
- run_id: `20260605_082058`
- branch: `feat/supabase-postgres-deployment`
- head_before: `95efae6`
- status: **PASS**

## 0. 核心结论

✅ **PASS** — 本轮交付连续 staged observation 全部设计 + 工具 + 样例, A 线 (continuous observation) 严格不触 B 线 (execution), V2 在轨保护完整, 无任何 probe / canary / live / paper / wallet / tx 触发.

## 1. V2 在轨保护

- V2 6h supervisor PID 3872268 alive, ELAPSED 3h+
- 4/6 checkpoints 已写, expected end 2026-06-05T10:51:29Z
- 启动以来无任何 V2 文件被本轮触碰
- 启动以来无任何 V2 进程被 kill / restart / parallel

## 2. 本轮交付物 (11 个 spec + 1 个工具 + 1 个 sample)

| 类别 | 路径 | 状态 |
|---|---|---|
| V2 保护审计 | `CURRENT_V2_PROTECTION_AUDIT_CN.md` / `.json` | ✅ |
| 输入证据审计 | `INPUT_EVIDENCE_AUDIT_CN.md` / `.json` | ✅ |
| Continuous Staged Observation Design | `CONTINUOUS_STAGED_OBSERVATION_DESIGN_CN.md` / `.json` | ✅ |
| Node Report Schema | `NODE_REPORT_SCHEMA_CN.md` / `.json` | ✅ |
| Pool Universe Coverage Manifest Spec | `POOL_UNIVERSE_COVERAGE_MANIFEST_SPEC_CN.md` / `.json` | ✅ |
| Fee Estimation Without Probe | `FEE_ESTIMATION_WITHOUT_PROBE_CN.md` / `.json` | ✅ |
| Range / Liquidity / Fee Sensitivity Spec | `RANGE_LIQUIDITY_FEE_SENSITIVITY_SPEC_CN.md` / `.json` | ✅ |
| Next-Stage Decision | `CONTINUOUS_OBSERVATION_NEXT_STAGE_DECISION_CN.md` / `.json` | ✅ |
| Node Report Generator v1 | `scripts/lp_long_horizon_node_report_generator_v1.py` | ✅ |
| Sample 6h node report | `reports/lp_long_horizon_node_reports/20260605_043726/6h/` (WARN_ACCEPTABLE, partial_sample) | ✅ |
| Final Verdict + this OnePage + ARTIFACT_INDEX | `FINAL_VERDICT.json` / `ONEPAGE_CN.md` / `ARTIFACT_INDEX.md` | ✅ |

## 3. 关键设计原则 (5 条)

1. **数据采集连续**: collector 不在节点之间停机, 同一 RUN_ID 全程单 supervisor
2. **节点报告自动**: 在 6h/12h/24h/48h/72h/7d 节点自动生成阶段报告
3. **节点报告 ≠ 批准实盘**: 节点报告只回答"数据是否可信", 不回答"是否能交易"
4. **节点 gate 只决定数据质量**: PASS / WARN_ACCEPTABLE / FAIL, 都不触发 probe / trade
5. **FAIL 仍可继续采集**: FAIL 节点标记 `data_quality_fail` 不可作为 preflight 依据, 但不阻止后续节点采集

## 4. Node Report Schema (21 top-level fields)

- `node_stage` / `run_id` / `generated_at_utc` / `node_window_*_utc`
- `runtime_minutes` / `expected_runtime_minutes` / `runtime_within_tolerance`
- `short_mode_used` (always false) / `collection_continuity` / `single_supervisor`
- `coverage` (chain/dex/pool 三层) / `row_count_block` / `market_regime_block`
- `candidate_block` (best + rejected) / `fee_estimation_block` / `range_sensitivity_block`
- `data_quality_block` / `gate_block` / `recommended_next_action_block`

**Forbidden top-level keys** (任何出现 = schema invalid + exit 8): `tx_hash`, `wallet_address`, `private_key`, `keypair`, `mnemonic`, `seed`, `signed_transaction`.

## 5. 覆盖范围透明化 (7 chains × 10 protocols)

**observed=true**: Base Uniswap V3, Base Aerodrome, Solana Raydium CLMM, Solana Orca Whirlpool, Solana PancakeSwap V3

**observed=false** (honest disclosure):

- Solana Meteora DLMM (`not_implemented_yet`)
- Solana Raydium CPMM (`not_implemented_yet`)
- Solana Raydium AMM v4 (`not_implemented_yet`)
- BSC PancakeSwap V3 (`bsc_chain_adapter_not_implemented_yet`)
- BSC PancakeSwap V2 (`bsc_chain_adapter_not_implemented_yet`)
- Ethereum / Arbitrum / Optimism / Polygon (`chain_skipped_for_safety_mainnet_only_design_target`)

## 6. Fee Estimation (R0 proxy, no actual fee)

**R0 locked fields** (在所有 fee_estimation_block 强制):

- `actual_fee_data_available: false`
- `fee_proxy_used: true`
- `heuristic_used: true`
- `fee_estimate_confidence: "low"`

**5 pool type 公式**: V3/CLMM (narrow/medium/wide range × in_range_time_ratio) + Meteora DLMM (narrow/medium/wide bin coverage) + CPMM (full range × lp_share) + Stable / LST-Stable (low IL + depeg risk adjustment)

**R0 → R1 升级路径** (7 个必要数据点): `tokenId`, `entry/exit feeGrowthGlobal`, `tokensOwed`, `collected fee (USD)`, `actual add/remove cost (USD)`, `realized PnL`. 任何缺失 = 仍为 proxy.

## 7. Sample Node Report (6h partial_sample)

- `reports/lp_long_horizon_node_reports/20260605_043726/6h/`
- `gate_status: WARN_ACCEPTABLE` (4/6 ckpts, 67% complete)
- `best_candidate_count: 0` (placeholder rows have all 3 ready=false)
- `rejected_candidate_count: 20` (no_quote_ready / no_fee_ready / no_ev_ready)
- `partial_sample: true` (V2 6h supervisor 跑满 6h 后用户触发本 generator 可生成 full_sample)

## 8. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |

## 9. Recommended Next Stage

**`LP_LONG_HORIZON_CONTINUOUS_OBSERVATION_NODE_REPORTS_V1`**

(用户 pivot 2 后: continuous observation, 不在每个节点停机, 节点报告只用于数据观察 + 是否继续采集判断)

**严禁** (forbidden next stages):

- `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_APPROVAL_V1` (V2 in-flight, 已执行)
- `LP_LONG_HORIZON_READONLY_COLLECTOR_12H_RUN_APPROVAL_V1` (未批准)
- `LP_LONG_HORIZON_READONLY_COLLECTOR_24H_RUN_APPROVAL_V1` (未批准)
- 任何 probe / canary / live / paper / wallet / keypair stage

## 10. 安全检查

```
ps aux | egrep 'canary|lpbot-live|live|paper|sendTransaction|eth_sendRawTransaction|eth_sendTransaction|keypair' | grep -v grep
→ (空) ✅ 无禁止进程
```

```
tmux ls 2>/dev/null | grep -E "lp_long_horizon_6h_v2_20260605_043726|staged_observation"
→ lp_long_horizon_6h_v2_20260605_043726 (V2, created Fri Jun 5 06:51:15 2026)
→ (无 staged_observation session)
✅ 本轮未启动任何新 tmux
```

## 11. 后续行动 (用户可手动触发)

```
# V2 6h 完成后 (预计 2026-06-05T10:51:29Z)
python3 scripts/lp_long_horizon_node_report_generator_v1.py \
  --run-id 20260605_043726 \
  --node 6h
# → 生成 full_sample=true 6h node report

# 后续节点需要新 supervisor (本轮未创建, 下一轮单独安排)
```

## 12. 结论

✅ 本轮 A→J 全部 PASS. V2 在轨保护完整. 连续 staged observation 工具链 ready. Sample 6h partial_sample node report 成功生成. 节点报告**不**作为 B 线 preflight 依据, 严格 A/B 分离. 锁定字段全部保持, 严禁任何 probe / canary / live / paper / wallet / tx 行为.
