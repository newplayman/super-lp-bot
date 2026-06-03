# EVM Standard V3 Multichain Discovery — Stage D

- stage: `LP_MULTICHAIN_DEX_LP_DISCOVERY_AND_SURVIVAL_EV_V1`
- run_id: `20260603_051605`
- script: `scripts/lp_evm_standard_v3_multichain_discovery_v1_readonly.py`
- 全部 read-only；只调 `eth_chainId` / `eth_blockNumber` / `eth_call(factory, getPool)` / `eth_gasPrice`

## 1. 关键结果

| chain | chain_id | queries | rpc_ready | pool_exists_count |
|---|---|---|---|---|
| Base | 8453 | 48 | ✅ | 20 |
| BSC | 56 | 28 | ✅ | 25 |
| Arbitrum | 42161 | 32 | ✅ | 24 |
| Optimism | 10 | 24 | ✅ | 12 |
| Polygon | 137 | (待 v2 重跑) | ✅ | (待定) |
| Ethereum | 1 | (待 v2 重跑) | ✅ | (待定) |

**v1 总计**：6 chains × 7 protocols，134 candidate queries，**81 pools exist** (其中 Base/BSC/Arbitrum/Optimism 4 chain 完成；Polygon/Ethereum 因默认 public RPC 返回 chain_id=0 失败，本轮已升级 RPC fallback 列表，将重跑)。

## 2. 已发现的 top pools（per chain, pool_exists=true 子集）

### 2.1 Base（20 池）

主要包含：

- WETH/USDC 100: 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 — **上游 NO_GO 候选**（fee 100）
- WETH/USDC 500: 多个
- WETH/USDC 3000 / 10000
- WETH/USDT 各 fee tier
- cbBTC/USDC / cbBTC/WETH（fee 100/500）
- USDC/USDT（fee 100）
- PancakeSwap V3 WETH/USDC, WETH/USDT 各 fee tier

### 2.2 BSC（25 池）

- USDT/WBNB fee 100: 0x172fcd41e0913e95784454622d1c3724f546f849 — **上游 BSC best pool**（fee 100, ev=-0.0156）
- USDT/WBNB fee 500 / 2500 / 10000
- USDC/WBNB fee 100/500/2500/10000
- WETH/USDT fee 100/500/2500/10000
- BTCB/USDT fee 500/2500/10000
- BTCB/WBNB fee 500/2500/10000
- USDC/USDT fee 100

### 2.3 Arbitrum（24 池）

- WETH/USDC fee 100/500/3000/10000
- WETH/USDC.e fee 100/500/3000/10000
- WETH/USDT fee 100/500/3000/10000
- WETH/DAI fee 100/500/3000/10000
- WBTC/USDC fee 500/3000
- WBTC/WETH fee 3000
- USDC/USDT fee 100
- USDC/DAI fee 100

### 2.4 Optimism（12 池）

- WETH/USDC fee 100/500/3000
- WETH/USDT fee 100
- WETH/DAI fee 100
- WBTC/USDC fee 500
- WBTC/WETH fee 500
- USDC/USDT fee 100
- + PancakeSwap V3 失败（factory address 在 Optimism 上不存在）

### 2.5 Polygon / Ethereum（待 v2 重跑）

默认 public RPC 返回 `chain_id=0`（rate-limit）。脚本升级了 fallback RPC 列表，重跑后会写入。

## 3. discovery_confidence 解读

- `pool_exists=true` 的池子: `discovery_confidence=0.95`（已确认 deploy）
- `pool_exists=false` 的池子: `discovery_confidence=0.0`（factory getPool 返回 0x0；说明该 pair/fee 没 deploy）
- RPC 失败的: `rpc_ready=false`，`chain_id_observed=0`，整个 chain 视为 `needs_data`

## 4. 不在本轮做的事

- ❌ 不 quote readiness probe（Stage E 才做）
- ❌ 不算 fee velocity（Stage F 才做）
- ❌ 不调 slot0 / tickSpacing（Stage E 才做）
- ❌ 不调 QuoterV2（Stage E 才做）
- ❌ 不 wallet approve / mint / swap

## 5. 安全断言

```text
this_stage_did_read_only_rpc = true
wallet_or_tx_touched          = false
signer_created                = false
signer_call_site              = (none)
wallet_client_created         = false
can_run_probe_now             = false
```

## 6. 字段列表

完整字段见 `evm_standard_v3_multichain_discovery.csv` / `.json`。每个 row 包含：

```text
chain, chain_id, rpc_url, protocol, factory, npm,
token_a_symbol, token_b_symbol, fee_tier,
pool_address, pool_exists,
metadata_ready, quote_ready, tick_ready, gas_ready,
discovery_confidence, invalid_reason
```

> 详细 quote/tick/fee_velocity 字段在 Stage E 的 `multichain_pool_readiness_probe.{csv,json}` 里。
