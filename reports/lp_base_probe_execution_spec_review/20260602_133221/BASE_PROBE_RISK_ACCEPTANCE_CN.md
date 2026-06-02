# Base 10U Probe 风险接受声明

- stage: `LP_BASE_10_20U_PROBE_EXECUTION_SPEC_REVIEW_V1`
- phase: I
- run_id: `20260602_133221`

> ⚠️ **本文件是用户在键入执行审批短语之前必须阅读并接受的风险声明。** 本轮不构造 executor，本轮不发起任何交易。

## 1. EV 不是正数

| 字段 | 值 |
|---|---|
| upstream pool-level EV proxy (20U) | **-$0.0600** |
| upstream actual_position_fee lineage | **missing** (real_fee_accrual WARN) |
| expected realistic outcome | 负 PnL |

## 2. 这**不是**盈利策略验证

```text
本 probe 不验证 LP 策略在 Base 上是否盈利。
本 probe 只验证：
  - mint → hold → decrease → collect → revoke round-trip 路径
  - tokenId 捕获
  - actual_position_fee lineage 数据
  - 真实 PnL（gas + slippage + IL）测量

成功标准 = 完整记录 + 完整退出
不是赚钱。
```

## 3. 可能亏损全部 gas + 滑点 + IL + 手续费

| 组成 | 范围 |
|---|---|
| gas (entry + exit + revoke) | $0.01 - $0.02 (Base 0.0148 gwei) |
| slippage (entry + exit) | 0 - $0.05 |
| IL / LVR | 0 - $1 (depending on WETH 15m drift) |
| fees_collected | 0 - $0.05 (15m low-activity pool) |
| WETH residual | 0 - $5 (取决于价格漂移) |
| **expected realistic loss** | **$0.5 - $2** |
| **worst case** | **$12** (full 10U + 2 buffer) |

## 4. 10U 也可能产生负 PnL

10U notional 看起来小，但：
- $10 是真实的 USD 价值
- 极端情况下 mint 成功 + 15m 内 WETH 暴跌 + 退出时 IL 吃掉本金，可能 10U 退成 $9 或更少
- 不要把它当成"无所谓"的钱

## 5. 成功标准 = 完整记录 tokenId / fee / PnL

即使最终 PnL = -$2，本 probe 在以下意义上仍是**成功**的：

- tokenId 被记录
- actual_position_fee lineage 写进 lp_probe_position_fee_trace_v1
- PnL 写进 lp_probe_actual_pnl_v1
- 退出余额被记录
- USDC + WETH allowance 被 revoke 到 0
- exit_immediate_<id> 或 success 状态被标记

**"赔钱但记录完整" 比 "赚钱但记录缺失" 更重要**。

## 6. 用户必须理解风险后再批准

- [ ] 接受 EV 是负的；这是通道/遥测投资，不是盈利
- [ ] 接受 10U 也可能产生负 PnL
- [ ] 接受 15m hold 期间 WETH 价格波动会导致 IL
- [ ] 接受 actual_position_fee 是未知的（lineage 缺失）
- [ ] 接受不会自动 retry；任何 retry 都需新审批
- [ ] 接受不会自动 loop；任何下一轮 probe 需新审批
- [ ] 接受钱包是个人控制的、不是 multi-sig / 共享 / 冷储主金库
- [ ] 接受主机无 lpbot-live / canary / paper / 其他生产进程
- [ ] 接受监控 15-30 min 并对 stop condition 做出反应
- [ ] 接受 BASE_RPC_PRIMARY 设为付费 endpoint 或明确接受 publicnode
- [ ] 接受批准本短语**不**授权执行；任何 tx 签名/发送前还需 executor 自身独立二次校验 + 操作员在执行时点再键入一次

## 7. 明确不声明

```text
× no_profit_guarantee                — 不保证盈利
× no_ev_positive_claim               — 不声明 EV 为正
× no_real_fee_data                   — 不保证 real fee 数据可用
× no_scaling_recommendation          — 10U/20U 是 probe；不推荐 scale 到 $100/$1000/...
× not_strategy_validation            — 不验证 LP 策略在 Base 上是否盈利
```

## 8. 余额缓冲要求

| token | 最小值 | 原因 |
|---|---|---|
| USDC | 12 | 10U notional + 2 buffer for slippage/IL |
| ETH gas | 0.20 USD | 218,704 gas × 0.0148 gwei = $0.0076；2x buffer = $0.0152；外加 1 笔 mint estimateGas revert 重试的 0.36M gas × 0.0148 gwei = $0.0053；累计 = $0.02；buffer $0.18 = $0.20 |

## 安全

```text
wallet_or_tx_touched              = false
can_run_probe_now                 = false
tiny_canary_allowed               = no
edge_proven                       = no
```
