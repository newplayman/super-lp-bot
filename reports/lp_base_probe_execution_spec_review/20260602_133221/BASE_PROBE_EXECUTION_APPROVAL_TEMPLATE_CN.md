# Base 10U Probe Execution 人工审批模板

- stage: `LP_BASE_10_20U_PROBE_EXECUTION_SPEC_REVIEW_V1`
- phase: H
- run_id: `20260602_133221`

> ⚠️ **本轮不构造 executor。即使有人键入该短语，本轮也不会执行。**
> 未来该短语只在 `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_V1` 构建的 executor 中被识别；该 executor 仍需**操作员在执行时点再键入一次**才会真正提交交易。

## 唯一可接受的未来执行审批短语模板

```text
APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0x<your_wallet_address> pool=0x<the_pool_address> notional=10 hold=15m
```

示例：

```text
APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0xb05b2872ace4564ff247555b6f7b097d31f3d835 pool=0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 notional=10 hold=15m
```

校验正则：

```text
^APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0x[0-9a-fA-F]{40} pool=0x[0-9a-fA-F]{40} notional=10 hold=15m$
```

## 字段解释

| 字段 | 含义 | 接受范围 |
|---|---|---|
| APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT | 固定前缀 | 不可改 |
| wallet=0x<40 hex> | 公开钱包地址 | 0x + 正好 40 hex chars |
| pool=0x<40 hex> | 公开池地址 | 0x + 正好 40 hex chars |
| notional=10 | USD 10 | 只能 10；不接受 20 |
| hold=15m | 15 分钟 | 只能 15m；不接受 30m（30m 仅作 15m 干净完成后的独立延期） |

## 该短语解锁什么（仅在 executor 构建后）

```text
1. executor 加载用户提供的 wallet（公开地址）作为 from / recipient
2. executor 校验 USDC.balanceOf(wallet) >= 12 (10 + 2 buffer)
3. executor 校验 USDC.allowance(wallet, NPM) < 10；若不足则 sign + broadcast approve(USDC, NPM, 10_000_000)
4. executor sign + broadcast NPM.mint(...recipient=wallet, deadline=now+3600, amount1Desired=10_000_000, amount1Min=9_949_999, tickLower=-200643, tickUpper=-200243...)
5. executor 抓取 ERC721 Transfer event 取 tokenId
6. executor hold 15 min（每 60s 采样 hold telemetry）
7. executor sign + broadcast decreaseLiquidity(tokenId, liquidity=full, ...)
8. executor sign + broadcast collect(tokenId, recipient=wallet, ...)
9. executor sign + broadcast approve(USDC, NPM, 0)（revoke）
10. executor sign + broadcast approve(WETH, NPM, 0)（revoke，若需要）
11. executor 写 actual_pnl.json / actual_pnl.csv / session_summary.md
12. executor 退出（不留后台进程）
```

## 该短语**不**解锁什么

```text
× 自动 loop / 重复 probe
× 跨池（只动指定 pool）
× 超出审批的 notional
× ApproveMax
× 自动 swap-back（WETH→USDC）
× 跨链桥
× 任何 live / canary / paper 模式
× 任何后台 unattended 进程
× 任何策略 auto-selection
× 钱包复用超出本 run
× 任何静默 retry
```

## 必须被拒绝的替代短语

```text
× APPROVE_BASE_10U_LP_PROBE_EXECUTE / _NOW / _SIGN / _MINT / _LIVE / _PAPER / _CANARY
× APPROVE_BASE_20U_LP_PROBE_EXECUTION_ONE_SHOT ... (20U 不允许)
× APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT ... notional=20 ...
× APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT ... hold=30m
× APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0xUSER_PROVIDED_WALLET_ADDRESS ... (placeholder)
× APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=USER_SELECTED ... (placeholder)
× GO / SHIP_IT / PROCEED / APPROVE_BASE_10U_LP_PROBE_YES
```

## 输入短语之前操作员必须确认

- [ ] 已阅读 candidate freeze / runbook / stop conditions / telemetry spec / script boundary / risk acceptance 报告
- [ ] realistic EV 不是正数（pool-level proxy = -$0.0600；actual_position_fee lineage 仍 missing）；本 probe 是通道/遥测投资，不是盈利策略
- [ ] 可能亏损全部 gas + slippage + IL + 手续费；10U 也可能产生负 PnL
- [ ] 成功标准不是赚钱，而是完整记录 tokenId / actual fee / PnL
- [ ] 即将提供的 wallet 由个人控制；USDC 余额 ≤ 22；ETH gas ≥ $0.20；不是 multi-sig / 共享钱包 / 冷储主金库
- [ ] 本机无 lpbot-live / lpbot-canary / lpbot-paper / 其他生产进程
- [ ] BASE_RPC_PRIMARY 已设付费 endpoint 或明确接受 publicnode
- [ ] 理解批准本短语**不**授权执行；任何 tx 签名/发送前还需 executor 自身独立二次校验 + 操作员在执行时点再键入一次

## 首轮推荐

```text
notional = 10
hold     = 15m
```

**20U 不作为首轮**；20U 仅在 10U round-trip 干净完成后，由用户单独走一次"20U probe 审批"。

## 安全

```text
wallet_or_tx_touched                  = false
can_run_probe_now                     = false
tiny_canary_allowed                   = no
edge_proven                           = no
approval_phrase_effective_this_round  = false
```
