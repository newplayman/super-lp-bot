# Base 10U Probe Execution Runbook (设计，未执行)

- stage: `LP_BASE_10_20U_PROBE_EXECUTION_SPEC_REVIEW_V1`
- phase: D
- run_id: `20260602_133221`
- wallet_address_masked: `0xb05b...d835`
- chain: Base (chain_id 8453)
- pool: `0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38` (WETH/USDC 0.01%)

> ⚠️ **本 runbook 是规范，不是执行清单。本轮不构造 signer、不发任何交易、不打开任何浏览器钱包、不连接硬件钱包。**
> 真正执行由未来 `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_V1` 构建的执行脚本 + 用户在执行时点单独审批短语 共同触发。

## 0. 操作员前置

- [ ] 执行审批短语已被粘贴到本 run 目录的 signed log（参见 Phase H）
- [ ] `BASE_RPC_PRIMARY` 已设为付费 endpoint（或明确接受仅用 publicnode）
- [ ] 主机无 lpbot-live / lpbot-canary / lpbot-paper / 其他生产进程
- [ ] 钱包资金未发生实质性变化（USDC > 22、ETH gas > $0.20）
- [ ] 操作员能全程监控 15m（30m 若延期）

## Step 0：pre-execution sanity（任何一项 fail → halt + 不进入 Step 1）

| # | 检查 | 期望 | halt if |
|---|---|---|---|
| 0.1 | `eth_chainId` | 8453 | != 8453 |
| 0.2 | wallet ETH balance | >= 9.0e-5 ETH | < 9.0e-5 |
| 0.3 | wallet USDC balance | >= 12 (10U) / 22 (20U) | < 阈值 |
| 0.4 | wallet WETH balance | log only | n/a |
| 0.5 | USDC.allowance(wallet, NPM) | log + 比较 need | log only |
| 0.6 | WETH.allowance(wallet, NPM) | log only | n/a |
| 0.7 | pool.slot0() current_tick | inside/near [-200643, -200243] | 漂出 half-range |
| 0.8 | pool.liquidity() | > 1e15 | < 1e15 |
| 0.9 | QuoterV2 WETH→USDC (10 USDC worth) | out ≈ 9.95-10.0 USDC | out < 9.5 |
| 0.10 | QuoterV2 USDC→WETH (10 USDC) | out ≈ 0.005 WETH | out < 0.004 |
| 0.11 | mint eth_estimateGas | <= 360,000 | revert 或 > 360k |
| 0.12 | total gas cost USD | < $0.10 | >= $0.20 |
| 0.13 | hold timer set | 15m | n/a |

**任何失败** → HALT + 不进入 Step 1 + 写 `HALT_<reason>_CN.md` + 报告操作员。

## Step 1：ApproveExact, only if needed

```text
if USDC.allowance >= notional_required:
    skip approve entirely
else:
    build ERC20.approve(USDC, NPM, notional_required)
    invariant: amount_raw == chosen notional in raw USDC; never uint256.max
    sign + broadcast
    wait 12 confirmations
    re-read allowance on-chain; record actual
```

WETH 端 amount = 0 wei，**默认不 approve WETH**。如果 Step 0 出现意外 WETH 需求 → HALT，不静默 approve。

## Step 2：Mint

```text
build NPM.mint(
    token0=0x4200...0006,  # WETH
    token1=0x8335...2913,  # USDC
    fee=100,
    tickLower=-200643,
    tickUpper=-200243,
    amount0Desired=0,
    amount1Desired=10_000_000 (or 20_000_000),
    amount0Min=0,
    amount1Min=9_949_999 (or 19_899_999),
    recipient=wallet,
    deadline=now+3600
)
sign + broadcast
wait 12 confirmations
decode ERC721 Transfer event for tokenId
call NPM.positions(tokenId) — record canonical state
record balance deltas for WETH + USDC
```

**无 increaseLiquidity**（probe 是单 mint，不追加）。
**不创建新位置**（不增加额外 tokenId）。

## Step 3：Hold monitoring（每 60s 一次）

```text
for minute in 1..hold_window_minutes:
    read pool.slot0() — current_tick
    read NPM.positions(tokenId) — liquidity, feeGrowthInside, tokensOwed
    QuoterV2 spot reference
    mark-to-market in USDC
    record: block, tick, liquidity, feeGrowthInside0/1, tokensOwed0/1, mtm_usd, mtm_pnl
    check Stop Conditions (Phase E)
    if any stop: jump to Step 4 immediately
```

## Step 4：Exit (decreaseLiquidity + collect)

```text
build NPM.decreaseLiquidity(tokenId, liquidity=full, amount0Min=0, amount1Min=with_slippage, deadline=now+3600)
sign + broadcast
wait 12 confirmations
build NPM.collect(tokenId, recipient=wallet, amount0Max=max, amount1Max=max)
sign + broadcast
wait 12 confirmations
call NPM.positions(tokenId) — confirm liquidity=0, tokensOwed=0
record final balances
DO NOT swap-back WETH→USDC (需要独立审批)
```

**不 swap-back**。Probe 退到 WETH + USDC 余额，不做自动换币。

## Step 5：post-exit cleanup

```text
build ERC20.approve(USDC, NPM, 0)   # revoke USDC
sign + broadcast
wait 12 confirmations
if WETH.allowance > 0:
    build ERC20.approve(WETH, NPM, 0)
    sign + broadcast
    wait 12 confirmations
final balance snapshot (ETH + WETH + USDC)
generate actual_pnl report (see Phase F)
commit all telemetry to this run directory
mark run complete
```

## 严格禁止（本 runbook 内）

```text
× 自动重复执行（probe 只跑一次；下次必须新审批）
× 多池（这次只动 0x72ab388e..）
× 超出审批的 notional
× ApproveMax
× 自动 swap-back
× 跨链桥
× 任何 live loop / canary / paper trading
× 任何策略 auto-selection
× 钱包复用（此 wallet 仅用于本次审批的 probe）
× 隐藏 retry（每次 retry 必须新审批 + 新建 telemetry session）
```

## 安全

```text
wallet_or_tx_touched = false  (本 runbook 不发起任何 tx)
can_run_probe_now    = false  (runbook 不授权执行)
tiny_canary_allowed  = no
edge_proven          = no
```
