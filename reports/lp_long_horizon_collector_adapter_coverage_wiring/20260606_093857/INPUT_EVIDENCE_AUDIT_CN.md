# Input Evidence Audit — Collector Adapter Coverage Wiring V1

- stage: `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1`
- run_id: `20260606_093857`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T09:39:00Z`

## 0. 总结

✅ **本轮只做 wiring + short smoke, 不启动 12h / 24h / 长期 collector / 任何长跑**. 上一 stage 已确认 universe 33 → 72, 8 protocols, 3 chains, 但 23 池 (10 Base + 13 BSC) `collector_observable=false` 因为 EVM/BSC adapter 未接入 long-horizon collector. 本 stage 给 5 个缺失 adapter (Base UniV3, Base Aerodrome, BSC V3, BSC V2, Meteora DLMM check) 接入或验证. **预期** observable_pool_count 升到 49+ 取决于 (a) public RPC 实际可用, (b) EVM 池的 `PENDING_*_RPC_VALIDATION` placeholder 在 smoke 中能被解析. 如果 smoke 因 RPC 受限部分失败, 必须**诚实**记录, **不** 得把 adapter_missing 标成 pool negative.

## 1. 5 个输入证据文件 (只读)

### 1.1 `reports/lp_long_horizon_real_pool_universe_coverage_expand/20260606_091120/FINAL_VERDICT.json` (prior stage)

```json
{
  "stage": "LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1",
  "status": "WARN",
  "expanded_pool_count": 72,
  "added_pool_count": 39,
  "meteora_dlmm_added_count": 16,
  "base_uniswap_v3_added_count": 5,
  "base_aerodrome_added_count": 5,
  "bsc_pancakeswap_v3_added_count": 8,
  "bsc_pancakeswap_v2_added_count": 5,
  "observable_pool_count": 49,
  "non_observable_pool_count": 23,
  "collector_full_coverage_ready": false,
  "can_start_12h_retry_after_this": false,
  "recommended_next_stage": "LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1"
}
```

**expanded universe = 72 pools**, **observable = 49** (Solana only), **non_observable = 23** (10 Base + 13 BSC).

### 1.2 `reports/lp_long_horizon_real_pool_universe_coverage_expand/20260606_091120/expanded_real_pool_universe_for_12h_retry.json` (current universe)

72 池: solana 49 (33 V2 + 16 Meteora) + base 10 (UniV3 5 + Aero 5) + bsc 13 (V3 8 + V2 5). 5 池的 pool_address 是 `PENDING_*_RPC_VALIDATION` marker (4 Base UniV3 + 1 BSC V2), 等待 EVM/BSC RPC-validate.

### 1.3 `reports/lp_long_horizon_real_pool_universe_collector_fix/20260605_083000/FINAL_VERDICT.json` (prior-2 stage)

collector CLI 已支持 `--pool-universe`, stage runner 转发 `--pool-universe` 给 collector. 短 smoke 5 real pools 验证通过.

### 1.4 `scripts/lp_long_horizon_readonly_collector_v1.py` (collector)

801 lines, 默认 `--mode design`, 接受 `--pool-universe`, 写入 real pool snapshots. **当前 5 个缺失 adapter 都没在 collector 内部 stub** — 5 个 EVM/BSC/Meteora chain 需要单独 wire.

### 1.5 `scripts/run_lp_long_horizon_readonly_stage_once.sh` (stage runner)

518 lines. trap / aggregate / finalize / fallback 4 个 Python heredoc 全部 `<<'PYEOF_xxx'` quoted + env vars (上一 stage 已修). 转发 `--pool-universe` 给 collector.

## 2. 5 个缺失 adapter (本 stage 目标)

| Adapter | 缺失原因 | 来源 |
|---|---|---|
| Base Uniswap V3 | EVM collector not wired into smoke mode; Go adapter exists at `internal/adapters/pool/uniswap_v3` but Python long-horizon collector 没接通 | V2 missing_protocols_honest_disclosure |
| Base Aerodrome | 同上 (Solidly fork + Slipstream custom tick math) | V2 missing_protocols_honest_disclosure |
| BSC PancakeSwap V3 | bsc_chain_adapter_not_implemented_yet | V2 missing_protocols_honest_disclosure |
| BSC PancakeSwap V2 / CPMM | 同上 | V2 missing_protocols_honest_disclosure |
| Meteora DLMM (long-horizon check) | 已有 connector (`reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/`), 但 long-horizon collector 内部没接通, 仅 spec 上 `adapter_ready=true` | 16 verified pools |

## 3. 现有基础设施 (本 stage 复用)

| 文件 | 描述 |
|---|---|
| `scripts/lp_long_horizon/__init__.py` | LP long-horizon read-only collector helper package |
| `scripts/lp_long_horizon/adapters/__init__.py` | adapters subpackage |
| `scripts/lp_long_horizon/adapters/solana_rpc_readonly.py` | 现有 Solana RPC read-only adapter (getMultipleAccountsInfo) |
| `scripts/lp_long_horizon/adapters/public_api_coingecko.py` | 现有 Coingecko read-only adapter (OHLC) |
| `scripts/lp_long_horizon/adapters/local_artifact_replay.py` | 现有 local artifact replay |
| `scripts/lp_long_horizon/classify/market_regime.py` | 7-regime classifier |
| `scripts/lp_long_horizon/storage/research_store.py` | SQLite + JSONL store |
| `scripts/lp_long_horizon/utils/retry.py` | retry/backoff/timeout/429 helpers |
| `scripts/lp_long_horizon/utils/abort.py` | AbortController, ErrorRateMonitor |

**关键观察**: Python long-horizon helper package **已存在**, 但只 stub 了 Solana 链. EVM/BSC 需要新增 4 个 adapter (Base UniV3, Base Aerodrome, BSC V3, BSC V2), Meteora DLMM 验证 long-horizon 可读.

## 4. 根因 (RCA)

5 个缺失 adapter 都因为 "EVM / BSC 池**未** 在 long-horizon Python collector stub 中", 而 Go `internal/adapters/pool/*` 仅是 dryrun code, **不** 被 long-horizon Python 实际调用. 修复 = 在 `scripts/lp_long_horizon/adapters/` 新增 5 个 Python adapter file, 每个:
- 提供 read-only eth_call / Solana getMultipleAccountsInfo
- 输出 pool_snapshot + quote_snapshot (healer / fallback)
- 标记 `implementation_status` 明确
- 不读 wallet / 不签名 / 不发 tx
- 接受 timeout + 429 backoff

## 5. 本轮操作

| Stage | 操作 |
|---|---|
| B (registry) | 设计 `scripts/lp_long_horizon/adapters/registry.py` (read-only metadata) + 8 个 adapter file (4 existing + 4 new + 1 verify) |
| C (Base UniV3) | 新增 `evm_base_uniswap_v3.py`: pool_snapshot (slot0, liquidity, tick) + quote (10/20/100/500/1000/2000U) + fee_velocity (heuristic) + market_regime (NORMAL) |
| D (Base Aerodrome) | 新增 `evm_base_aerodrome.py`: classic (Solidly-style getReserves) + slipstream (marked adapter_ready=false due to custom tick math) |
| E (BSC V3) | 新增 `evm_bsc_pancakeswap_v3.py`: pool_snapshot (slot0, liquidity) + quote (QuoterV2 staticcall + fallback math) |
| F (BSC V2) | 新增 `evm_bsc_pancakeswap_v2.py`: getReserves + CPMM quote formula |
| G (Meteora check) | 验证 Meteora DLMM 16 verified pools 可被 long-horizon collector 读取 (re-use existing solana_rpc_readonly) |
| H (integrated smoke) | 用 expanded universe (72 池) 跑短 smoke, 选 12 池, 1 snapshot. 记录 chain_observed_count + protocol_observed_count. **不** 回退 placeholder. Base/BSC RPC 受限时必须清楚标记. |
| I (decision) | 5 conditions: observable≥45, chain≥3, protocol≥5, placeholder=0, no wallet/tx/probe. 决定 next stage. |
| J (final) | FINAL_VERDICT.json + ONEPAGE_CN.md + ARTIFACT_INDEX.md |
| K (test + safety) | pytest 22+ tests + go test + ps safety check |
| L (git publish) | commit + push |

## 6. 锁定字段 (5 项全 false/no)

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

## 7. 严禁 (本轮全部不触发)

- ❌ 不启动 12h / 24h / 48h / 72h / 7d retry
- ❌ 不启动 long-running collector
- ❌ 不启动 tmux / cron / systemd / daemon
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
- ❌ **不**修改 collector (本 stage 仅**新增** 5 adapter file, **不**改** collector 主程序)

## 8. 下一轮 (本 stage 推荐)

- **`LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1`** — 12h retry (per FINAL_VERDICT recommended_next_stage spec). 仅在 Stage I 5 conditions 全 met 时推荐. 否则:
- **`LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT`** — 修复 short smoke 中发现的 adapter 缺口
- **`PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA`** — 用户决定暂停

## 9. 结论

✅ **Stage A PASS** — 输入证据齐备, 5 缺失 adapter 明确, 现有 `scripts/lp_long_horizon/` Python helper package 完整可扩展. 进入 Stage B 设计 adapter registry + 5 阶段 C-G 接入 5 个 adapter.
