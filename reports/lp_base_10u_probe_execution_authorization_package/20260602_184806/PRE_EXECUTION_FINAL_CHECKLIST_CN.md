# Pre-Execution Final Checklist

- stage: `LP_BASE_10U_PROBE_EXECUTION_AUTHORIZATION_PACKAGE_V1`
- phase: D
- run_id: `20260602_184806`
- 适用范围: **未来** 执行 runner 启动时必须每一项重新通过。任何一项 fail ⇒ 强制 **abort**，不允许继续。

## 通道与参数 gate

| # | gate | 检查方法 | 失败时动作 |
|---|---|---|---|
| 1 | `chain_id == 8453` | `eth_chainId` 与硬编码常量比对 | abort |
| 2 | 钱包地址精确匹配 `0xb05b2872ace4564ff247555b6f7b097d31f3d835` | argparse `--wallet` ↔ 常量 WALLET 比对 | abort |
| 3 | 池地址精确匹配 `0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38` | approval phrase 解析 + 常量 POOL 比对 | abort |
| 4 | `notional == 10` USD | argparse `--notional` ↔ approval phrase ↔ 常量 NOTIONAL_USD 三方比对 | abort |
| 5 | `hold == 15m` | argparse `--hold` ↔ approval phrase ↔ 常量 HOLD_WINDOW 三方比对 | abort |

## chain 实时 gate

| # | gate | 检查方法 | 失败时动作 |
|---|---|---|---|
| 6 | current_tick re-read | `eth_call(POOL, slot0)` 实时；不可信赖任何 cached snapshot | abort if RPC fail |
| 7 | dynamic range recomputed | `proposed_lower = current_tick - 200`, `proposed_upper = current_tick + 200` | abort if compute fail |
| 8 | current_tick INSIDE proposed range | `proposed_lower <= current_tick <= proposed_upper` | abort |
| 9 | drift threshold check | `abs(current_tick - LEGACY_FROZEN_TICK) > 200` ⇒ require fresh approval | require fresh approval phrase (强制) |
| 10 | fresh approval re-input if drift > threshold | 操作员在 prompt 中重新输入精确审批短语；以前的短语不复用 | abort if same phrase reused |

## 余额与 allowance gate

| # | gate | 检查方法 | 失败时动作 |
|---|---|---|---|
| 11 | gas balance sufficient | `eth_getBalance(wallet)` ≥ `MIN_NATIVE_FOR_GAS`（建议 0.001 ETH） | abort |
| 12 | USDC balance sufficient | `USDC.balanceOf(wallet)` ≥ 10_000_000 raw | abort |
| 13 | WETH balance check | 本路径 amount0Desired=0，不强求 WETH > 0，但记录 `USDC.balanceOf(wallet)` 与 `WETH.balanceOf(wallet)` 到 telemetry | warn-only |
| 14 | allowance check | `USDC.allowance(wallet, NPM)` 读取；若 ≥ 10_000_000 ⇒ **skip approve step**；若 < 10_000_000 ⇒ **must ApproveExact 10_000_000**；任何尝试 ApproveMax ⇒ abort | conditional |
| 15 | approve exact if needed | step 2 执行 ApproveExact(USDC, NPM, 10_000_000)；amount > 0 且 < UINT256_MAX/2 | abort if condition violated |

## 报价与 slippage gate

| # | gate | 检查方法 | 失败时动作 |
|---|---|---|---|
| 16 | quote valid | `QuoterV2.quoteExactInputSingle` 或 mint pre-call simulate 返回非零 amount | abort |
| 17 | slippage within threshold | `amount1Min_raw = floor(amount1Desired_raw * 0.995)`；mint 期望 fill ≥ amount1Min | abort if quote 推断会 underfill |
| 18 | gas estimate within threshold | `eth_estimateGas` < `MAX_GAS_LIMIT_PER_TX`(600_000) | abort |

## 合约存在 gate

| # | gate | 检查方法 | 失败时动作 |
|---|---|---|---|
| 19 | NPM code exists | `eth_getCode(NPM)` ≠ `0x` | abort |
| 20 | pool code exists | `eth_getCode(POOL)` ≠ `0x` | abort |

## 进程与环境 gate

| # | gate | 检查方法 | 失败时动作 |
|---|---|---|---|
| 21 | no live/canary/paper process | `ps aux \| egrep 'lpbot-live\|canary\|paper'` 必须空 | abort |
| 22 | no production dirty state | 未设置 `DATABASE_URL` / `POSTGRES_DSN` / `SHADOW_POSTGRES_DSN` 等 env；executor v2 启动时已自检（exit 4） | abort (executor 自带) |
| 23 | telemetry path writable | `reports/lp_base_10u_probe_execution_runtime/<run_id>/` 可写 | abort |

## Approval gate（重申）

| # | gate | 检查方法 | 失败时动作 |
|---|---|---|---|
| 24 | gate 1 — `--mode execute-guarded` | argparse `choices` 限定 | abort (argparse error) |
| 25 | gate 2 — approval phrase 完全匹配 | `parse_approval_phrase` regex + 27 危险词 + 4 cross-check | abort |
| 26 | gate 3 — `--i-understand-this-sends-real-transactions` flag 必须显式 | argparse `store_true` | abort |
| 27 | dry-run-only / no-send default true 必须显式覆盖 | 操作员加 `--no-dry-run-only --no-no-send` 或等价 flag（**仍需 send hard-disable 解除**） | abort (本 stage 永远 false) |

## **任何一项 fail ⇒ 未来执行必须 abort**

不允许任何手工绕过；不允许临时硬编码；不允许"等一下重试"。

## 安全（本阶段不变量）

```text
wallet_or_tx_touched          = false
can_run_probe_now             = false
tiny_canary_allowed           = no
execution_allowed_now         = false
```
