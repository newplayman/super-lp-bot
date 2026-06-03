# Overnight Run Bootstrap — Stage C

- stage: `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1`
- run_id: `20260603_174815`
- branch: `feat/supabase-postgres-deployment`
- head_before: `404ddd1`

## 0. 启动方式

```text
runner_script  = scripts/lp_meteora_dlmm_known_pool_feed_expansion_overnight_v1_readonly.sh
runner_inner   = scripts/lp_meteora_dlmm_known_pool_feed_expansion_overnight_v1_readonly.js
tmux_session   = lp_meteora_known_pool_expansion_20260603_174815
sdk_install    = /tmp/lpbot_meteora_dlmm_sdk_overnight_20260603_174815/
report_dir     = reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/
logs           = reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/logs/run.log
checkpoint     = reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/checkpoint/state.json
data           = reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/data/
```

## 1. Runner 特性

- `--run-id <id>` : 必填
- `--output-dir <dir>` : 必填
- `--max-hours 10` : wallclock 上限 (default 10)
- `--checkpoint-minutes 60` : checkpoint 频率 (default 60)
- `--max-pools 50` : candidate 上限
- `--min-pools 20` : candidate 下限
- `--mode all` : 只支持 "all" (覆盖 D-J)
- **Resume**: 启动时如果发现 `checkpoint/state.json` 存在，从上一阶段继续

## 2. 输出文件 (each stage)

| stage | files |
|---|---|
| D | data/candidate_raw.json, METEORA_CANDIDATE_SOURCE_COLLECTION_CN.md, meteora_candidate_source_collection.csv, meteora_candidate_source_collection.json |
| E | data/chain_verification.json, METEORA_POOL_CHAIN_VERIFICATION_CN.md, meteora_pool_chain_verification.csv, meteora_pool_chain_verification.json |
| F | data/decoded_pools.json, METEORA_BATCH_POOL_SNAPSHOT_CN.md, meteora_batch_pool_snapshot.csv, meteora_batch_pool_snapshot.json |
| G | data/bin_liquidity.json, data/bin_liquidity_summary.json, METEORA_BATCH_BIN_LIQUIDITY_CN.md, meteora_batch_bin_liquidity.csv, meteora_batch_bin_liquidity.json |
| H | data/quotes.json, METEORA_BATCH_QUOTE_CN.md, meteora_batch_quote.csv, meteora_batch_quote.json |
| I | data/scored_pools.json, METEORA_POOL_SCORING_CN.md, meteora_pool_scoring.csv, meteora_pool_scoring.json |
| J | data/survival_ev.json, METEORA_BATCH_SURVIVAL_EV_CN.md, meteora_batch_survival_ev.csv, meteora_batch_survival_ev.json |
| K+L | METEORA_EXPANDED_FEED_CANDIDATE_DECISION_CN.md/json, FINAL_VERDICT.json, ONEPAGE_CN.md, ARTIFACT_INDEX.md |

## 3. 安全 invariant (硬编码)

- 不读 Solana 私钥 / seed phrase / keypair
- 不 instantiate signer / wallet adapter
- 不构造 transaction
- 不调用 sendTransaction / sendRawTransaction
- 不调用 swap transaction builder
- 不调用 open_lp / close_lp / collect_fee / addLiquidity / removeLiquidity
- 不 bridge
- 不启动 live / canary / paper
- 不写 production positions
- 不覆盖 shadow 表
- 不修改 EVM executor v2
- 不释放 hard-disable
- can_run_probe_now = false (locked)
- tiny_canary_allowed = "no" (locked)

## 4. Runner safety code path

Runner 不 import 任何 wallet / signer / tx builder SDK。

`@meteora-ag/dlmm` SDK only exposes:
- `DLMM.create(connection, publicKey, opts)` — pool handle (read-only)
- `dlmmPool.getActiveBin(connection)` — active bin id + price
- `dlmmPool.getFeeInfo()` — base/max fee
- `dlmmPool.getBinArrayForSwap(swapYtoX, binArrayIndex)` — bin array pubkey list
- `dlmmPool.swapQuote(connection, inAmount, swapYtoX, allowedSlippage, binArrays, isPartialFill, blockTimestamp)` — **returns a quote object only**, does NOT construct a transaction, does NOT sign, does NOT send

runner 严格只调用上述方法；不调用 SDK 的 pos-create / addLiquidity / removeLiquidity / closePosition / claimFee / claimReward / sendTransaction 等任何会动链状态的 API。

## 5. Wallclock budget (max 10h)

| phase | budget (rough) |
|---|---|
| D: collect | 60s |
| E: chain verify | 5-15 min (1 RPC call per candidate) |
| F: SDK decode | 5-15 min (1 DLMM.create + 2-3 sub-calls per pool) |
| G: bin array read | 30-60 min (10+ pools × 5-15 bin arrays × single-account read) |
| H: quote | 30-60 min (10+ pools × 3 notionals × 2 directions) |
| I: scoring | <1 min |
| J: survival EV | 1-2 min (CPU only) |
| K+L: decision + final | <1 min |
| Total estimated | 1.5-3 hours |

If wallclock exceeds 10h, runner aborts with checkpoint. Partial final emitted.

## 6. Checkpoint format

```json
{
  "run_id": "20260603_174815",
  "phase": "D_collect|E_verify|F_decode|G_bin_liquidity|H_quote|I_score|J_ev|done",
  "start_time": "2026-06-03T17:48:15Z",
  "last_update": "2026-06-03T17:50:00Z",
  "wallclock_ms_used": 105000,
  "max_wallclock_ms": 36000000,
  "error_count": 0,
  "rpc_error_count": 0,
  "counts": {
    "candidate_raw": 32,
    "verified": 12,
    "decoded_success": 10,
    "quote_success": 5,
    "ev_rows": 1680
  },
  "aborted": false,
  "abort_reason": null
}
```

## 7. 启动 smoke (2 分钟)

启动后必须确认：

- tmux session 存在
- `logs/run.log` 在更新
- `checkpoint/state.json` 已生成
- 没有 forbidden process 在跑
- 没有 wallet / keypair / transaction 行为

详细见 `TMUX_START_HEALTHCHECK_CN.md`。

## 8. 下一阶段

进入 Stage D — candidate source collection。
