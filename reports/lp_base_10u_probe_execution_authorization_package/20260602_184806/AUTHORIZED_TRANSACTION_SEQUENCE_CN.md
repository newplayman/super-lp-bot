# Authorized Transaction Sequence

- stage: `LP_BASE_10U_PROBE_EXECUTION_AUTHORIZATION_PACKAGE_V1`
- phase: E
- run_id: `20260602_184806`
- 适用范围: **未来** 执行 runner 仅允许下列交易；任何其它交易必须 abort。

## 允许的交易 — whitelist

| # | tx | conditional | function | 参数约束 |
|---|---|---|---|---|
| 1 | **optional USDC ApproveExact** | 仅当 `USDC.allowance(wallet, NPM) < 10_000_000` | `USDC.approve(NPM, 10_000_000)` | amount == 10_000_000 exactly；amount > 0；amount < UINT256_MAX/2；selector 0x095ea7b3 |
| 2 | **optional WETH ApproveExact** | 本路径 `amount0Desired=0` 不需要 WETH，因此默认 **跳过**；只在未来路径若 `amount0Desired_wei > 0` 时才允许，且仍 ApproveExact | `WETH.approve(NPM, amount0Desired_wei)` | amount == amount0Desired_wei exactly |
| 3 | **NPM.mint** for exact candidate pool/range/notional | 必选 | `NPM.mint((WETH, USDC, 100, dynamic_lower, dynamic_upper, 0, 10_000_000, 0, 9_950_000, wallet, now+3600))` | token0/token1/fee 全 hardcoded；recipient=wallet；deadline runtime；amount1Min ≥ 9_950_000 (0.5% slippage) |
| 4 | **NPM.decreaseLiquidity** for tokenId from this run only | 必选 | `NPM.decreaseLiquidity((tokenId, liquidity_all, amount0Min, amount1Min, now+3600))` | tokenId **必须** 来自当轮 mint receipt 解析，不允许引用历史 tokenId |
| 5 | **NPM.collect** for tokenId from this run only | 必选 | `NPM.collect((tokenId, wallet, (1<<128)-1, (1<<128)-1))` | recipient=wallet；amount0Max/amount1Max=uint128.max |
| 6 | **optional revoke approval to 0** | 仅当 step 1 执行过 | `USDC.approve(NPM, 0)` | amount == 0 exactly |

## 禁止的交易 — blacklist

| 类别 | 具体禁止 |
|---|---|
| **ApproveMax** | `approve(NPM, UINT256_MAX)` 或任何 ≥ UINT256_MAX/2 的金额 |
| **multi-pool** | 同一笔 run 不允许在 ≠ POOL 的池中 mint / swap / approve |
| **notional > 10** | 任何 amount1Desired_raw > 10_000_000 |
| **hold > 15m without new approval** | 未重新生成 `APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT ... hold=15m` 仅 hold=15m 短语，禁止改 hold=20m/30m/1h |
| **swap-back** | 不允许在 mint 之前/之后执行 swap 调整余额 |
| **bridge** | 不允许跨链 bridge USDC/WETH |
| **auto-repeat** | 不允许同一 wallet 在第一轮完成前自动开启第二轮 mint |
| **live loop** | 不允许启动 `lpbot-live` 进程 |
| **canary** | 不允许启动 canary 模式 |
| **paper** | 不允许启动 paper 模式 |
| **strategy auto-selection** | 不允许执行内部 strategy 模块自动选池逻辑 |
| **any other wallet** | 不允许用 ≠ `0xb05b...d835` 的 wallet |
| **any other pool** | 不允许用 ≠ `0x72ab...2d38` 的 pool |
| **any other chain** | 不允许在 chain_id ≠ 8453 上执行 |

## `skip_approve_if_allowance_sufficient` — 必补项落地说明

未来执行 runner 在 step 1 (preflight) 后必须：

```text
allowance = USDC.allowance(wallet, NPM)
if allowance >= 10_000_000:
    skip_approve = true
    telemetry.allowance_already_sufficient = true
    proceed directly to mint (step 3)
else:
    skip_approve = false
    must execute step 1 (ApproveExact 10_000_000)
    NEVER ApproveMax
```

`executor v2` 已经实现 `encode_allowance` helper (l.209-210) 但未在 caller 中调用；future runner 必须 wire 这个调用。

## tx 顺序与依赖

```text
[preflight (R-O)]
        |
        v
[allowance check (R-O)]
        |
    allowance < 10M  ?
        |
    yes |--> [USDC ApproveExact (tx)] --> [verify allowance >= 10M (R-O)]
    no  |---------------------------+
        |                           |
        v                           |
    [mint (tx)] <-------------------+
        |
        v
    [extract tokenId from receipt (R-O)]
        |
        v
    [validate positions(tokenId) matches expected (R-O)]
        |
        v
    [hold monitor 15m, 1-3 min interval (R-O)]
        |
        v
    [pre-exit fee state read (R-O)]
        |
        v
    [decreaseLiquidity (tx)]
        |
        v
    [collect (tx)]
        |
        v
    [post-collect fee state read (R-O)]
        |
        v
    [revoke USDC allowance to 0 if step 1 executed (tx)]
        |
        v
    [final PnL telemetry (R-O)]
```

## 安全（本阶段不变量）

```text
wallet_or_tx_touched          = false
can_run_probe_now             = false
tiny_canary_allowed           = no
execution_allowed_now         = false
this_phase_only_whitelists_tx_for_future = true
```
