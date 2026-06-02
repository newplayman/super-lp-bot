# Armed Runner Preflight Smoke — LP_BASE_10U_PROBE_OVERNIGHT_ARMED_RUNNER_BUILD_AND_READONLY_MONITOR_V1

- stage: `LP_BASE_10U_PROBE_OVERNIGHT_ARMED_RUNNER_BUILD_AND_READONLY_MONITOR_V1`
- run_id: `20260602_193517`
- mode: `armed_runner_v1 --mode preflight`
- read-only: **是**（仅 eth_chainId / eth_getBalance / eth_call / dynamic_tick_range_recompute）
- 不签、不发、不构造 signer

## 1. 跑法

```bash
python3 scripts/lp_base_10u_probe_armed_runner_v1.py \
  --mode preflight \
  --run-id 20260602_193517 \
  --wallet 0xb05b2872ace4564ff247555b6f7b097d31f3d835 \
  --notional 10 \
  --hold 15m \
  --no-send \
  --out-dir reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517
```

## 2. 关键读数（2026-06-02 21:35 UTC）

| 字段 | 值 | 解读 |
|---|---|---|
| `chain_id_observed` | 8453 | Base mainnet ✅ |
| `chain_id_match` | true | 与冻结 chain_id 一致 |
| `wallet_eth_balance_wei` | 90470751043807 ≈ 0.0905 ETH | 够付 gas 估算（0.0905 ETH） |
| `usdc_balance_raw` | 21774783 ≈ 21.77 USDC | 足以 10U probe 一次 |
| `weth_balance_raw` | 2470131003793800 ≈ 0.00247 ETH | 备用，几乎不需要 |
| `usdc_allowance_raw` | 5000000 = 5 USDC | **< 10 USDC**，fresh_approval_required 触发（这是上游就预期的）|
| `weth_allowance_raw` | 2470131003793800 | 充裕（不重要，因为 10U 入场只需 USDC 路径）|
| `pool_liquidity_raw` | 0x5b9b2466a69add1 | 池子有真实流动性 |
| `current_tick` (来自 dynamic_tick_range) | **-200867** | 上游 review 时是 -200747；**drift 累计变大** |
| `drift_ticks` | **-424** | 上游 review 时是 -304；**现已 -424**（> 200 阈值）|
| `proposed_tick_lower / upper` | -201067 / -200667 | 动态范围 |
| `current_tick_inside_new_range` | true | 仍在范围内 |
| `fresh_approval_required` | **true** | 任何 armed runner 真要发，必须重新读 USDC 余额、重新做 approveExact |
| `tick_outside_new_range` | false | ok |
| `any_stop_condition_active` | **true** | 因 `fresh_approval_required=true` |

## 3. 结论

- `preflight_smoke_ran = true`
- `preflight_smoke_pass = WARN`（**不是 PASS**：因为 `any_stop_condition_active=true`，原因是有 fresh approval 待签）
- 含义：**市场已变更** — 距 frozen center -200443 漂移 424 ticks，已超 200 阈值。任何 armed runner 真要执行，必须先做 fresh approval（重新读 allowance + 重新构建 approveExact 交易）。本阶段 armed runner 仍然不签不发，所以**这一项不构成对今夜 monitor 的阻断**；它仅作为 monitor 的 baseline 之一被记录。
- tickSpacing `eth_call` revert（`pool_tick_spacing_error`）属正常：Base 上很多池子的 `tickSpacing()` 走另一 selector `0xd0c93a7c`；本阶段不阻塞 monitor。

## 4. 与上游 review 的漂移对比

| 时间 | current_tick | drift from -200443 |
|---|---|---|
| 上游 review 20260602_182402 | -200747 | -304 |
| 本 preflight 20260602_193517 | -200867 | -424 |
| 差 | -120 | -120 ticks（约 0.12 USDC 单边）|

市场在这 ~1 小时内持续下行。Monitor 启动后会每 10 分钟记录新读数；明早收尾时若有反向回 -200443 附近，则可以减少 fresh approval 焦虑。

## 5. 安全断言（本轮守住）

```text
wallet_or_tx_touched                  = false
can_run_probe_now                     = false
execution_allowed_now                 = false
send_hard_disable_active              = true
tiny_canary_allowed                   = no
edge_proven                           = no
fresh_approval_required               = true
preflight_only_used_readonly_rpc      = true
private_key_loaded                    = false
mnemonic_loaded                       = false
keystore_loaded                       = false
signer_created                        = false
wallet_client_created                 = false
eth_sendTransaction_called            = false
eth_sendRawTransaction_called         = false
```
