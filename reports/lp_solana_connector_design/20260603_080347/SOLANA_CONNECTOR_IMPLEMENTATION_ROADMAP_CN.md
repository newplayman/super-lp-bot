# Solana Connector Implementation Roadmap — Stage K

- stage: `LP_SOLANA_LP_CONNECTOR_DESIGN_V1`
- run_id: `20260603_080347`

## 0. 总览（6 phases）

```
Phase 1:  Solana read-only RPC readiness + protocol registry
   ↓
Phase 2:  Meteora DLMM pool metadata read-only connector
   ↓
Phase 3:  Meteora DLMM quote + bin liquidity snapshot
   ↓
Phase 4:  Meteora fee velocity / volume proxy
   ↓
Phase 5:  Solana survival EV preview (read-only model)
   ↓
Phase 6:  Solana 10/20U probe preflight review
   ↓
[future]
Phase 7+: Dry-run builder; actual execution stages (operator approval gated)
```

## 1. Phase 1 — Solana read-only RPC readiness + protocol registry

| 字段 | 值 |
|---|---|
| task_name | Solana RPC public connection + 4-protocol registry + cached pool universe |
| script_name | `scripts/lp_solana_readonly_rpc_and_registry_v1_readonly.py` |
| report_dir | `reports/lp_solana_readonly_rpc_and_registry/<RUN_ID>/` |
| inputs | public Solana RPC urls; protocol program IDs (Meteora DLMM, Meteora DAMM v2, Orca Whirlpools, Raydium CLMM) |
| outputs | `solana_lp_pool_universe_v1` jsonl + csv; `solana_lp_pool_metadata_v1` jsonl; protocol registry YAML |
| tests | `tests/test_lp_solana_readonly_rpc_and_registry_v1_readonly.py` |
| safety_gate | read-only RPC; no wallet; no signing; no tx |
| expected_blocker | public RPC rate limit; some accounts (very large) may need ddrpc fallback |
| next_stage | Phase 2 |

**关键动作**:
- 验证 public RPC (`api.mainnet-beta.solana.com` + `solana.publicnode.com`) 可用
- 4 个 protocol program pubkey 列表 (Meteora DLMM, Meteora DAMM v2, Orca Whirlpools, Raydium CLMM)
- discovery via `getProgramAccounts` with filters
- write to local JSONL (not in production DB; not in shadow tables)
- 缓存 24h rolling
- 严禁: 任何 private RPC; 任何 wallet 关联; 任何 tx

## 2. Phase 2 — Meteora DLMM pool metadata read-only connector

| 字段 | 值 |
|---|---|
| task_name | Meteora DLMM account decoder; populate metadata table |
| script_name | `scripts/lp_meteora_dlmm_readonly_connector_v1_readonly.py` |
| report_dir | `reports/lp_meteora_dlmm_readonly_connector/<RUN_ID>/` |
| inputs | Phase 1 universe; Meteora DLMM IDL/SDK reference (or raw parser) |
| outputs | `solana_lp_pool_metadata_v1` populated for Meteora DLMM; `bin_step`, `dynamic_fee_supported`, `token_a/b_vault` |
| tests | `tests/test_lp_meteora_dlmm_readonly_connector_v1_readonly.py` |
| safety_gate | read-only; no signing; no tx |
| expected_blocker | exact LbPair account layout may need on-chain test; dynamic fee formula may need calibration |
| next_stage | Phase 3 |

**关键动作**:
- 写 raw Python parser for LbPair state (size ~ 900 bytes)
- 提取: `bin_step_bps`, `active_id`, `mint_x`, `mint_y`, `vault_token_x`, `vault_token_y`, `base_fee_bps`
- 写 metadata table
- 严禁: 任何 wallet 操作

## 3. Phase 3 — Meteora DLMM quote + bin liquidity snapshot

| 字段 | 值 |
|---|---|
| task_name | Bin array loader; quote per notional; liquidity snapshot |
| script_name | `scripts/lp_meteora_dlmm_quote_liquidity_v1_readonly.py` |
| report_dir | `reports/lp_meteora_dlmm_quote_liquidity/<RUN_ID>/` |
| inputs | Phase 2 metadata; BinArray accounts (PDA derived from lbPair + bin_array_idx) |
| outputs | `solana_lp_liquidity_snapshot_v1`; `solana_lp_quote_snapshot_v1` (10/20/100U) |
| tests | `tests/test_lp_meteora_dlmm_quote_liquidity_v1_readonly.py` |
| safety_gate | read-only; no signing |
| expected_blocker | BinArray account size ~ 8000 bytes; may exceed public RPC response limits |
| next_stage | Phase 4 |

**关键动作**:
- derive BinArray PDA: `[DLMM_program, "bin_array", lbPair_pubkey, bin_array_idx]`
- load BinArray account; parse 256 bins
- snapshot active_bin + 10 bins each side
- quote via simulateTransaction (read-only; unsigned)
- 6 notionals × N pools → 6N rows

## 4. Phase 4 — Meteora fee velocity / volume proxy

| 字段 | 值 |
|---|---|
| task_name | Decoded swap events; volume + fee 24h proxy |
| script_name | `scripts/lp_meteora_fee_velocity_v1_readonly.py` |
| report_dir | `reports/lp_meteora_fee_velocity/<RUN_ID>/` |
| inputs | Phase 1/2/3 outputs; Solana `getSignaturesForAddress` + `getTransaction` |
| outputs | `solana_lp_fee_velocity_v1` (24h/7d volume + fee_usd + fee_apr_proxy) |
| tests | `tests/test_lp_meteora_fee_velocity_v1_readonly.py` |
| safety_gate | read-only; no signing |
| expected_blocker | rate limit on getSignaturesForAddress; some Meteora DLMM swap events may need manual decoding |
| next_stage | Phase 5 |

**关键动作**:
- query `getSignaturesForAddress(lbPair_pubkey, limit=1000)` for last 24h
- query `getTransaction` for each signature; parse swap event from inner instructions
- aggregate volume in USD (using cached USDC price)
- aggregate fee = volume × fee_bps
- fee_apr = fee_24h / TVL × 365
- Jupiter Quote API for USDC price reference

## 5. Phase 5 — Solana survival EV preview (read-only model)

| 字段 | 值 |
|---|---|
| task_name | Apply adapted EVM V3 survival EV model to Solana pool set |
| script_name | `scripts/lp_solana_survival_ev_preview_v1_readonly.py` |
| report_dir | `reports/lp_solana_survival_ev_preview/<RUN_ID>/` |
| inputs | Phase 2 metadata + Phase 3 quote + Phase 4 fee velocity |
| outputs | `solana_lp_virtual_position_preview_v1`; per (pool, notional, hold) net_ev_proxy |
| tests | `tests/test_lp_solana_survival_ev_preview_v1_readonly.py` |
| safety_gate | read-only; pure model |
| expected_blocker | Solana-specific IL model differs (DLMM binary; CLMM gradual); calibration needed |
| next_stage | Phase 6 |

**关键动作**:
- 复用 EVM V3 5-scenario × 6-notional × 9-hold grid
- 替换 cost model with Solana rent + tx + priority
- DLMM survival = 1 if active_bin in chosen range; CLMM = Gaussian half-normal
- 输出 positive_realistic_count 等; 与 EVM V3 对比

## 6. Phase 6 — Solana 10/20U probe preflight review

| 字段 | 值 |
|---|---|
| task_name | Run 12-gate preflight against top 1-3 Solana candidates |
| script_name | `scripts/lp_solana_probe_preflight_review_v1_readonly.py` |
| report_dir | `reports/lp_solana_probe_preflight_review/<RUN_ID>/` |
| inputs | Phase 5 EV preview top candidates; current SOL/USDC prices; cost estimates |
| outputs | `solana_lp_probe_preflight_v1` for top candidates; preflight_pass yes/warn/no per candidate |
| tests | `tests/test_lp_solana_probe_preflight_review_v1_readonly.py` |
| safety_gate | read-only; **NOT** actually executing probe |
| expected_blocker | need actual wallet pubkey for balance check (still read-only); may need to add wallet to balance check before probe |
| next_stage | STOP or future dry-run/execution stages |

**关键动作**:
- 12-gate preflight design
- simulateTransaction on unsigned tx (still no signing)
- output preflight_pass + blocker
- 报告 + 推荐; 不实际执行 probe

## 7. Phase 7+ (NOT THIS STAGE; future)

| phase | task | safety |
|---|---|---|
| 7 | LP_SOLANA_10_20U_PROBE_DRY_RUN_BUILDER_V1 | build unsigned tx; no sign |
| 8 | LP_SOLANA_10_20U_PROBE_FIRST_EXECUTION_REQUEST_V1 | operator explicit approval |
| 9 | LP_SOLANA_10_20U_PROBE_FIRST_EXECUTION_RUN_V1 | actual send |

**Only when operator types A + 2 specific phrases + double confirmation flag**.

## 8. 不在任何 phase 做

- ❌ 读 Solana 私钥/seed phrase/keypair
- ❌ 创建 signer
- ❌ 发 Solana transaction (除 simulateTransaction)
- ❌ 启动 live/paper/canary
- ❌ 桥接
- ❌ 换币
- ❌ 写 production positions
- ❌ 覆盖 shadow 表
- ❌ 修改 EVM executor 执行路径
- ❌ 解除 send hard-disable

## 9. 安全断言（roadmap 全程）

```text
evm_v3_path_paused                    = true
solana_connector_design_complete      = false  (this stage only design)
solana_connector_implementation_status = phase_1_pending
can_run_probe_now                      = false
solana_wallet_or_keypair_touched       = false
tiny_canary_allowed                    = "no"
edge_proven                            = "no"
```

## 10. 决策

下一阶段推荐 = **LP_SOLANA_READONLY_RPC_AND_REGISTRY_V1** (Phase 1)：
- 不直接进 Meteora DLMM connector (Phase 2)
- 原因：必须先确认 public RPC + 4 个 protocol program pubkey 都可用；data confidence 建立后再进 Phase 2。
- 这是 4 个允许 next stage 中风险最低的入口。
