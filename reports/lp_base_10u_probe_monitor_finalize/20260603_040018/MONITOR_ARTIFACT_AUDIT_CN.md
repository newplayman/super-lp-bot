# Monitor Artifact Audit — Stage D

- stage: `LP_BASE_10U_PROBE_MONITOR_FINALIZE_AND_GO_NOGO_V1`
- run_id: `20260603_040018`
- source: `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor/`

## 1. 关键统计（实测）

| 字段 | 值 | 备注 |
|---|---|---|
| `checkpoint_count` | **47** | iter 1–47 |
| `first_checkpoint_time` | 2026-06-02T19:44:19Z | 启动后立即第一个 |
| `last_checkpoint_time` | 2026-06-03T03:34:19Z | max_hours_reached 前最后一个 |
| `monitor_duration_minutes` | **470** (≈7h 50m) | 与 max_hours=8 一致 |
| `rpc_failure_count` | **0** | 47/47 RPC 成功 |
| `market_safe_true_count` | **0** | 0% |
| `market_safe_false_count` | **47** | 100% |
| `stop_condition_count` | **47** | 每一次都至少有一个 stop condition active |
| `tick_drift_min` | **-722** | 03:34 时最大漂移 |
| `tick_drift_max` | **-318** | 19:54 时最小漂移 |
| `tick_drift_threshold` | 200 | 来自 armed runner v2 |
| `gas_estimate_min_wei` | **6000000** (0.006 gwei) | Base 极低 |
| `gas_estimate_max_wei` | **14018528** (0.014 gwei) | 第一次 checkpoint |
| `allowance_status_last` | **5000000** (5 USDC) | < 10 USDC 阈值 |
| `balance_status_last` | **21774783** (21.77 USDC) | 充裕 |

## 2. 时间序列要点

- **drift 单调恶化**（最差时）-722：20:00 前在 -318~-389 区间波动；22:00 后开始 -414~-485；23:00 后 -590~-664；02:00 后 -615~-673；03:34 顶峰 -722。
- **current_tick_inside_new_range 始终 true**（动态 ±200 范围随 tick 调整，所以一直包住）
- **fresh_approval_required 始终 true**（USDC allowance 5M < 10M 阈值）
- **gas 始终 0.006–0.014 gwei**（Base L2 极低）
- **block_number 单调增长 46820056 → 46834161**（47 个 checkpoint 间 14105 个块，~6.5 blocks/min，符合 Base L2 出块节奏）

## 3. 漂移 vs 上游 review 对比

| 时间点 | current_tick | drift_ticks | 漂移 vs frozen -200443 |
|---|---|---|---|
| 上游 review 20260602_182402 | -200747 | -304 | > 200 阈值 |
| preflight 20260602_193517 | -200828 | -385 | > 200 |
| monitor iter=1 20260602_194419 | -200828 | -385 | > 200 |
| monitor iter=10 20260602_211611 | -200806 | -363 | > 200 |
| monitor iter=20 20260602_225850 | -201016 | -573 | > 200 |
| monitor iter=30 20260603_004033 | -200991 | -548 | > 200 |
| monitor iter=40 20260603_022232 | -201074 | -631 | > 200 |
| **monitor iter=47 (last) 20260603T033419** | **-201165** | **-722** | **> 200 (大量超标)** |

结论：漂移**不是临时波动**，而是**持续单边恶化**（USDC 相对 WETH 在 8h 内持续升值 / WETH 持续贬值；或 WETH/USDC 价下降）。任何时候 tick 都偏离 frozen center 至少 318 ticks，远超 200 阈值。

## 4. quote_drift 字段（v1 monitor 暂未收集）

> 注意：v1 monitor 写 18 个字段到 readiness_timeseries.csv，**不含 quote_drift**。
> 这是 v1 设计的已知缺口（已在 `MONITOR_FINALIZE_SCHEMA_CN.md` 标记为 v2 monitor 候选）。
> 任何 GO 决策不能基于 quote_drift 缺失阻断 GO，但应在 schema v2 加上。

## 5. 最新 checkpoint 关键字段

```text
ts_iso                                = 2026-06-03T03:34:19Z
iteration                             = 47
chain_id                              = 8453
chain_id_match                        = true
block_number                          = 46834161
wallet_eth_wei                        = 90470751043807 (~0.0905 ETH)
usdc_balance_raw                      = 21774783 (~21.77 USDC)
weth_balance_raw                      = 2470131003793800 (~0.00247 ETH)
usdc_allowance_raw                    = 5000000 (5 USDC)
weth_allowance_raw                    = 2470131003793800
current_tick                          = -201165
drift_ticks                           = -722
proposed_tick_lower                   = -201365
proposed_tick_upper                   = -200965
current_tick_inside_new_range         = true
fresh_approval_required               = true
gas_price_wei                         = 13455641 (~0.013 gwei)
any_stop_condition_active             = true
market_safe_for_execution_candidate   = false
```

## 6. 一句话

47 次 checkpoint **0 次** market_safe；漂移 -318 → -722（恶化）；fresh_approval_required 持续 true；gas 极低；RPC 稳定；最新 tick 仍在动态范围内但远超 frozen center。**市场对 10U probe 长期不适合**。
