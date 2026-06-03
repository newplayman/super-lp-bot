# Multichain Pool Readiness Probe — Stage E

- stage: `LP_MULTICHAIN_DEX_LP_DISCOVERY_AND_SURVIVAL_EV_V1`
- run_id: `20260603_051605`
- script: `scripts/lp_evm_v3_pool_readiness_probe_v1_readonly.py`

## 1. 关键结果

```text
pools_probed         = 142
state_ready          = 134
tick_ready           = 142
cost_ready           = 142
quote_ready          = 0      (v1 QuoterV2 selector encoding 已知有问题; v2 待修)
high_confidence      = 134    (state + tick + cost 全 ready)
```

## 2. 字段解读

| 字段 | 含义 |
|---|---|
| `state_ready` | slot0() + liquidity() 都返回非零 |
| `tick_ready` | slot0() tick 解析成功 |
| `cost_ready` | eth_gasPrice 返回非零 |
| `quote_ready` | 6 个 notional 中至少 1 个 QuoterV2 quote 成功 (v1 暂时 0) |
| `confidence` | 5 个组件 (state/tick/cost/quote/log) 准备好比例 |
| `capacity_N` | notional N 在该池的容量评分 (基于 liquidity / amount_in ratio) |
| `gas_cost_proxy` | 350k gas × gas_price × native_USD (粗略 LP 交易成本) |

## 3. 已知缺口 (v1 → v2)

- **quote_ready=0** — QuoterV2 真实 ABI 是 `quoteExactInputSingle((address,address,uint256,uint24,uint160))` tuple inline；v1 用简化编码，部分 revert。Stage E **不**修复；v2 monitor candidate (per upstream) 应该重新实现。
- `swap_log_count` 大概率是 0 或 -1（public RPC 不支持 eth_getLogs 长时间范围）。
- `volume_usd_proxy_24h` / `pool_fee_usd_proxy_24h` 留空，待 v2 接 subgraphs。

## 4. chain 分布

按 chain 列出 state_ready 池子数（来自探针）：

| chain | pool_exists | state_ready | tick_ready | cost_ready |
|---|---|---|---|---|
| Base | 21 | (variable) | 21 | 21 |
| BSC | 25 | (variable) | 25 | 25 |
| Arbitrum | 24 | (variable) | 24 | 24 |
| Optimism | 12 | (variable) | 12 | 12 |
| Polygon | 32 | (variable) | 32 | 32 |
| Ethereum | 28 | (variable) | 28 | 28 |

具体每个池的字段在 `multichain_pool_readiness_probe.csv` / `.json` 里。

## 5. 安全断言

```text
this_stage_only_did_read_only_rpc = true
wallet_or_tx_touched              = false
signer_created                    = false
wallet_client_created             = false
eth_sendTransaction_called        = false
eth_sendRawTransaction_called     = false
can_run_probe_now                 = false
```

## 6. 下游使用

Stage F (survival EV model) 用 `state_ready=true` 子集；
Stage G (out-of-range risk) 用 `state_ready=true` 子集；
Stage H (scoring) 用 `state_ready=true` + Stage F/G 结果组合。
