# 多链 DEX Universe 规划

- stage: `LP_MULTICHAIN_DEX_LP_DISCOVERY_AND_SURVIVAL_EV_V1`
- run_id: `20260603_051605`

## 0. 规划原则

1. **不**重新发明 EVM V3 ABI / pool layout — 复用 `scripts/lp_base_10u_probe_executor_v2.py` 的 `dynamic_tick_range_recompute`、`encode_balance_of`、`encode_allowance` 路径。
2. **不**触碰生产路径；只新增 read-only discovery / probe / scoring 脚本。
3. **不**接受 one-shot execution phrase；**不**解除 v2 hard-disable。
4. wallet 资金仅在 Base（$26.84），BSC $0；任何非 Base / 非 BSC 候选**只能**列为 **"watch / needs_data / reject"** 或提示用户准备资金，**不**自动 bridge / swap。
5. spec 三层优先级：
   - P0 = EVM 标准 V3（ABI 兼容；立刻能跑）
   - P1 = EVM 非标准 / 需自定义 parser
   - P2 = 非 EVM（Solana Meteora / Orca / Raydium 单独 connector）

## 1. P0：标准 EVM V3（可复用 v2 pipeline）

| chain | chain_id | protocol | factory | NPM | quote_via | fee_tiers |
|---|---|---|---|---|---|---|
| Base | 8453 | Uniswap V3 | `0x33128a8fC17869897dcE68Ed026d694621f6FDfD` | `0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1` | QuoterV2 `0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a` (read-only staticcall) | 100/500/3000/10000 |
| Base | 8453 | PancakeSwap V3 | `0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865` | `0x46A15B0bda11dd51589E78B4F8b815a9D2887F5e` | QuoterV2-like `0xB048Bbc1e6C61bC9F5c5F5a0cE3D2E7d6f9c2b9B4` (verify) | 100/500/2500/10000 |
| BSC | 56 | PancakeSwap V3 | `0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865` | `0x46A15B0bda11dd51589E78B4F8b815a9D2887F5e` | `0xB048Bbc1e6C61bC9F5c5F5a0cE3D2E7d6f9c2b9B4` (verify) | 100/500/2500/10000 |
| Arbitrum | 42161 | Uniswap V3 | `0x1F98431c8aD98523631AE4a59f267346ea31F984` | `0xC36442b4a4522E871399CD717aBDD847Ab11FE88` | QuoterV2 `0x61fFE014bA17989E6c287eC286C7beb5BA65D1e7` (verify) | 100/500/3000/10000 |
| Arbitrum | 42161 | PancakeSwap V3 | (deployed) | (verify) | (verify) | 100/500/2500/10000 |
| Optimism | 10 | Uniswap V3 | `0x1F98431c8aD98523631AE4a59f267346ea31F984` | `0xC36442b4a4522E871399CD717aBDD847Ab11FE88` | QuoterV2 `0x61fFE014bA17989E6c287eC286C7beb5BA65D1e7` (verify) | 100/500/3000/10000 |
| Polygon | 137 | Uniswap V3 | `0x1F98431c8aD98523631AE4a59f267346ea31F984` | `0xC36442b4a4522E871399CD717aBDD847Ab11FE88` | QuoterV2 `0x61fFE014bA17989E6c287eC286C7beb5BA65D1e7` (verify) | 100/500/3000/10000 |
| Ethereum | 1 | Uniswap V3 | `0x1F98431c8aD98523631AE4a59f267346ea31F984` | `0xC36442b4a4522E871399CD717aBDD847Ab11FE88` | QuoterV2 `0x61fFE014bA17989E6c287eC286C7beb5BA65D1e7` (verify) | 100/500/3000/10000 |

> 注：括号 `(verify)` 表示本阶段需要 RPC `eth_call(factory, getPool(tokenA, tokenB, fee))` 反查；不是 hard-code。
> 因为多链 deploy 经常有 proxy / version drift；不能用上游 spec 写死的地址。改用 discovery 路径：先 `eth_chainId` → 根据 chain 查 factory → factory.getPool。
> 在 `scripts/lp_evm_standard_v3_multichain_discovery_v1_readonly.py` 里把 factory / npm / quoter 列在 chain-config dict，逐链查。

### 1.1 P0 candidate pairs

每条链至少尝试：

| 优先级 | pair | 备注 |
|---|---|---|
| 1 | WETH/WUSDC（即 wrapped native / native USDC） | 高流动性基线 |
| 2 | WETH/WUSDT | USDT 路径（特别在 BSC、Polygon） |
| 3 | WBTC/cbBTC/WETH | 不同链叫法不同（Ethereum WBTC；Base cbBTC） |
| 4 | WBTC/cbBTC/USDC | 稳定-波动配对 |
| 5 | USDC/USDT | 稳定-稳定 |
| 6 | USDC/DAI | 仅在 DAI 部署链（Ethereum、Polygon、Optimism、Arbitrum） |
| 7 | (protocol-specific high-volume) | 例：Base USDC/WETH 也叫 0x72ab388e；BSC USDT/WBNB 0x172fcd41 |

### 1.2 P0 已知候选（来自上游）

- Base WETH/USDC 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 fee 100 — 上游 NO_GO
- BSC USDT/WBNB 0x172fcd41e0913e95784454622d1c3724f546f849 fee 100 — best of BSC EV $-0.0156

## 2. P1：EVM 非标准 / 需自定义 parser

| 链 | 协议 | pool type | 备注 |
|---|---|---|---|
| Base | Aerodrome Slipstream | CL V3 (forks Uniswap V3 with hooks) | factory `0xAero`. 多数 slots 兼容 V3；custom fee/hooks 字段需 skip |
| Optimism | Velodrome V3 / Superchain | CL V3 | factory `0x0A ` 类似 Slipstream |
| Ethereum | Curve stable pools | stableswap | 完全不同 ABI；需独立 parser |
| Ethereum/Polygon/Optimism/Arbitrum | Curve tricrypto | stableswap | 同上 |
| 多链 | Balancer weighted / stable | weighted math | 完全不同 ABI |
| BSC/其它 | PancakeSwap V2 / stable pools | constant product (Uniswap V2 类) | getReserves() 而非 slot0 |

P1 路径**只**写 parser 框架；不写**任何** EV 模型（v1）。Stage G / H / F 只对 P0 跑数据。

## 3. P2：非 EVM（单独 connector 设计）

| 链 | 协议 | 类型 | 备注 |
|---|---|---|---|
| Solana | Meteora DLMM | bin-based CLMM | 完全不同的 pool layout；id 是 pubkey |
| Solana | Meteora DAMM v2 | constant-product + dynamic fee | 2025 launch |
| Solana | Orca Whirlpool | CL V3 fork | tick array layout |
| Solana | Raydium CLMM | CL V3 fork | 跟 Orca 类似 |

P2 路径**只**写 spec / connector 设计稿；不写 v1 实际 connector（需要 JSON-RPC via solana web3.js；当前 Python toolchain 没有 solana-py + 没有 wallet）。

## 4. RPC 规划（read-only）

P0 chains 需要每条链至少 1 个稳定的 public RPC（`eth_call` / `eth_chainId` / `eth_blockNumber` / `eth_getBalance` / `eth_estimateGas`）。优先：

- Base: `https://mainnet.base.org` (已有 `https://base-rpc.publicnode.com` 作为备)
- BSC: `https://bsc-dataseed.binance.org` 或 `https://bsc.publicnode.com` (上游 BSC pipeline 用)
- Arbitrum: `https://arb1.arbitrum.io/rpc` (public, 有 rate limit)
- Optimism: `https://mainnet.optimism.io`
- Polygon: `https://polygon-rpc.com`
- Ethereum: `https://eth.llamarpc.com` 或 `https://cloudflare-eth.com`

> **不**写入脚本任何 private RPC；`grep -i 'secret\|password\|database_url'` 不阻断；URL 是 public 的。

## 5. 不在本轮做

- ❌ Solana connector 实际代码（仅 spec）
- ❌ Curve / Balancer 实际 quote（仅 spec）
- ❌ 任何 RPC 上 broadcast 类调用
- ❌ 任何对 wallet 的 swap / bridge
- ❌ 修改策略自动交易路径
- ❌ 解除 v2 hard-disable
- ❌ 改写 v1 / v2 executor
- ❌ 接受 one-shot execution phrase
- ❌ 把 `tiny_canary_allowed` 设成 yes

## 6. 实现路径（接下来几个 stage 的输出）

- Stage D: `lp_evm_standard_v3_multichain_discovery_v1_readonly.py` 跑 P0 6 chains × N pairs × 4 fees；输出 discovery CSV
- Stage E: 对发现到的 `pool_exists=true` 池子做轻量 probe：slot0, liquidity, decimals, quote readiness (10/20/100/500/1000/2000U)
- Stage F: survival EV model (5 scenarios × 6 notional × 9 hold_window)
- Stage G: out-of-range risk (p50/p90/p95 tick move)
- Stage H: candidate scoring + top 5 by notional
- Stage I: cross-chain probe route decision
- Stage J: next stage decision
