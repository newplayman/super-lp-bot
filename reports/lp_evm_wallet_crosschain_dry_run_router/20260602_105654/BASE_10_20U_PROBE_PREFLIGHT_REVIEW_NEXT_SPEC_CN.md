# Base 10/20U Probe — Dry-run Builder 下一阶段 spec

- stage: `LP_EVM_WALLET_ADDRESS_CROSSCHAIN_DRY_RUN_ROUTER_V1`
- phase: I（这是**下一阶段** spec，不是执行）

## 下一阶段

```text
LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1
```

镜像 `LP_BSC_10_20U_PROBE_DRY_RUN_BUILDER_V1` 的结构，仅候选改为 Base。

## 输入

```text
- 本阶段 crosschain_dry_run_route_decision.json
- Base RPC endpoint (推荐 BASE_RPC_PRIMARY env 注入付费 endpoint；dry-run 阶段可用 publicnode)
- wallet_address_public = 0xb05b...d835  (Phase D 已确认 Base 端有资金)
- notional = 10 (preferred) 或 20 (max)
```

## 提议 phase 顺序

```text
A. workspace + RUN_ID
B. input evidence audit（包含本阶段的 FINAL_VERDICT）
C. Base candidate freeze (pool=0x72ab388e..., pair=WETH/USDC, fee=100, notional 10/20)
D. Base pool state refresh (slot0 / liquidity / fee / tickSpacing / QuoterV2，全 read-only eth_call)
E. Base tick range proposal (narrow/medium/wide 三档；推荐 medium)
F. Base token amount calculation (10U/20U → WETH+USDC desired + amountMin)
G. Base unsigned tx package (mint draft on Uniswap V3 NPM Base 0x03a520b3...;
                              recipient=PLACEHOLDER_USER_WALLET_NOT_SET;
                              deadline=PLACEHOLDER_MANUAL_SET; ApproveExact)
H. Base gas feasibility (eth_estimateGas with from=wallet — 这是本钱包第一次 bind)
I. Base manual approval checkpoint
J. final verdict
K. tests
L. git publish
```

## 下一阶段绝对禁止

```text
- send any transaction
- load private key / mnemonic / keystore
- create signer
- execute approve / mint / increaseLiquidity / decreaseLiquidity / collect / burn / swap
- start lpbot-live / lpbot-canary / lpbot-paper
- auto-bridge / auto-swap
- flip can_run_probe_now / tiny_canary_allowed / edge_proven
```

## 复用本仓库已有 artifacts

| 数据 | 路径 |
|---|---|
| 本阶段 FINAL_VERDICT | `reports/lp_evm_wallet_crosschain_dry_run_router/20260602_105654/FINAL_VERDICT.json` |
| 钱包余额审计 | `.../evm_wallet_crosschain_balance_audit.json` |
| 钱包 allowance 审计 | `.../evm_wallet_crosschain_allowance_audit.json` |
| Base V3 tick-liquidity | `reports/lp_v3_tick_liquidity_fix/20260601_132644/...` |
| Base real cost model | `reports/lp_real_cost_model/20260601_141103/...` |
| Base real fee accrual | `reports/lp_real_fee_accrual/20260601_143401/...` |
| Base precise quote | `reports/lp_precise_quote/20260601_120001/...` |

## 下下阶段的 approval phrase 正则（当 Base dry-run builder 完成才允许）

```text
^APPROVE_BASE_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY wallet=0x[0-9a-fA-F]{40} notional=(10|20)$
```

**该短语依然不解锁执行** — 只解锁 Base wallet-address bound 的 dry-run（与 BSC 路径同结构）。

## 安全

```text
wallet_or_tx_touched = false
can_run_probe_now    = false
```
