# Input Evidence Audit — Partial 12h Read-only Continuous Observation Request V1

- stage: `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_PARTIAL_REAL_UNIVERSE_REQUEST_V1`
- run_id: `20260606_131323`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T13:14:00Z`

## 0. 总结

✅ **本轮启动一个 12h 只读观察, 范围限定为当前已可观测的 Solana + BSC 真实池**. 同时保留 Base/Meteora RPC coverage gap, 显式标记 `coverage_scope=partial_solana_bsc_real_universe, full_coverage_ready=false, do_not_treat_as_full_universe=true`. **不** 实盘, **不** probe, **不** live. 每小时 checkpoint + 15min heartbeat. 12h 完成后自动 finalize + commit + push. **不** 自动进入 24h.

## 1. 4 个输入证据文件 (只读)

### 1.1 `reports/lp_long_horizon_rpc_reachability_adapter_smoke_fix/20260606_103807/FINAL_VERDICT.json` (prior stage)

```json
{
  "stage": "LP_LONG_HORIZON_COLLECTOR_RPC_REACHABILITY_AND_ADAPTER_SMOKE_FIX_V1",
  "status": "WARN",
  "adapter_registry_ready": true,
  "rpc_reachability_matrix_ran": true,
  "base_rpc_reachable": false,
  "bsc_rpc_reachable": true,
  "solana_rpc_reachable": true,
  "base_adapter_smoke_success": false,
  "bsc_adapter_smoke_success": true,
  "meteora_dlmm_smoke_success": false,
  "integrated_smoke_ran": true,
  "observable_pool_count": 49,
  "observable_chain_count": 2,
  "observable_protocol_count": 5,
  "placeholder_pool_count": 0,
  "collector_full_coverage_ready": false,
  "can_start_12h_real_universe_retry": false,
  "recommended_next_stage": "LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT"
}
```

**full_coverage_ready=false** (5 conditions 4 met, chain=2 < 3 因为 Base 不可达).

### 1.2 `reports/lp_long_horizon_rpc_reachability_adapter_smoke_fix/20260606_103807/integrated_observable_smoke_retry.json`

observable_pool_count=49 (45 Solana + 4 BSC V3), observable_chain_count=2, observable_protocol_count=5, placeholder_pool_count=0.

### 1.3 `reports/lp_long_horizon_real_pool_universe_coverage_expand/20260606_091120/expanded_real_pool_universe_for_12h_retry.json`

72 池 universe (solana 49 + base 10 + bsc 13). 本 stage 过滤出 49 observable 池 (Solana 45 + BSC V3 4).

### 1.4 `scripts/lp_long_horizon_readonly_collector_v1.py` (collector, 801 lines)

支持 `--pool-universe`, `--max-pools`, `--max-snapshots`, `--readonly`, `--no-wallet --no-tx --no-bridge --dry-run`. 12h 模式 via stage runner.

### 1.5 `scripts/run_lp_long_horizon_readonly_stage_once.sh` (stage runner, 518 lines)

4 个 Python heredoc (trap / aggregate / finalize / fallback) 全部 `<<'PYEOF_xxx'` quoted + env vars (上一-2 stage 已修 finalize). 转发 `--pool-universe` 给 collector.

## 2. 根因 (RCA)

12h retry 之前 blocking 在 `full_coverage_ready=false`. 主要因 Base public RPC 不可达 (env-level 网络问题, **不** 是 adapter 代码). 用户决定: **不** 等待 Base RPC 改善, 直接启动 partial 12h (Solana + BSC). 理由:
- Solana 已有 45 池 (4 protocols) 真实可观测
- BSC 已有 4 池 (1 protocol: PancakeSwap V3) 真实可观测
- 5 protocol target **已 met**
- 45 pool target **已 met**
- placeholder=0 **已 met**
- 仅 chain=2 < 3 (因为 Base 不可达), 这**不** 是 chain protocol/池 问题, 是**网络**问题
- 启动 partial 12h 不影响全链结论, 显式标记 `do_not_treat_as_full_universe=true`

## 3. 本轮操作 (Stage A→J)

| Stage | 操作 |
|---|---|
| A (input evidence) | 读 4 个 prior 文件, 确认 full_coverage_ready=false, observable=49, Base blocker 存在. 本轮是 partial 12h. |
| B (scope freeze) | 写明 `coverage_scope=partial_solana_bsc_real_universe, do_not_treat_as_full_universe=true`. |
| C (universe build) | 过滤 expanded universe, 留下 49 池 (45 Solana + 4 BSC V3). **不** 含 Base, **不** 含 BSC V2 zero-getPair, **不** 含 placeholder. |
| D (approval) | 记录 `APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=12h mode=readonly no_probe=true scope=partial_solana_bsc`. `auto_advance_allowed=false`. |
| E (run config) | 12h duration, 60min checkpoint, 15min heartbeat, no auto advance. |
| F (safety check) | 验证: 无 running collector / canary / live / paper / wallet / keypair. partial universe no placeholder, ≥45. tests pass. dirs writable. **失败则不启动**. |
| G (launch) | tmux/noHup 启动 stage runner, 12h. 2-3min healthcheck. commit + push. |
| H (finalize 模板) | 12h 完成后自动 finalize (此 stage 启动后由 G 自动触发, 不在本 stage 范围内). |
| I (tests) | pytest 至少 22 tests + go test. |
| J (git publish) | commit + push. |

## 4. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `long_run_started` | `false` (启动时变 `true`) |
| `auto_advance_to_24h_disabled` | `true` |
| `do_not_treat_as_full_universe` | `true` |
| `no_collector_started_pre_safety_check` | `true` (启动前必须为 true) |
| `no_paid_rpc_key_committed` | `true` |
| `no_real_secret_committed` | `true` |

## 5. 严禁 (本轮全部不触发, 启动后仍不触发)

- ❌ 不启动 24h / 48h / 72h / 7d (auto_advance_to_24h=false)
- ❌ 不启动并行 collector (单 stage runner only)
- ❌ 不启用 cron / systemd / daemon (tmux session 启动, no daemon mode)
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / seed / keypair / signer
- ❌ 不发送 transaction / approve / mint / swap / bridge
- ❌ 不写 production positions
- ❌ 不覆盖 shadow 原始表
- ❌ 不接 paid RPC / paid indexer (仅 public free RPC)
- ❌ **不** 写真实 RPC key / private_key / mnemonic / seed
- ❌ **不**修改 12h data_dir (84 文件, 0 修改)
- ❌ **不**修改 6h data_dir (42 文件, 0 修改)
- ❌ **不**修改 v2 12h FINAL_VERDICT / v2 6h FINAL_VERDICT / corrected verdicts / 12h node report
- ❌ **不**修改 supervisor stage runner (上一-2 stage 已修 finalize)
- ❌ **不**修改 collector (本 stage 仅**新增** partial universe file, **不**改** collector 主程序)

## 6. 12h 后处理 (Stage H, 启动后由 G 触发, 不在本 stage 范围内)

12h 完成后 stage runner 自动生成:
- `FINAL_VERDICT.json` (status=RUNNING → PASS/WARN/FAIL, gate_pass=true/false)
- `ONEPAGE_CN.md`
- `ARTIFACT_INDEX.md`
- 12h node report (基于 partial coverage, **不** 当 full coverage 用)
- coverage manifest (3 levels: chain/dex/pool, observed=false 标记 Base)
- fee estimation basis
- candidate review
- next node decision

`recommended_next_stage` 仅允许 4 个值:
- `LP_LONG_HORIZON_PARTIAL_12H_NODE_REPORT_REVIEW_V1`
- `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT`
- `LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_PARTIAL_EXTENSION_REQUEST_V1`
- `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA`

## 7. 结论

✅ **Stage A PASS** — 输入证据齐备, full_coverage_ready=false 已确认, observable=49 (Solana 45 + BSC V3 4), Base RPC blocker 存在, 本轮是 partial 12h. 进入 Stage B scope freeze.
