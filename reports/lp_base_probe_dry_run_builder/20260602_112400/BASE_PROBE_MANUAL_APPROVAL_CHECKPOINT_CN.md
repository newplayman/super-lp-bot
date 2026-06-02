# 人工审批 Checkpoint

- stage: `LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1`
- phase: K

## 唯一允许的审批短语

```text
APPROVE_BASE_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY wallet=0x<your_wallet_address> notional=<10|20>
```

示例（10U）：

```text
APPROVE_BASE_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY wallet=0xABCDEF0123456789ABCDEF0123456789ABCDEF01 notional=10
```

校验正则（与 upstream spec 一致）：

```text
^APPROVE_BASE_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY wallet=0x[0-9a-fA-F]{40} notional=(10|20)$
```

## 这个短语解锁什么

```text
1. 下一阶段 (LP_BASE_10_20U_PROBE_EXECUTION_SPEC_REVIEW_V1) 可读取您提供的 wallet 地址
2. 下一阶段可调用 ERC20.allowance(owner=wallet, spender=NPM) 判断是否需要 approve
3. 下一阶段可调用 ERC20.balanceOf(wallet) 校验 USDC 余额是否足够
4. 下一阶段可用 from=wallet 做 eth_estimateGas
5. 下一阶段产出精细化的 gas / cost 预测 + 收紧的 unsigned tx package
```

## 这个短语**不**解锁什么

```text
× 加载私钥
× 创建 signer
× 签名任何 tx
× 发送任何 tx (eth_sendTransaction / eth_sendRawTransaction)
× approve / mint / increaseLiquidity / decreaseLiquidity / collect / burn / swap
× 任何链上状态变更
× 任何 production lpbot 表的写入
× 启动 lpbot-live / lpbot-canary / lpbot-paper
× probe 执行 — 执行是更后面的、尚未 spec 的阶段
```

## 必须被拒绝的替代短语

任何**不**匹配上述正则的短语都必须被拒绝，包括但不限于：

```text
APPROVE_BASE_10_20U_PROBE_EXECUTE
APPROVE_BASE_10_20U_PROBE_NOW
APPROVE_BASE_10_20U_PROBE_MINT
APPROVE_BASE_10_20U_PROBE_SIGN
APPROVE_BASE_10_20U_PROBE_LIVE
APPROVE_BASE_10_20U_PROBE_PAPER
APPROVE_BASE_10_20U_PROBE_CANARY
GO
SHIP_IT
PROCEED
APPROVE_BASE_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY wallet=0xUSER_PROVIDED_WALLET_ADDRESS notional=10
APPROVE_BASE_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY wallet=USER_SELECTED_WALLET notional=10
```

> ⚠️ **placeholders `USER_PROVIDED_WALLET_ADDRESS` / `USER_SELECTED_WALLET` 不会被接受**。wallet 字段必须正好是 `0x` + 40 hex chars。

## 输入短语之前您必须确认

- [ ] 我已阅读 candidate freeze / tick range / token amount / unsigned tx package / gas feasibility 报告
- [ ] 我接受 `best_new_net_ev_proxy_usd = -$0.06`（real_fee_accrual pool-level proxy）；本 probe 是通道/遥测投资，不是利润交易
- [ ] 我即将提供的 wallet 地址：
   - 由我个人控制
   - Base 上 USDC 余额 ≤ 22（20U notional + ~$2 gas/slippage buffer）
   - WETH 余额任何值（0+ 都够 0-WETH probe 路径）
   - ETH native 余额 ≥ $0.18（borderline；建议补充 ~$1 缓冲）
   - **不是** multi-sig / 共享钱包 / 冷储主金库
- [ ] 本机没有 lpbot-live / lpbot-canary / lpbot-paper / 其他生产进程在跑
- [ ] 我已设置 `BASE_RPC_PRIMARY` 为付费 endpoint，或明确接受下阶段 wallet-address dry run 仅用 publicnode
- [ ] 我理解批准本短语**不**授权执行；任何 tx 签名/发送前还需另一个有独立 spec + 独立审批的阶段

## 下阶段获批后记录什么

- 用户键入的完整审批短语（含 wallet 地址）
- 下阶段开始的 block number
- wallet 的 USDC 余额 + USDC 对 NPM 的 allowance
- round-trip 每笔 tx 的 `eth_estimateGas` 结果（用户应预期 mint 在 publicnode 仍会 revert，下阶段须自带 fallback）
- 当前 gas_price 下的精细化 `gas_cost_usd`
- 更新后的 unsigned tx package（recipient 填为这个 wallet，但仅供模拟；**不签名不发送**）

## 安全

```text
wallet_or_tx_touched         = false
can_run_probe_now            = false
tiny_canary_allowed          = no
edge_proven                  = no
```
