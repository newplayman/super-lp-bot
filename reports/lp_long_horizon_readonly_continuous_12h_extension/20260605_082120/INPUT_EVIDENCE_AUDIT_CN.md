# Stage A: 输入证据审计

- stage: `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_EXTENSION_REQUEST_V1`
- audit_stage: `A_INPUT_EVIDENCE_AUDIT`
- audited_at_utc: `2026-06-05T14:42:00Z`
- auditor: agent (read-only)

## 0. 目的

确认 6h 阶段已 PASS, 12h 延展条件已满足, 但 6h 用的是 5 个 smoke placeholder 池, 12h **必须**使用真实 pool universe (从已有 readonly connector 研究提取), 不得继续 placeholder.

## 1. 7 个核心输入证据

| 标签 | 路径 | 关键事实 |
|---|---|---|
| `6h_corrected_verdict` | `reports/lp_long_horizon_6h_finalizer_rebuild/20260605_043726/CORRECTED_FINAL_VERDICT.json` | gate=**PASS**, runtime=**360**, data_quality=**PASS**, 13/13 gate checks pass, recommended=12H_EXTENSION_REQUEST_V1 |
| `6h_node_report` | `reports/lp_long_horizon_node_reports/20260605_043726/6h/FINAL_NODE_VERDICT.json` | full_sample=**true**, ckpts=6/6, gate=PASS |
| `6h_coverage_manifest` | `reports/lp_long_horizon_node_reports/20260605_043726/6h/POOL_UNIVERSE_COVERAGE_MANIFEST.csv` | 5 smoke placeholder pools, **全部 tvl=0**, 0 real pools |
| `readonly_connector_research` | `reports/lp_orca_whirlpool_readonly_connector/` + `reports/lp_raydium_clmm_readonly_connector/` + `reports/lp_raydium_cpmm_readonly_connector/` | orca: 75 selected candidates; raydium_clmm: 80 selected; raydium_cpmm: 120 selected. **真实** on-chain pool addresses, real TVL, real 24h volume |
| `supervisor_script_6h` | `scripts/run_lp_long_horizon_readonly_6h_once.sh` | 750 行, END_TS-based loop + fail-safe trap + .finalize_succeeded marker + CORRECTED_FINAL_VERDICT_FALLBACK.json |
| `node_report_generator` | `scripts/lp_long_horizon_node_report_generator_v1.py` v1.0 | 支持 6h/12h/24h/48h/72h/7d, 11 输出文件 per node |
| `collector_script` | `scripts/lp_long_horizon_readonly_collector_v1.py` v1.0 | design + smoke modes, current smoke pool count=5 (placeholder) |

## 2. 关键断言

| 断言 | 值 |
|---|---|
| `6h_corrected_gate_pass` | ✅ **true** |
| `6h_corrected_runtime_valid` | ✅ **true** |
| `6h_corrected_actual_runtime_minutes` | ✅ **360** |
| `6h_corrected_checkpoint_count` | ✅ **6** |
| `6h_full_node_report_exists` | ✅ **true** |
| `6h_pool_universe_was_placeholder` | ✅ **true** (5 smoke placeholder pools) |
| `6h_smoke_placeholder_pool_count` | `5` |
| `6h_real_pool_count` | `0` |
| `12h_must_use_real_pool_universe` | ✅ **true** |
| `12h_real_pool_sources_available` | ✅ 3 protocols: orca + raydium_clmm + raydium_cpmm |
| `12h_missing_protocols` | ⚠️ meteora_dlmm + raydium_amm_v4 (未实现) + stable/LST-stable (无 dedicated research) |
| `12h_evm_status` | ⚠️ Base/BSC collectors NOT wired into smoke mode |
| `no_auto_24h` | ✅ **true** (LOCKED) |
| `manual_approval_required_for_24h` | ✅ **true** |
| `can_run_probe_now` | ❌ **false** (LOCKED) |
| `tiny_canary_allowed` | `"no"` (LOCKED) |
| `edge_proven` | `"no"` (LOCKED) |
| `wallet_or_tx_touched` | ❌ **false** (LOCKED) |
| `transaction_sent` | ❌ **false** (LOCKED) |
| `lp_strategy_research_freeze` | **ACTIVE** |

## 3. 6h vs 12h 改进点

| 维度 | 6h (已完成) | 12h (本轮启动) |
|---|---|---|
| 池 universe | 5 smoke placeholder (tvl=0) | **35+ real pools** (从 orca/raydium_clmm/raydium_cpmm readonly connector 研究提取) |
| pool address | `<smoke_pool_*_a>` placeholder | 真实 base58 Solana 地址 (e.g. `Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE` for SOL/USDC) |
| TVL | 0 (placeholder) | 真实 on-chain TVL (e.g. orca SOL/USDC: 32M USD) |
| 24h volume | 0 (placeholder) | 真实 on-chain 24h volume (e.g. orca SOL/USDC: 230M USD) |
| token pair | `?` (placeholder) | 真实 token symbol (e.g. SOL/USDC, SOL/Fartcoin, cbBTC/USDC) |
| quote_ready | 0/5 | (TBD by collector, real on-chain RPC) |
| fee_ready | 0/5 | (TBD by collector, real on-chain RPC) |
| ev_ready | 0/5 | (TBD by collector) |
| preflight_candidate | 0 | (TBD by collector) |
| 协议覆盖 | 5 solana protocols (smoke placeholder) | 3 solana protocols (real) + 2 missing (meteora_dlmm / raydium_amm_v4) + stable/LST-stable (TBD) |
| 链覆盖 | 1 (solana, smoke) | 1 (solana, real) + EVM/BSC NOT wired into smoke mode (honest disclosure) |
| wallclock | 6h (360 min) | **12h (720 min)** |
| checkpoint interval | 1h | 1h |
| heartbeat interval | 15 min | 15 min |

## 4. 6h 关键数据 (锁定)

| 字段 | 值 |
|---|---|
| actual_runtime_minutes | 360 |
| actual_runtime_valid_for_6h_gate | true |
| short_mode_used | false |
| checkpoint_count | 6 |
| selected_pool_count | 5 (placeholder) |
| pool_snapshot_rows | 5 (placeholder) |
| quote_snapshot_rows | 180 (placeholder) |
| fee_velocity_rows | 150 (placeholder) |
| liquidity_distribution_rows | 30 (placeholder) |
| market_regime_rows | 42 (placeholder) |
| data_quality_status | PASS |
| gate_pass | true |
| recommended_next_stage | LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_EXTENSION_REQUEST_V1 |

## 5. 12h 协议覆盖 (honest disclosure)

| Chain | Protocol | Status | Reason |
|---|---|---|---|
| solana | orca_whirlpool | ✅ real pool universe (10+ pools) | readonly connector research `reports/lp_orca_whirlpool_readonly_connector/20260604_025414/orca_candidate_source_collection.csv` |
| solana | raydium_clmm | ✅ real pool universe (10+ pools) | readonly connector research `reports/lp_raydium_clmm_readonly_connector/20260604_034503/raydium_clmm_candidate_source_collection.csv` |
| solana | raydium_cpmm | ✅ real pool universe (10+ pools) | readonly connector research `reports/lp_raydium_cpmm_readonly_connector/20260604_040952/raydium_cpmm_candidate_source_collection.csv` |
| solana | meteora_dlmm | ❌ observed=false | `not_implemented_yet` (no Go pool adapter; no readonly connector research yet) |
| solana | raydium_amm_v4 | ❌ observed=false | `not_implemented_yet` (legacy AMM, no Go pool adapter) |
| solana | solana_stable | ⚠️ TBD (5 pools TBD) | no dedicated research yet, will use existing real pools from orca/raydium_clmm/raydium_cpmm if they fit stable/stable pair (e.g. USDC/USDT) |
| base | uniswap_v3 | ❌ observed=false | `evm_collector_not_wired_into_smoke_mode` (Go adapter `internal/adapters/pool/uniswap_v3` exists, but smoke mode doesn't reach EVM) |
| base | aerodrome | ❌ observed=false | `evm_collector_not_wired_into_smoke_mode` (Go adapter exists, same reason) |
| bsc | pancakeswap_v3 | ❌ observed=false | `bsc_chain_adapter_not_implemented_yet` + evm_collector_not_wired |
| bsc | pancakeswap_v2 | ❌ observed=false | `bsc_chain_adapter_not_implemented_yet` + evm_collector_not_wired |

## 6. 严禁 (本轮全部不触发)

- 不启动 24h / 48h / 72h / 7d
- 不启动并行 collector
- 不启用 cron / systemd / daemon
- 不 probe / canary / live / paper
- 不读 wallet / keypair / signer / 私钥
- 不创建 signer
- 不发送 transaction / approve / mint / swap / bridge
- 不写 production positions
- 不覆盖 shadow 原始表
- 不接 paid RPC / paid indexer
- 不修改 6h data_dir (42 文件, 0 修改)
- 不修改 6h report_dir

## 7. 结论

✅ 6h gate PASS, 12h 延展条件已满足. 6h 用的是 5 smoke placeholder 池, 12h **必须**用真实 pool universe (从 orca/raydium_clmm/raydium_cpmm readonly connector 研究提取). 缺失的 meteora_dlmm / raydium_amm_v4 / EVM/BSC 必须在 coverage manifest 写 observed=false + reason, 不得假装覆盖.

**Stage A PASS** → 进入 Stage B (12h 审批记录).
