# 审批短语被拒绝（APPROVAL_PHRASE_REJECTED）

- stage: `LP_BSC_10_20U_PROBE_WALLET_ADDRESS_DRY_RUN_V1`
- phase: A — approval phrase validation
- run_id: `20260602_100951`
- **status: REJECTED**

## 原因

收到的审批短语**带有字面占位符**，不是真实值：

```text
APPROVE_BSC_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY wallet=USER_PROVIDED_WALLET_ADDRESS notional=USER_SELECTED_NOTIONAL
```

上一阶段（`LP_BSC_10_20U_PROBE_DRY_RUN_BUILDER_V1`）冻结的校验正则是：

```text
^APPROVE_BSC_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY wallet=0x[a-fA-F0-9]{40} notional=(10|20)$
```

## 逐字段诊断

| 字段 | 收到 | 要求 | 通过 |
|---|---|---|---|
| `wallet=` | `USER_PROVIDED_WALLET_ADDRESS` | `^0x[a-fA-F0-9]{40}$`（40 个十六进制字符的地址） | ✗ |
| `notional=` | `USER_SELECTED_NOTIONAL` | `10` 或 `20` | ✗ |

## 本轮**已做**的事

```text
- git fetch origin   （无状态变更）
- git status         （只读）
- 短语对照正则       （纯字符串比较）
```

## 本轮**未做**的事（严格遵守 Phase A 的 STOP）

```text
× 未调用 eth_getBalance
× 未调用 ERC20.balanceOf
× 未调用 ERC20.allowance
× 未调用 eth_estimateGas
× 未加载任何私钥
× 未加载任何 mnemonic / seed
× 未构造任何 signer
× 未调用 eth_sendTransaction
× 未调用 eth_sendRawTransaction
× 未执行 approve / mint / increaseLiquidity / decreaseLiquidity / collect / burn / swap
× 未进入 Phase D / E / F / G / H / I
× 未修改任何链上状态
× 未写任何 production lpbot 表
× 未启动 lpbot-live / lpbot-canary / lpbot-paper
× 未翻转 can_run_probe_now / tiny_canary_allowed / edge_proven
```

## 您需要重新发送的内容（unblock 下一次尝试）

请按 **完全相同的格式**重新发送，把两个占位符**替换为真实值**：

```text
APPROVE_BSC_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY wallet=0x<您的40位十六进制钱包地址> notional=<10 或 20>
```

示例（10U）：

```text
APPROVE_BSC_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY wallet=0xABCDEF0123456789ABCDEF0123456789ABCDEF01 notional=10
```

示例（20U）：

```text
APPROVE_BSC_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY wallet=0xABCDEF0123456789ABCDEF0123456789ABCDEF01 notional=20
```

## 您选择 wallet 地址时必须满足的约束（来自 dry-run builder 的 approval checkpoint）

- 必须是您**个人控制**的钱包
- USDT + WBNB 余额合计**不超过 $25**（20U notional + ~$5 gas/slippage buffer）
- **不是** multi-sig / 共享钱包 / 冷储主金库
- 不持有其他大量价值
- **只发公开地址** — 请勿在短语中（或对话其它地方）写出私钥或助记词

## 即使发送了有效短语，**仍不**解锁的事

```text
× 私钥加载
× 助记词加载
× signer 构造
× eth_sendTransaction / eth_sendRawTransaction
× approve / mint / increaseLiquidity / decreaseLiquidity / collect / burn / swap 执行
× live / canary / paper 模式
× probe 执行
```

## 推荐下一阶段

```text
recommended_next_stage = LP_BSC_10_20U_PROBE_WALLET_ADDRESS_DRY_RUN_FIX_REPEAT
```

含义：用替换好的真实值的短语重新发起本任务。校验正则是唯一被卡住的门禁；其它阶段都会照常跑。

## 全局安全标记

```text
wallet_or_tx_touched               = false
can_run_probe_now                  = false
manual_approval_required_for_probe = true
tiny_canary_allowed                = no
edge_proven                        = no
```
