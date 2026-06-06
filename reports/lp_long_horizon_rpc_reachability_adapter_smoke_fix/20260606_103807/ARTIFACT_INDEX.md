# ARTIFACT INDEX — RPC Reachability and Adapter Smoke Fix V1

- stage: `LP_LONG_HORIZON_COLLECTOR_RPC_REACHABILITY_AND_ADAPTER_SMOKE_FIX_V1`
- run_id: `20260606_103807`
- branch: `feat/supabase-postgres-deployment`
- status: **WARN** (4 conditions met, chain=2 < 3 because Base public RPC unreachable)
- generated_at_utc: `2026-06-06T10:49:00Z`

## 1. Output files (in `reports/lp_long_horizon_rpc_reachability_adapter_smoke_fix/20260606_103807/`)

| # | 文件 | 描述 |
|---|---|---|
| 1 | `INPUT_EVIDENCE_AUDIT_CN.md` | 输入证据审计 (CN) |
| 2 | `input_evidence_audit.json` | 输入证据审计 (JSON) |
| 3 | `RPC_FALLBACK_REGISTRY_CN.md` | RPC registry 设计 (CN) |
| 4 | `rpc_fallback_registry.json` | RPC registry (JSON) |
| 5 | `RPC_REACHABILITY_MATRIX_CN.md` | RPC reachability matrix (CN) |
| 6 | `rpc_reachability_matrix.csv` | RPC reachability matrix (CSV) |
| 7 | `rpc_reachability_matrix.json` | RPC reachability matrix (JSON) |
| 8 | `BASE_ADAPTER_SMOKE_RETRY_CN.md` | Base adapter smoke retry (CN) |
| 9 | `base_adapter_smoke_retry.json` | Base adapter smoke retry (JSON) |
| 10 | `BSC_ADAPTER_SMOKE_RETRY_CN.md` | BSC adapter smoke retry (CN) |
| 11 | `bsc_adapter_smoke_retry.json` | BSC adapter smoke retry (JSON) |
| 12 | `METEORA_DLMM_SMOKE_RETRY_CN.md` | Meteora DLMM smoke retry (CN) |
| 13 | `meteora_dlmm_smoke_retry.json` | Meteora DLMM smoke retry (JSON) |
| 14 | `INTEGRATED_OBSERVABLE_SMOKE_RETRY_CN.md` | Integrated smoke retry (CN) |
| 15 | `integrated_observable_smoke_retry.json` | Integrated smoke retry (JSON) |
| 16 | `COVERAGE_READINESS_DECISION_CN.md` | Coverage readiness decision (CN) |
| 17 | `coverage_readiness_decision.json` | Coverage readiness decision (JSON) |
| 18 | `FINAL_VERDICT.json` | Final verdict (含 spec-required 完整字段) |
| 19 | `ONEPAGE_CN.md` | One-pager 总结 (CN) |
| 20 | `ARTIFACT_INDEX.md` | 本文件 |
| 21 | `run_*.py` (4 files) | Smoke / matrix scripts (read-only) |
| 22 | `build_*.py` (2 files) | Build helpers (integrated smoke + decision) |

## 2. New file (in `scripts/lp_long_horizon/`)

| File | Status | 备注 |
|---|---|---|
| `rpc_registry.py` | new | RPC fallback registry — 3 chains, primary + fallback + env override, no secret |

## 3. Integrated smoke (45 real pools)

- `selected_pool_count`: 45 (all Solana, all real on-chain)
- `pool_snapshot_rows`: 45
- `quote_snapshot_rows`: 270 (45 × 6 notional)
- `fee_velocity_rows`: 225 (45 × 5 windows)
- `market_regime_rows`: 7
- `placeholder_pool_count`: **0**
- `all_pools_are_real_on_chain`: **true**

## 4. 锁定字段 (5 项全 false/no)

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
| `no_paid_rpc_key_committed` | `true` |
| `no_real_secret_committed` | `true` |

## 5. 严禁 (本轮全部不触发)

- ❌ 不启动 12h / 24h / 48h / 72h / 7d
- ❌ 不启动 long-running collector
- ❌ 不启动 tmux / cron / systemd / daemon
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer / 私钥
- ❌ 不发送 transaction / approve / mint / swap / bridge
- ❌ 不写 production positions
- ❌ 不覆盖 shadow 原始表
- ❌ 不接 paid RPC / paid indexer
- ❌ **不** 提交 paid RPC key
- ❌ **不** 写真实 secret
- ❌ **不**修改 12h data_dir (84 文件, 0 修改)
- ❌ **不**修改 6h data_dir (42 文件, 0 修改)
- ❌ **不**修改 v2 12h FINAL_VERDICT / v2 6h FINAL_VERDICT / corrected verdicts / 12h node report
- ❌ **不**修改 supervisor stage runner
- ❌ **不**修改 collector (本 stage 仅**新增** rpc_registry.py, **不**改** collector 主程序 / 已有 adapter)

## 6. 4-stage allowed next stages

- **`LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT`** (本 stage 推荐) — 在能 reach public Base RPC 的 env 再 smoke
- `LP_LONG_HORIZON_COLLECTOR_ADAPTER_CODE_FIX_REPEAT` — 主要因 Base/BSC/Meteora adapter 代码问题 (本 stage **不** 是这种情况)
- `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1` — 12h retry (但**不**推荐 until chain=3 met)
- `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA` — 用户决定暂停

## 7. Recommended next stage

**`LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT`**

理由: 5 conditions NOT all met. observable_pool_count=49 ≥ 45 ✓, observable_chain_count=2 < 3 (主要因 Base public RPC 全部 403 Forbidden in this env). 4 conditions met. 主要阻塞是 env-level 网络问题 (Base public RPC 不可达), **不** 是 adapter 代码问题 (4 个新 adapter + 1 verify 全部 self-check 通过; BSC V3 4/4 real on-chain 证明 adapter 工作). 下一 stage 在能 reach public Base RPC 的 env 再 smoke 一次, 或等 RPC 改善.

## 8. 5 conditions

| 条件 | 实际 | 状态 |
|---|---|---|
| `observable_pool_count >= 45` | 49 | ✅ met |
| `observable_chain_count >= 3` | 2 (solana + bsc) | ❌ NOT met |
| `observable_protocol_count >= 5` | 5 (4 Solana + 1 BSC) | ✅ met |
| `placeholder_pool_count == 0` | 0 | ✅ met |
| `no_wallet_tx_probe` | yes | ✅ met |

**1 condition NOT met**: `observable_chain_count` (2 < 3, Base 不可达).
