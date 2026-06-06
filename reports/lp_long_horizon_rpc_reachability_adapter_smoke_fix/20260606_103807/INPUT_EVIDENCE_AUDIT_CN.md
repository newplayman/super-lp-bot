# Input Evidence Audit — RPC Reachability and Adapter Smoke Fix V1

- stage: `LP_LONG_HORIZON_COLLECTOR_RPC_REACHABILITY_AND_ADAPTER_SMOKE_FIX_V1`
- run_id: `20260606_103807`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T10:39:00Z`

## 0. 总结

✅ **本轮只做 RPC reachability / endpoint fallback / adapter smoke fix, 不启动 12h / 24h / 任何长跑**. 上一 stage 4 个新 adapter (Base UniV3, Base Aerodrome, BSC V3, BSC V2) + 1 verify (Meteora DLMM) 全部 self-check 通过, **代码** ready. 唯一阻塞是公共 RPC reachability (Base public RPC + Solana public RPC 在此 env 受限, BSC public RPC 可达但 V2 candidate 地址空). 本 stage: (a) 新增 `rpc_registry.py` 集中管理 primary + fallback + env override, (b) 实测 RPC reachability matrix, (c) 重试 Base / BSC / Meteora adapter smoke, (d) 跑 integrated smoke with 45 pools, (e) 决定 next stage.

## 1. 8 个输入证据文件 (只读)

### 1.1 `reports/lp_long_horizon_collector_adapter_coverage_wiring/20260606_093857/FINAL_VERDICT.json` (prior stage)

```json
{
  "stage": "LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1",
  "status": "WARN",
  "adapter_registry_ready": true,
  "base_uniswap_v3_adapter_ready": true,
  "base_aerodrome_adapter_ready": "classic_only",
  "bsc_pancakeswap_v3_adapter_ready": true,
  "bsc_pancakeswap_v2_adapter_ready": true,
  "meteora_dlmm_long_horizon_adapter_ready": "existing_solana_rpc_works_when_rpc_reachable",
  "integrated_smoke_ran": true,
  "observable_pool_count": 13,
  "observable_chain_count": 2,
  "observable_protocol_count": 5,
  "placeholder_pool_count": 0,
  "collector_full_coverage_ready": false,
  "can_start_12h_real_universe_retry": false,
  "recommended_next_stage": "LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT"
}
```

**adapter code ready** (5 适配器全部 self-check 通过), **但** public Base/Solana RPC 在此 env 受限.

### 1.2 5 个 adapter file (代码 ready, RPC 受限)

| Adapter | Status | Smoke 阻塞 |
|---|---|---|
| `scripts/lp_long_horizon/adapters/evm_base_uniswap_v3.py` | ready | Base public RPC not reachable |
| `scripts/lp_long_horizon/adapters/evm_base_aerodrome.py` | ready (classic_only, slipstream=not supported) | Base public RPC not reachable |
| `scripts/lp_long_horizon/adapters/evm_bsc_pancakeswap_v3.py` | ready | (1 pool real observed in prior stage) |
| `scripts/lp_long_horizon/adapters/evm_bsc_pancakeswap_v2.py` | ready | WBNB/USDT address returned empty; need factory.getPair |
| `scripts/lp_long_horizon/adapters/solana_meteora_dlmm_check.py` | ready | Solana public RPC returned empty for 2 test pools |

### 1.3 `reports/lp_long_horizon_real_pool_universe_coverage_expand/20260606_091120/expanded_real_pool_universe_for_12h_retry.json`

72 pools (solana 49 + base 10 + bsc 13). 5 池用 `PENDING_*_RPC_VALIDATION` marker (4 Base UniV3 + 1 BSC V2), 等本 stage 用 factory.getPair / PoolFactory.getPool 解析.

### 1.4 `scripts/lp_long_horizon_readonly_collector_v1.py` (collector)

801 lines. 已支持 `--pool-universe`. 本 stage 用 `--pool-universe=expanded_universe_for_12h_retry.json --max-pools 45 --max-snapshots 1`.

## 2. 根因 (RCA)

5 个 adapter 全部代码 ready, **唯一阻塞**是公共 RPC reachability. 进一步分析:

| Issue | Root cause | Fix |
|---|---|---|
| Base public RPC not reachable | 防火墙/网络问题, 单 endpoint (mainnet.base.org) | 引入 fallback list (base-rpc.publicnode.com, base.llamarpc.com) |
| Solana public RPC empty for Meteora test | rate-limit 或 endpoint issue | 引入 fallback list (solana-rpc.publicnode.com) |
| BSC V2 candidate address empty | 0x16b9a8...162 地址不是真实 WBNB/USDT pair, **不** 该硬编码 | 改用 `PancakeSwap V2 Factory.getPair(tokenA, tokenB)` 解析真实 pair |

## 3. 本轮操作

| Stage | 操作 |
|---|---|
| B (registry) | 新增 `scripts/lp_long_horizon/rpc_registry.py` 集中管理 base/bsc/solana 3 chain 的 primary + fallback + env override. **不** 提交任何 paid RPC key. |
| C (reachability) | 对每条链每个 endpoint 做只读 probe (eth_chainId / eth_blockNumber / getLatestBlockhash). Honest 记录 latency + error. |
| D (Base retry) | 用 selected Base endpoint 重试 Base UniV3 + Aerodrome classic. Slipstream 仍 marked unsupported honestly. |
| E (BSC retry) | 用 selected BSC endpoint 重试 BSC V3 + V2. V2 改用 `factory.getPair(tokenA, tokenB)` 解析真实 pair. |
| F (Meteora retry) | 用 selected Solana endpoint 重试 Meteora DLMM. |
| G (integrated) | 用 expanded universe 72 池, `--max-pools 45 --max-snapshots 1` 跑短 smoke. No placeholder fallback. |
| H (decision) | 5 conditions: observable>=45, chain>=3, protocol>=5, placeholder=0, no wallet/tx. 决定 next stage. |
| I (final) | FINAL_VERDICT.json + ONEPAGE_CN.md + ARTIFACT_INDEX.md |
| J (test + safety) | pytest + go test + ps safety |
| K (git publish) | commit + push |

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
| `no_12h_retry_started` | `true` |
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
- ❌ **不** 提交 paid RPC key (即使 env var 也**不** 提交真实 value, 仅占位)
- ❌ **不** 写真实 secret (private_key, mnemonic, seed, API key)
- ❌ **不**修改 12h data_dir (84 文件, 0 修改)
- ❌ **不**修改 6h data_dir (42 文件, 0 修改)
- ❌ **不**修改 v2 12h FINAL_VERDICT / v2 6h FINAL_VERDICT / corrected verdicts / 12h node report
- ❌ **不**修改 supervisor stage runner
- ❌ **不**修改 collector (本 stage 仅**新增** rpc_registry.py, **不**改** collector 主程序 / 已有 adapter)
- ❌ **不** 假装 RPC 成功 (reachability 失败必须 honest 记录)

## 6. 下一轮 (本 stage 推荐)

- **`LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1`** — 仅当 all 5 conditions met 时推荐
- **`LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT`** — 主要因 public RPC 不稳定
- **`LP_LONG_HORIZON_COLLECTOR_ADAPTER_CODE_FIX_REPEAT`** — 主要因 Base/BSC/Meteora adapter 代码问题
- **`PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA`** — 用户决定暂停

## 7. 结论

✅ **Stage A PASS** — 输入证据齐备, 5 适配器代码 ready, 唯一阻塞是 public RPC reachability. 进入 Stage B 构建 RPC fallback registry.
