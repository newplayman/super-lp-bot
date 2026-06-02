# Base 候选池发现（从既有 artifacts）

- stage: `LP_EVM_WALLET_ADDRESS_CROSSCHAIN_DRY_RUN_ROUTER_V1`
- phase: G

## 钱包在 Base 上实际持有的 token

| symbol | address | USD |
|---|---|---|
| WETH | `0x4200...0006` | $4.89 |
| USDC | `0x8335...2913` | $21.77 |

（其余 Base token 余额为 0：USDT、cbBTC、DAI）

## 候选筛选（来自 5 个 cost-ready Base V3 池）

| pool | pair | fee_tier | quote@20U | tick | cost | fee | wallet match | best EV @20U | status |
|---|---|---|---|---|---|---|---|---|---|
| `0x9c087eb7...` | VIRTUAL/WETH | — | ✓ | ✓ | ✓ | ✓ | ✓ (WETH 命中) | **+$0.0376** | **BASE_DRY_RUN_READY** |
| `0x72ab388e...` | WETH/USDC | 100 | ✓ | ✓ | ✓ | ✓ | ✓ (WETH+USDC 双命中) | -$0.0600 | **BASE_DRY_RUN_READY** |
| `0xd0b53d92...` | USDC/WETH | — | ✓ | ✓ | ✓ | ✓ | ✓ (USDC+WETH 双命中) | -$16.58 | BASE_DRY_RUN_READY (EV proxy 异常) |
| `0xb94b2233...` | cbBTC/USDC | — | ✓ | ✓ | ✓ | ✓ | ✓ (USDC 命中) | -$20.28 | BASE_DRY_RUN_READY (EV proxy 异常) |
| `0xc211e1f8...` | cbBTC/WETH | — | ✓ | ✓ | ✓ | ✓ | ✓ (WETH 命中) | -$20.61 | BASE_DRY_RUN_READY (EV proxy 异常) |

**dry_run_ready_count = 5**

## 候选之间的实操差异（钱包能否真实开仓）

| 候选 | 钱包需要的 token | 钱包是否实际持有 | 备注 |
|---|---|---|---|
| WETH/USDC (`0x72ab388e...`) | WETH ≈ $5 + USDC ≈ $5 (for 10U LP) | **两端都有** | **最适合做 dry-run + 未来 probe**：钱包余额双命中、且有 Uniswap V3 NPM 历史 allowance |
| VIRTUAL/WETH (`0x9c087eb7...`) | VIRTUAL ≈ $5 + WETH ≈ $5 | 只有 WETH，没有 VIRTUAL | dry-run 通道仍可走，但要真实 mint 需要先用 swap 换出 ~$5 VIRTUAL（**本阶段绝不替您做**） |
| USDC/WETH / cbBTC/USDC / cbBTC/WETH | 见行 | 多数双命中或单命中 | best_ev_proxy 异常大负数 — 上游 cost model 对高价 token 有单位 bug，**先不推荐基于这几个的 EV 数字做判断** |

## EV proxy 异常说明

`real_cost_model` 与 `real_fee_economics_preview` 对 cbBTC 类高价 token 给出的 `total_cost_usd` / `new_net_ev_proxy_usd` 显著超出实际可能（$16-$20+ 单笔 swap cost 是不合理的，0.01%-0.05% 费档对 20U notional 的真实滑点应 < $0.02）。这是上游 pipeline 的已知数值异常，**不影响**通道/候选可达性判断，但意味着：

- VIRTUAL/WETH 的 +$0.038 best EV 是这 5 个候选里**唯一可信的微正数**
- WETH/USDC 的 -$0.06 best EV 在合理范围（与 BSC USDT/WBNB 0.01% 的 -$0.0156 同量级）
- 其余三个的大负数应被理解为"上游 pipeline 异常，需另行修复"，不是真实结论

## 推荐候选（仅供 dry-run builder 下一阶段使用）

```text
推荐 #1：WETH/USDC  (pool 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38)
  - 钱包双 token 命中
  - 已有 Uniswap V3 NPM 部分 allowance（WETH=0.00247 / USDC=$5）
  - fee_tier=100 (0.01%) — 与 BSC 候选同档
  - best_ev_proxy=-$0.060（与 BSC USDT/WBNB 同档负 EV，符合"通道验证而非 +EV 押注"定位）

推荐 #2：VIRTUAL/WETH  (pool 0x9c087eb773291e50cf6c6a90ef0f4500e349b903)
  - 唯一微正 EV 候选 (+$0.038)
  - 但钱包只持有一端 (WETH)，需另行获取 VIRTUAL
  - 本阶段绝不替您做获取 VIRTUAL 的 swap

不推荐：cbBTC 系（pipeline 异常）；USDC/WETH 0xd0b53d... 同样 EV 异常
```

## 安全

```text
wallet_or_tx_touched = false
can_run_probe_now    = false
本阶段未做：approve / mint / swap / 任何 tx
```
