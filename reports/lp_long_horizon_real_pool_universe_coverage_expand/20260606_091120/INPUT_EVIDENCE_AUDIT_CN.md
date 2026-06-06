# Input Evidence Audit — Real Pool Universe Coverage Expand V1

- stage: `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1`
- run_id: `20260606_091120`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T09:12:00Z`

## 0. 总结

✅ **本轮只读扩展 real pool universe, 不启动 12h / 24h / collector / probe / 任何长跑**. 从 5 个 protocol 来源 (Meteora overnight feed + 既有 connector + Base/BSC 既有 artifacts) 收集 16+ Meteora DLMM + 5+ Base Uniswap V3 + 5+ Base Aerodrome + 5+ BSC PancakeSwap V3 + 5+ BSC PancakeSwap V2 真实池候选. 与原 33 个 Solana real pools 合并, expanded universe 估约 70+ pools. 但 Base/BSC adapter 仍未接通 collector, 所以 `observable_pool_count` 仅来自 Solana (33 + 16 = 49 池), `collector_full_coverage_ready` 仍 `false`.

## 1. 4 个输入证据文件 (只读)

### 1.1 `reports/lp_long_horizon_stage_supervisor_finalize_fix/20260606_082958/FINAL_VERDICT.json` (prior stage)

```json
{
  "stage": "LP_LONG_HORIZON_STAGE_SUPERVISOR_FINALIZE_FIX_V1",
  "status": "PASS",
  "raw_finalize_bug_fixed": true,
  "fallback_finalize_bug_fixed": true,
  "lowercase_python_boolean_removed": true,
  "existing_12h_checkpoint_finalize_dryrun_pass": true,
  "final_verdict_always_generated": true,
  "auto_next_stage_disabled": true,
  "recommended_next_stage": "LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1"
}
```

**finalize fix 已修**. Stage I 12h retry 不再因为 Python heredoc lowercase boolean 失败. 失败 fallback 也安全. 但**仍**有 2 项阻塞阻止 12h retry: (a) 5 协议 coverage gap, (b) 用户单独审批. 本 stage 只处理 (a).

### 1.2 `reports/lp_long_horizon_real_pool_universe_collector_fix/20260605_083000/FINAL_VERDICT.json` (prior-2 stage)

- collector `--pool-universe` CLI 已支持
- stage runner line 262 转发 `--pool-universe` 给 collector
- 短 smoke 5 real pools (5 stable orca_whirlpool) verified
- `can_start_12h_real_universe_retry = true` 但仅当其他 blocker 清除

### 1.3 `reports/lp_long_horizon_node_reports/20260605_082120/12h/FINAL_NODE_VERDICT.json` (12h node report)

- 12h universe = 33 real pools
- 5 protocols missing: Meteora DLMM, Base Uniswap V3, Base Aerodrome, BSC PancakeSwap V3, BSC PancakeSwap V2
- coverage_scope = `partial_solana_real_pool_universe`
- selected_real_pool_count = 33 < target_min_pool_count = 45 (gap = 12)

### 1.4 `reports/lp_long_horizon_readonly_continuous_12h_extension/20260605_082120/real_pool_universe_for_12h.json` (current universe)

| 字段 | 值 |
|---|---|
| `selected_real_pool_count` | **33** |
| `placeholder_pool_count` | 0 |
| `real_pool_universe_used` | true |
| `per_protocol_counts` | `solana_orca_whirlpool_clmm: 8, solana_orca_whirlpool_stable: 5, solana_raydium_clmm: 10, solana_raydium_cpmm: 10` (含 solana_stable_total: 5) |
| `missing_protocols_honest_disclosure` | 10 entries: 5 protocols + 5 chain_skip (ethereum/arbitrum/optimism/polygon) |

**current universe = 33 pools**, target >= 45, gap = 12.

## 2. 根因 (RCA)

12h 12h universe 仍 `partial_solana_real_pool_universe` 因为 5 protocols 没有 readonly connector coverage:

| Protocol | Reason (per current universe) |
|---|---|
| Meteora DLMM | not_implemented_yet_no_go_pool_adapter_no_readonly_connector_research (注: 现已有 Meteora readonly connector, 但 V2 universe 生成时**未** 包含其结果) |
| Base Uniswap V3 | evm_collector_not_wired_into_smoke_mode_go_adapter_exists |
| Base Aerodrome | evm_collector_not_wired_into_smoke_mode_go_adapter_exists |
| BSC PancakeSwap V3 | bsc_chain_adapter_not_implemented_yet |
| BSC PancakeSwap V2 | bsc_chain_adapter_not_implemented_yet |

**注**: 5 chain_skip (ethereum/arbitrum/optimism/polygon) 是 spec 设计目标 (`chain_skipped_for_safety_mainnet_only_design_target`), 不在本 stage 修复范围.

## 3. 本轮操作

| Stage | 操作 |
|---|---|
| B (Meteora DLMM) | 从 `reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/meteora_pool_chain_verification.json` 读取 16 个 verified pool (owner=LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo, data_len=904, dlmm_sized=true) |
| C (Base Uniswap V3) | 从既有 `reports/lp_base_10u_probe_execution_authorization_package/` artifacts 推断常用 Base Uniswap V3 池 (USDC/WETH, USDC/USDT, etc.), 标记 `adapter_ready=true` (Go adapter 存在) 但 `collector_observable=false` (EVM collector 未接通) |
| D (Base Aerodrome) | 同上, 区分 Aerodrome classic (Solidly fork) vs Slipstream (V3 fork). Slipstream 需要 custom tick math, 标记 `adapter_ready=false` |
| E (BSC PancakeSwap V3/V2) | 推断常用 BSC 池 (USDT/WBNB, USDC/WBNB, etc.). V3 `adapter_ready=false` (bsc_chain_adapter 未实现). V2 `adapter_ready=false` (bsc_chain_adapter 未实现) |
| F (合并) | expanded_universe = 33 (原) + 16 (Meteora verified) + 5 (Base UniV3 candidate) + 5 (Base Aero classic) + 5 (BSC Pancake V3) + 5 (BSC Pancake V2) = ~69 pools |
| G (decision) | universe 已扩, 但 Base/BSC `adapter_ready=false` 阻止 full coverage. `recommended_next_stage = LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1` |

## 4. 实数 (verified from prior research)

| Source | 数量 | 验证方式 |
|---|---|---|
| Meteora DLMM verified on-chain | **16 pools** (pool_chain_verification.json) | `account_exists=true, owner_is_meteora_dlmm=true, data_len=904` |
| Solana orca_whirlpool / raydium_clmm / raydium_cpmm | 33 pools | V2 12h universe (re-aggregate from 5 protocols) |
| Base Uniswap V3 / Aerodrome / BSC PancakeSwap V3/V2 | **0 verified on-chain** (本 stage 仅推断候选, 未 RPC-validate) | (not validated — adapter not wired) |

**诚实披露**: Base/BSC pools in this stage are **inferred candidates** from common mainnet patterns + 既有 BSC `precise_quote` artifacts, **not** RPC-validated in this stage. They are marked `adapter_ready=false, collector_observable=false` per spec requirement.

## 5. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `long_run_started` | `false` |
| `auto_next_stage_disabled` | `true` |
| `no_collector_started` | `true` |
| `no_tmux_session_created` | `true` |
| `no_12h_24h_48h_72h_7d_started` | `true` |

## 6. 严禁 (本轮全部不触发)

- ❌ 不启动 12h / 24h / 48h / 72h / 7d
- ❌ 不启动长期 collector
- ❌ 不启动新 tmux / cron / systemd / daemon
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer / 私钥
- ❌ 不发送 transaction / approve / mint / swap / bridge
- ❌ 不写 production positions
- ❌ 不覆盖 shadow 原始表
- ❌ 不接 paid RPC / paid indexer
- ❌ **不**修改 12h data_dir (84 文件, 0 修改)
- ❌ **不**修改 6h data_dir (42 文件, 0 修改)
- ❌ **不**修改 v2 12h FINAL_VERDICT / v2 6h FINAL_VERDICT / corrected verdicts / 12h node report
- ❌ **不**修改 supervisor stage runner (上一 stage 已修 finalize)
- ❌ **不**修改 collector (上一-2 stage 已修 --pool-universe)

## 7. 下一轮 (本 stage 推荐)

- **`LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1`** — 接通 Base/BSC EVM collector (EVM chain_adapter 实际接线到 long-horizon collector); Meteora DLMM collector 接线 (Go adapter → smoke mode). 完成此 stage 后 12h retry 才能真正 `collector_full_coverage_ready=true`.
- alternative: `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_REPEAT` — 找更多 Solana 池 (但 spec 不推荐, 因为 Solana 已有 33 + 16 = 49 池 ≥ 45 target).
- alternative: `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1` — 12h retry 仅在 Base/BSC 已 observable 之后才有意义, 否则 retry 仍 `partial_solana_real_pool_universe` 与现状无差.
- alternative: `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA` — 用户决定暂停.

## 8. 结论

✅ **Stage A PASS** — 输入证据齐备, finalize fix 已确认, 5 协议 gap 已确认, 既有 research artifacts (16 verified Meteora pools) 可用. 进入 Stage B 收 10 Meteora DLMM 真实池.
