# LP Long Horizon Real Pool Universe Collector Fix V1 — One Pager

- stage: `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COLLECTOR_FIX_V1`
- run_id: `20260605_083000`
- branch: `feat/supabase-postgres-deployment`
- status: **PASS**

## 0. 一句话

修复 collector v1 + stage runner, 让 collector 接受 `--pool-universe` CLI, 写真实池 (5 real on-chain Solana addresses, 0 placeholder), 而非 hardcoded smoke placeholder. 短 smoke 验证成功. **严禁**自动启动 12h retry, 需用户单独审批 + 修 V3 supervisor finalize bug + EVM coverage fix.

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `collector_pool_universe_arg_supported` | **true** (CLI 新增 `--pool-universe` / `--max-pools` / `--max-snapshots` / `--run-id` / `--no-daemon`) |
| `stage_runner_pool_universe_arg_supported` | **true** (line 262 转发 `--pool-universe "${POOL_UNIVERSE_PATH}"` 给 collector) |
| `real_pool_universe_smoke_ran` | **true** (5 real pools × 1 snapshot) |
| `real_pool_universe_used` | **true** (33 真实池 universe, 5 selected) |
| `selected_real_pool_count` | **5** |
| `placeholder_pool_count` | **0** |
| `all_pools_are_real_on_chain` | **true** |
| `all_pool_addresses_real` | **true** (5 unique real on-chain Solana addresses, no `<smoke_pool_`) |
| `pool_snapshot_rows` | **5** |
| `quote_snapshot_rows` | **30** (5 × 6 notional) |
| `fee_velocity_rows` | **25** (5 × 5 windows) |
| `liquidity_distribution_rows` | **5** (5 × 1) |
| `market_regime_rows` | **7** (7 regime classifications) |
| `can_start_12h_real_universe_retry` | **true** (满足 5 项前置) |
| `recommended_next_stage` | **`LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1`** |

## 2. 5 selected_real_pools (全部 stable, 来自 orca_whirlpool)

| # | Chain | Protocol | Pool Type | Pool Address | Token Pair | Fee (bps) | TVL (USD) | 24h Vol (USD) |
|---|---|---|---|---|---|---|---|---|
| 1 | solana | orca_whirlpool | stable | `Hp53XEtt4S8SvPCXarsLSdGfZBuUr5mMmZmX2DRNXQKp` | SOL/JitoSOL | 1 | 31,439,174 | 20,121,510 |
| 2 | solana | orca_whirlpool | stable | `G2FiE1yn9N9ZJx5e1E2LxxMnHvb1H3hCuHLPfKJ98smA` | JTO/JitoSOL | 30 | 6,752,812 | 2,010,289 |
| 3 | solana | orca_whirlpool | stable | `9tXiuRRw7kbejLhZXtxDxYs2REe43uH2e7k1kocgdM9B` | PYUSD/USDC | 30 | 5,372,197 | 4,039,707 |
| 4 | solana | orca_whirlpool | stable | `68soqftZg4HL1Dcis5hMgkLKU9qyC8qbn5JzLhrxhgi9` | FDUSD/USDT | 30 | 5,276,535 | 2,938,005 |
| 5 | solana | orca_whirlpool | stable | `5xfKkFmhzNhHKTFUkh4PJmHSWB6LpRvhJcUMKzPP6md2` | wfragSOL/JitoSOL | 1 | 3,665,596 | 1,265,672 |

**5 池全部 stable_classified=true** (per `_select_universe_pools` 的 `stable first` 排序). 短 smoke (`--max-pools 5`) 优先选 stable 池, 验证 fix 正确. 大 smoke (`--max-pools 33`) 可覆盖 4 类协议 (orca clmm + stable, raydium_clmm, raydium_cpmm).

## 3. R0 限制 (诚实披露)

| 字段 | 状态 |
|---|---|
| `no_live_RPC` | **true** (无 live RPC, pool addresses / TVL / volume 全部从 universe JSON) |
| `tvl_volume_are_proxies_from_universe_JSON` | **true** |
| `no_feeGrowth_snapshot` | **true** (R0 无 tokenId) |
| `no_tokensOwed` | **true** |
| `no_real_fee_accrual` | **true** |
| `actual_fee_data_available` | **false** (R0 仅 schema) |
| `fee_proxy_used` | **true** |
| `heuristic_used` | **true** |
| `fee_estimate_confidence` | **`"low"`** |

**quote / fee / EV 仍**不真实可用 (R0 read-only + 无 live RPC). 但**关键**: 池 universe (pool_address / token_pair / TVL / volume / source_artifact) 是真实的, **不**是 placeholder.

## 4. 修复内容 (本 stage)

| 维度 | 修复前 | 修复后 |
|---|---|---|
| collector v1 CLI | `--mode`, `--pools-per-protocol`, `--out`, `--no-wallet`, `--no-tx`, `--no-bridge`, `--dry-run` | **+** `--pool-universe`, `--max-pools`, `--max-snapshots`, `--run-id`, `--no-daemon` |
| collector behavior (with `--pool-universe`) | (无, 跑 5 placeholder) | **写真实池**, 拒绝任何 `<smoke_pool_` / `<smoke_mint_`, universe parse 失败 → REFUSED (exit 11-20), 不得回退 placeholder |
| collector behavior (without `--pool-universe`) | 跑 5 placeholder, `smoke_placeholder_only=true` | 跑 5 placeholder, **`smoke_placeholder_used=true` + `real_pool_universe_used=false` 显式标注** |
| stage runner (line 262) | `--mode smoke --pools-per-protocol 5 --out ${CKPT_DIR}` | **`--pool-universe "${POOL_UNIVERSE_PATH}" --max-snapshots 1 --run-id "${RUN_ID}"`** (前 3 个 stage runner preflight 已 hard guard: universe 必须真实, 不得 placeholder) |
| 12h supervisor fail mode | 跑 placeholder (因为 collector 没接通 real universe) | 如重跑 12h, 跑真实池 (fix 验证通过短 smoke) |

## 5. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |

## 6. can_start_12h_real_universe_retry 评估

| 必要条件 | 状态 |
|---|---|
| `collector_pool_universe_arg_supported` | ✅ **true** |
| `stage_runner_pool_universe_arg_supported` | ✅ **true** |
| `real_pool_universe_smoke_ran` | ✅ **true** |
| `real_pool_universe_used` | ✅ **true** |
| `placeholder_pool_count` | ✅ **0** |
| `selected_real_pool_count > 0` | ✅ **5** |
| `pool_snapshot_rows > 0` | ✅ **5** |
| `all_pool_addresses_real` | ✅ **true** |
| `no_wallet/tx/probe` | ✅ **true** |

**5 项全部满足 → can_start_12h_real_universe_retry = true**.

但 12h retry 仍需 **3 项额外阻塞清除**:

| Blocker | 说明 |
|---|---|
| **V3 supervisor finalize bug** | `scripts/run_lp_long_horizon_readonly_stage_once.sh` line 435 + 493 用 bash `${REAL_GATE_PASS}` interpolated to lowercase `true` in Python ternary, 触发 NameError, fail-safe trap 写 default-zeros. 修法: `${REAL_GATE_PASS^^}` 大写, 或 `<<'PYEOF'` quoted heredoc |
| **EVM coverage** | 当前 12h 是 `partial_solana_real_pool_universe` (5 协议缺失: Meteora DLMM / Base Uniswap V3 / Base Aerodrome / BSC PancakeSwap V3 / BSC PancakeSwap V2). 12h retry 需先做 Meteora DLMM + Base/BSC adapter coverage fix |
| **User manual approval** | 需用户单独审批 12h retry 短语 (`APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=12h mode=readonly no_probe=true`), 单独 FINAL_VERDICT, 单独 stage 启动 |

## 7. 严禁 (本轮全部不触发)

- ❌ 不启动 12h retry (本轮仅短 smoke 验证 fix, **不** 启动 12h)
- ❌ 不启动 24h / 48h / 72h / 7d
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
- ❌ **不**修改 V2 12h FINAL_VERDICT (FAIL verdict 保留)
- ❌ **不**修改 V2 6h FINAL_VERDICT + V2 6h corrected verdict
- ❌ **不**修改 V2 12h corrected verdict
- ❌ **不**修改 12h node report (commit 90cb18a)
- ❌ **不**修复 V3 supervisor finalize bug (本轮 read-only, 修复留给下一轮)

## 8. 下一轮建议 (用户决策)

| 选项 | 含义 |
|---|---|
| **接受本 stage fix + 触发 12h retry** | 推荐路径. 需先修 V3 supervisor finalize bug + EVM coverage fix + 用户单独审批. 12h retry 写真实池 (collector 已接通), 5 missing protocols 仍 partial. |
| **触发下一轮 `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COLLECTOR FIX_REPEAT`** | 进一步扩展 fix, e.g. 加 placeholder detection in pool_address format check, 加 real_pool_universe_used assertion in stage runner preflight, 扩大 smoke coverage |
| **触发 `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA`** | 用户决定暂停, 等其他 stage 补完再继续 |
| **触发 `STOP_LP_RESEARCH_NOW`** | 用户决定停止 LP research (不建议, edge_proven=no, 用户意图是 continuous observation) |

## 9. 关键数据点

- **12h 节点报告 (commit 90cb18a)** 显示 `all_pools_are_smoke_placeholder=true, 60 placeholder rows, 0 quote/fee/ev ready`. 这是**当前 12h 数据**, **不**是本 stage 短 smoke.
- **本 stage 短 smoke** 显示 `5 real pools, 0 placeholder, real TVL 31M/6M/5M/5M/3M USD, real 24h vol`. 是 fix 验证.
- 12h 节点报告**不**应被本 stage 短 smoke 覆盖. 12h 节点报告 60 placeholder rows 仍正确 (因为 12h supervisor 跑的是 commit 23fed9d 之前的 collector).

## 10. 后续

本 stage 完成, 17 个新文件 commit 在 `feat/supabase-postgres-deployment` 分支. 用户可在下一轮决定:
1. 接受本 fix + 触发 `LP_LONG_HORIZON_12H_COLLECTOR_FIX_REPEAT` (修 V3 supervisor bug, 然后 12h retry with real pool universe)
2. 直接触发 `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1` (需手动审批)
3. 暂停或停止

严禁 (per LP strategy research freeze): probe / canary / live / paper / wallet / tx / auto-12h.
