# Wallet-Bound Unsigned Tx Package

- stage: `LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1`
- phase: I
- run_id: `20260602_112400`
- chain: **Base** (chain_id 8453)
- wallet_address_bound: `0xb05b2872ace4564ff247555b6f7b097d31f3d835` (masked `0xb05b...d835`)
- npm: `0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1` (Uniswap V3 NonfungiblePositionManager Base)
- pool: `0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38` (WETH/USDC 0.01%)
- tick range: **[-200643, -200243]** (medium, 15m horizon recommended)

## Deadline placeholder

```text
deadline = 4070908800  (2099-01-01T00:00:00Z)
deadline_is_placeholder = true
```

**该 deadline 是 PLACEHOLDER 性质**：far-future 不会让 tx 在签名时立即过期；用户在执行前可覆盖为当下 + 1h（推荐）或当下 + 5min。**本 stage 不替用户选 deadline**。

## Approve policy (invariant #9)

```text
ApproveExact only.  Never ApproveMax.
本 stage 在 10U 路径 approve(USDC, 10_000_000) = 10 USDC；20U 路径 approve(USDC, 20_000_000) = 20 USDC。
```

WETH 端 amount0 = 0，无需新 approve。

## Tx sequence（10U 路径）

| step | action | from | to | value | data | 含义 |
|---|---|---|---|---|---|---|
| 1 | ERC20.approve | wallet | USDC (`0x8335..`) | 0 | `0x095ea7b3` + spender=NPM + amount=10_000_000 | 准许 NPM 动用 10 USDC（ApproveExact） |
| 2 | NPM.mint | wallet | NPM (`0x03a5..`) | 0 | `0x88316456` + 11 字段 tuple | 在 [P_low, P_up] 范围内以 0 WETH + 10 USDC 铸造 LP NFT；recipient=wallet；deadline=placeholder |
| 3 | (decreaseLiquidity + collect + revoke) | wallet | NPM | — | 由下阶段构建 | **本 stage 不构建**；probe 真实执行前需走 LP_BASE_10_20U_PROBE_EXECUTION_SPEC_REVIEW_V1 |
| 4 | ERC20.approve (USDC revoke) | wallet | USDC | 0 | `0x095ea7b3` + spender=NPM + amount=0 | post-exit revoke (invariant #10) |

## Tx sequence（20U 路径）

| step | action | from | to | value | data | 含义 |
|---|---|---|---|---|---|---|
| 1 | ERC20.approve | wallet | USDC | 0 | `0x095ea7b3` + spender=NPM + amount=20_000_000 | 准许 NPM 动用 20 USDC |
| 2 | NPM.mint | wallet | NPM | 0 | `0x88316456` + 11 字段 tuple | 0 WETH + 20 USDC 铸 LP；recipient=wallet；deadline=placeholder |
| 3 | (decreaseLiquidity + collect + revoke) | wallet | NPM | — | 由下阶段构建 | 同上 |
| 4 | ERC20.approve (USDC revoke) | wallet | USDC | 0 | `0x095ea7b3` + spender=NPM + amount=0 | post-exit revoke |

## mint call data (10U) 解读

```text
selector 0x88316456
offset 0x20
token0   = 0x4200000000000000000000000000000000000006  (WETH)
token1   = 0x833589fcd6edb6e08f4c7c32d4f71b54bda02913  (USDC)
fee      = 100                                         (0.01%)
tickLower= -200643  (int24, sign-extended 0xfff...fcf03d)
tickUpper= -200243  (int24, sign-extended 0xfff...fcf1cd)
amount0Des = 0     (WETH wei)
amount1Des = 10000000   (USDC raw, 10 USDC)
amount0Min = 0
amount1Min = 9949999   (USDC raw, 9.95 USDC, 0.5% slippage)
recipient  = 0xb05b2872ace4564ff247555b6f7b097d31f3d835  (the bound wallet)
deadline   = 4070908800  (2099-01-01 UTC, PLACEHOLDER)
```

## mint call data (20U) 解读

```text
...same as 10U except:
amount1Des = 20000000   (USDC raw, 20 USDC)
amount1Min = 19899999   (USDC raw, 19.90 USDC, 0.5% slippage)
```

## Invariant 检查

| # | 检查 | 状态 |
|---|---|---|
| #3 | dryrun broadcast count == 0 (本 stage 不发交易) | ✓ (无 tx 发出) |
| #4 | MinOut non-zero & Deadline non-zero (placeholder 仍 non-zero) | ✓ (amount1Min=9949999/19899999 > 0; deadline=4070908800 > 0) |
| #9 | ApproveExact only, never ApproveMax | ✓ (approve 金额 == 实际 LP 需求) |
| #10 | Post-exit revoke planned (step 4) | ✓ (USDC approve(NPM, 0) 已规划) |

## 已 sign / send

- ✗ 未签名
- ✗ 未发送任何 `eth_sendTransaction` / `eth_sendRawTransaction`
- ✗ 未加载 keystore / 助记词
- ✗ 未创建 signer
- ✗ 未 approve / mint / decrease / collect / burn / swap

## 安全

```text
wallet_or_tx_touched       = false
can_run_probe_now          = false
tiny_canary_allowed        = no
edge_proven                = no
approvemax_never_used      = true
post_exit_revoke_planned   = true
```
