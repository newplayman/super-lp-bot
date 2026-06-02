# 跨链 Allowance 审计（只读）

- stage: `LP_EVM_WALLET_ADDRESS_CROSSCHAIN_DRY_RUN_ROUTER_V1`
- phase: E
- wallet_address_masked: `0xb05b...d835`
- approve_executed_this_round: **false**

## Spender allowlist (本审计用)

| label | 地址 | 用途 |
|---|---|---|
| `uni_v3_npm_base` | `0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1` | Uniswap V3 NonfungiblePositionManager (Base) |
| `aero_slipstream_npm_base` | `0x827922686190790b37229fd06084350E74485b72` | Aerodrome Slipstream NonfungiblePositionManager (Base) |
| `pcs_v3_npm_bsc` | `0x46A15B0b27311cedF172AB29E4f4766fbE7F4364` | PancakeSwap V3 NonfungiblePositionManager (BSC) |

## Allowance 结果（read-only `ERC20.allowance(owner=wallet, spender=NPM)`）

| chain | protocol | token | allowance (raw) | allowance (human) | approval_needed_for_first_mint |
|---|---|---|---|---|---|
| base | Uniswap V3 NPM | **WETH** | `2,470,131,003,793,800` | **0.002470 WETH** | **no（但只够 ≤0.00247 WETH 的 mint，约 $4.89）** |
| base | Uniswap V3 NPM | **USDC** | `5,000,000` | **5.0 USDC** | **no（但只够 ≤$5 USDC 的 mint）** |
| base | Uniswap V3 NPM | USDT (Tether USD₮0) | `0` | 0 | yes |
| base | Uniswap V3 NPM | cbBTC | `0` | 0 | yes |
| base | Aerodrome Slipstream NPM | WETH | `0` | 0 | yes |
| base | Aerodrome Slipstream NPM | USDC | `0` | 0 | yes |
| base | Aerodrome Slipstream NPM | cbBTC | `0` | 0 | yes |
| bsc | PancakeSwap V3 NPM | USDT | `0` | 0 | yes |
| bsc | PancakeSwap V3 NPM | WBNB | `0` | 0 | yes |
| bsc | PancakeSwap V3 NPM | USDC | `0` | 0 | yes |

## 重要发现

钱包**已经有 Uniswap V3 NPM (Base) 的 WETH + USDC 历史 allowance**，且金额非常"对齐"：

- WETH allowance = 0.002470 WETH = **正好等于当前 WETH 余额**
- USDC allowance = 5.0 USDC

这是典型 **ApproveExact** 旧痕迹 —— 钱包过去在 Uniswap V3 Base 上做过 LP，且接近全部 WETH 被 approve 过给 NPM。这本身**没问题**（ApproveExact 是推荐做法），但意味着：

1. 如果未来 10U probe 用 **Uniswap V3 Base WETH+USDC** 候选：
   - WETH 端：现有 allowance 不够新一笔 mint（需要 ~$5 WETH = 0.00253 WETH，allowance 是 0.00247 WETH）→ 仍需一次新 `approve(NPM, 0.00253e18)`
   - USDC 端：现有 allowance ~ $5 刚好够 10U LP 的 USDC 一半（≈ $5）→ 不需要新 approve
2. 如果未来 10U probe 用 **Aerodrome Slipstream**：
   - WETH 和 USDC 都是 0 allowance → 两个 token 都需要 ApproveExact
3. 如果未来 用 **BSC PancakeSwap V3**：
   - 全部 0 → 但钱包**根本没 BSC 资金**，连 dry-run 都做不了

## 推论

```text
base_first_mint_needs_approve_count:
  on_uniswap_v3:    1 (WETH only;  USDC allowance OK for 10U but not for 20U)
  on_aerodrome:     2 (both tokens)

bsc_first_mint_needs_approve_count:
  pancakeswap_v3:   N/A (no BSC funds, dry-run blocked at Phase D)
```

## 安全

```text
approve_executed_this_round = false
all calls = ERC20.allowance via eth_call (read-only)
wallet_or_tx_touched = false
can_run_probe_now    = false
```
