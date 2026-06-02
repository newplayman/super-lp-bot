# 跨链 Dry-run 路由决策

- stage: `LP_EVM_WALLET_ADDRESS_CROSSCHAIN_DRY_RUN_ROUTER_V1`
- phase: H

## 输入摘要（来自前 4 个 phase）

```text
likely_funded_chain                              = base
base_total_usd_proxy                             = $26.84
  ├─ base_native_eth_usd                         = $0.18  (略低于 $0.20 保守 gas 底)
  └─ base_tokens_usd_total                       = $26.67 (WETH $4.89 + USDC $21.77)
bsc_total_usd_proxy                              = $0.00
bsc_candidate_blocked_by_funds_on_other_chain    = true

base_dry_run_ready_candidate_count               = 5
primary_recommendation                           = WETH/USDC 0x72ab388e... (0.01%)
secondary_observation                            = VIRTUAL/WETH 0x9c087eb7... (best EV +$0.038)
```

## 决策

```text
route_branch_taken = base_dry_run_builder_recommended
next_stage_only    = LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1
```

## 选 base / 不选 bsc 的逻辑（按 brief 的 4 路分支）

按 brief Phase H：

> 1. 如果 Base 钱包余额足够，且有 Base candidate ⇒ 输出 Base dry-run builder 下一阶段建议
> 2. 如果 Base 钱包余额足够，但 Base candidate 数据不足 ⇒ LP_BASE_CANDIDATE_REFRESH_...
> 3. 如果 BSC candidate 已 ready 但 BSC funds 不足 ⇒ 输出 BSC blocked by no funds on BSC
> 4. 如果 Base 和 BSC 都不足 ⇒ LP_WALLET_FUNDING_OR_CANDIDATE_REFRESH_REQUIRED

本轮情况是 **(1) 与 (3) 同时成立**：

- (1) 真：Base 钱包有 $26.84，且 5 个 Base V3 候选 dry_run_ready
- (3) 真：BSC 候选已 ready 但 BSC 完全无资金

按 brief，这种情况下：
- BSC 状态被记录为"blocked by no funds on BSC"（详见 `BSC_WALLET_READINESS_CHECK_CN.md`）
- 主路径走 Base dry-run builder（本决策）

## 推荐 Base 候选

| 候选 | 池子 | 钱包是否能直接 mint | 备注 |
|---|---|---|---|
| **WETH/USDC 0.01%** ✅ 推荐 | `0x72ab388e...` | **是**：两端都有；Uni V3 NPM 有部分 allowance | best_ev_proxy=-$0.06，与 BSC -$0.0156 同量级，定位仍是"通道验证" |
| VIRTUAL/WETH | `0x9c087eb7...` | **否**：钱包只有 WETH，没 VIRTUAL | 唯一正 EV 候选 (+$0.038)；要 mint 需另行获取 VIRTUAL（**本阶段不替您做**） |
| USDC/WETH `0xd0b53d92...` | 同上 | 是 | EV proxy 数字异常 -$16.58（上游 cost model 在高价 token 上有单位 bug）— 不推荐基于此数字判断 |
| cbBTC/USDC | `0xb94b2233...` | 是（钱包有 USDC） | EV proxy 异常 -$20.28，同因 |
| cbBTC/WETH | `0xc211e1f8...` | 是（钱包有 WETH） | EV proxy 异常 -$20.61，同因 |

## Gas balance 提示（advisory，不影响本阶段路由）

```text
当前 Base ETH balance = $0.18  ≈ 9.0e-5 ETH
保守 round-trip gas (approve×2 + mint + decrease + collect + revoke×2 ≈ 870k units)
  @ 0.05 gwei = 4.35e-5 ETH ≈ $0.09  (足够 1 次)
  @ 0.10 gwei = 8.70e-5 ETH ≈ $0.17  (刚好够，无缓冲)
  @ 0.50 gwei = 4.35e-4 ETH ≈ $0.86  (不够)
```

执行阶段（仍未授权）之前，建议操作员在 Base 上补 0.0005-0.001 ETH (≈ $1-$2) 以留出余地。**本阶段不替您 top up，也不替您 bridge。**

## 严格禁区（本阶段已遵守）

```text
no_automatic_bridge_suggestion   = true
no_automatic_swap_suggestion     = true
no_tx_executed_this_round        = true
wallet_or_tx_touched             = false
can_run_probe_now                = false
tiny_canary_allowed              = no
edge_proven                      = no
```

## 操作员未来抉择

- 如果要走 Base 路径：使用本决策推荐的 `LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1`（仍是 read-only builder，不签名、不发交易）
- 如果要走 BSC 路径：**由您自行决定**是否在 BSC 上准备资金（USDT + WBNB + BNB gas）；资金获取方法（CEX 提币 / 您自选 bridge）在本工具范围外
- 现有 BSC 的 dry-run builder artifacts (`reports/lp_bsc_probe_dry_run_builder/20260602_094727/`) 保留可用；如果未来 BSC 有资金，可直接重发审批短语进入 BSC 的 wallet-address dry run
