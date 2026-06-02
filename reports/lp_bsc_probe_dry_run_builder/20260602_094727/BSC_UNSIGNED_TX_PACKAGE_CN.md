# BSC Unsigned TX Package（不签名、不发送）

- stage: `LP_BSC_10_20U_PROBE_DRY_RUN_BUILDER_V1`
- phase: G
- 形式：**structured JSON only**，不 emit full ABI-encoded bytes
- `recipient = PLACEHOLDER_USER_WALLET_NOT_SET`
- `deadline = PLACEHOLDER_MANUAL_SET`

## 为什么不输出完整 calldata bytes

> recipient 是占位符，full-ABI-encoded bytes 的 recipient slot 是 zero address——这种 bytes 即使签名后发送也会 revert（或发到零地址）。**下一阶段**（有真实 wallet 地址时）必须 re-quote 后再 encode。

## Approval needed check（仅静态 unknown — 未读 allowance）

```text
kind   = static_unknown_without_wallet_address
policy = ApproveExact ONLY；禁止 ApproveMax；exit 后必须 revoke
spender allowlist = [PancakeSwap V3 NonfungiblePositionManager (BSC)]
spender 地址      = 0x46A15B0b27311cedF172AB29E4f4766fbE7F4364
this_round_calls_approve            = false
this_round_calls_eth_call_allowance = false
```

下一阶段（有 wallet 地址）必须先调用 `ERC20.allowance(owner=wallet, spender=NPM)`：
- 若 USDT allowance < amount0Desired → 需要 `USDT.approve(NPM, amount0Desired)`
- 若 WBNB allowance < amount1Desired → 需要 `WBNB.approve(NPM, amount1Desired)`

## Mint calldata draft

| 字段 | 值 |
|---|---|
| method | **`mint`**（不是 `increaseLiquidity` — 操作员此 pool 上还没有 tokenId） |
| target contract | PancakeSwap V3 NonfungiblePositionManager (BSC) |
| target address | `0x46A15B0b27311cedF172AB29E4f4766fbE7F4364` |
| selector hint | `0x88316456` |
| signature | `mint((address,address,uint24,int24,int24,uint256,uint256,uint256,uint256,address,uint256))` |

### Params for 10U

| 字段 | 值 |
|---|---|
| token0 | `0x55d398326f99059fF775485246999027B3197955` (USDT) |
| token1 | `0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c` (WBNB) |
| fee | `100` |
| tickLower | `-65280` |
| tickUpper | `-65080` |
| amount0Desired | `4971672871026643667` wei (4.972 USDT) |
| amount1Desired | `7427805378417271` wei (0.007428 WBNB) |
| amount0Min | `4946814506671510449` wei (4.947 USDT，50 bps slippage 底) |
| amount1Min | `7390666351525185` wei (0.007391 WBNB，50 bps) |
| recipient | **`PLACEHOLDER_USER_WALLET_NOT_SET`** |
| deadline | **`PLACEHOLDER_MANUAL_SET`** |

### Params for 20U

| 字段 | 值 |
|---|---|
| amount0Desired | `9943345742053287335` wei (9.943 USDT) |
| amount1Desired | `14855610756834543` wei (0.014856 WBNB) |
| amount0Min | `9893629013343020899` wei (9.894 USDT) |
| amount1Min | `14781332703050370` wei (0.014781 WBNB) |
| 其他字段 | 与 10U 相同 |

> **重要**：以上 amount 在 mint 真实执行前必须**重新报价**。`amounts_are_stale_after_seconds = 60`。

## Approve calldata draft（不发送）

| 代币 | 地址 | spender | value (10U / 20U) |
|---|---|---|---|
| USDT | `0x55d3...7955` | NPM `0x46A1...4364` | `4971672871026643667` / `9943345742053287335` |
| WBNB | `0xbb4C...c095c` | NPM `0x46A1...4364` | `7427805378417271` / `14855610756834543` |

约束：`value` 必须等于对应 `amountXDesired`（**ApproveExact**）。

## Exit path draft

1. `decreaseLiquidity((tokenId=FROM_MINT, liquidity=FULL, amount0Min=RECOMPUTED_50_BPS, amount1Min=RECOMPUTED_50_BPS, deadline=PLACEHOLDER))`
2. `collect((tokenId=FROM_MINT, recipient=PLACEHOLDER, amount0Max=uint128.MAX, amount1Max=uint128.MAX))`
3. `burn(tokenId=FROM_MINT)` — 可选（清理 NFT，退回少量 gas）

## Post-exit revoke draft

| 代币 | call |
|---|---|
| USDT | `approve(NPM, 0)` |
| WBNB | `approve(NPM, 0)` |

## Swap-back (default: 不做)

> 默认**不**做 swap-back。probe 目的是测真实经济，多一次 swap 多一次 quote drift。如果操作员要做，需走 `SwapRouter.exactInputSingle`（地址 `0x1b81D678ffb9C0263b24A97847620C99d213eB14`），同样要在 approval phrase 里写明。

## 严格约束自查

```text
recipient_never_real_wallet                       = true
deadline_never_real_value                         = true
no_private_key_or_seed_referenced                 = true
no_signer_constructed                             = true
no_transaction_sent                               = true
no_full_abi_encoded_bytes_emitted_for_execution   = true
approval_strategy_is_ApproveExact_only            = true
approval_max_forbidden                            = true
post_exit_revoke_required                         = true
```

## 下一阶段（仍非本轮）必须做的事

1. 校验 wallet 地址在操作员本地 allowlist
2. mint 提交前 60s 内 re-quote QuoterV2
3. 从新 quote 重算 amount0Min / amount1Min
4. **只有**填好 recipient 与 deadline 之后再 encode full ABI bytes
5. 用 `eth_call`（带 `from=wallet`）模拟整笔 tx 后再签
6. 由操作员显式键入指定短语才允许签名
7. **仍不是本轮责任** — 那是更后面阶段的门禁
