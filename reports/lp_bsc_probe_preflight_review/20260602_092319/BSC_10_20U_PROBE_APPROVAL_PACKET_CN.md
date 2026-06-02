# 10/20U Probe 审批包（给用户审批使用）

- stage: `LP_BSC_10_20U_PROBE_PREFLIGHT_REVIEW_V1`
- phase: G
- 收件人：**人工 operator（您）**

## 候选池

```text
chain                 = BSC
protocol              = PancakeSwap V3
pool_address          = 0x172fcd41e0913e95784454622d1c3724f546f849
pair                  = USDT/WBNB
fee_tier              = 0.01% (raw = 100)
```

## 预计资金

```text
preferred_usd         = 10
max_usd               = 20
single_pool_only      = yes
single_position       = yes
no_compounding        = yes
```

## 最大损失假设

| 维度 | 数额 (USD) |
|---|---|
| fixed_cost (entry+exit+collect+approval gas) | $0.0153 |
| realistic IL/LVR (20U / 15m) | $0.0004 |
| expected pool fee proxy (20U / 15m) | $0.0001 |
| expected net EV proxy (20U / 15m, realistic) | **-$0.0156** |
| tail loss if S1 quote_drift triggers immediately | ~$0.10 (40bps × 20U) |
| tail loss if S10 MtM stop triggers | $0.50 (配置阈值) |
| **绝对最坏（非催化失败下）** | **~$1.00** |

> 上述不含合约 rug / exploit 类极端情形。候选池是已知良好的审计池，但任何链上动作都不是零风险。

## 为什么不是 +EV 证明

1. **20U notional 下 $0.0153 fixed cost 主导任何 hold 的 fee_proxy**。
2. 候选池经济矩阵里**唯一一个正 EV cell** 是 `100U / 24h / zero_il_lvr = +$0.038`，但 `zero_il_lvr` 是不现实情境（声称 24h 的 WBNB/USDT LP 没有 IL，已知 false）。
3. realistic 情境下 20U 最好的 cell 是 15m 的 **-$0.0156**，并随 hold 加长而变差。
4. **本审批包不主张这是 +EV 交易**。

## 为什么仍然值得做（作为"通道探针"而非"盈利探针"）

1. **通道验证** — 完整的 approve → mint → in-range hold → decreaseLiquidity → collect → revoke 流程在本仓库还没用真实 wallet 在 BSC PancakeSwap V3 跑过端到端。
2. **tokenId 获取** — 真实的 NFT position tokenId 只能在真实 mint 之后从 NFT Transfer event 观测到；这校准下游 telemetry。
3. **实测 fee accrual** — pool-level fee_proxy 是**上界估计**（假设头寸吃 (notional / TVL_proxy) 份额，忽略 tick-range 集中性）。一次 15m 真实 probe 测得选定 `[tickLower, tickUpper]` 的 `feeGrowthInside / tokensOwed` 实际增量 — **这是给后续 100 / 500 / 1000 / 2000U 做尺度判断时最重要的校准输入**。
4. **exit-quote 稳定性** — 15m hold 让我们测一次真实 LP 大小下 swap-back quote 在 15m 窗口内的实际漂移。

## 预计持有时间

```text
initial         = 15 分钟
max extension   = 30 分钟（仅 health_ok 时人工手动延长）
```

## 成功标准（如未来 probe 获批执行）

- mint_tx 确认
- mint 后 30s 内成功观察到 tokenId（NFT Transfer event）
- hold 全程 in_range
- exit_tx（decreaseLiquidity + collect）确认
- actual_fee_accrual_usd 已记录（即使 ~$0）
- revoke_tx 确认
- net_pnl_usd 在最坏情形模型的 ±$1.00 之内

## 失败标准（如未来 probe 获批执行）

- 任一 stop condition（S1..S10）触发并强制 unplanned exit
- tokenId 未能在 mint 确认 30s 内取到
- exit quote 超过 60s + 1 次重试仍不可用
- exit 后 revoke 失败
- net 损失超过 $1.00
- probe 期间有任何 wallet / 私钥 / live order 进程被其他流程触碰

## 您必须明确确认的事项

- [ ] 我已阅读 candidate review / risk limits / telemetry spec / dry-run builder spec
- [ ] 我接受 realistic EV 为负，本 probe 是通道/遥测投资，不是利润交易
- [ ] 我已设置 `BSC_RPC_PRIMARY` 为付费 endpoint（或明确仅在 dry-run 阶段使用 publicnode）
- [ ] 我已准备一个钱包地址，余额上限 ≤ 25 USD 等值（20U notional + ~5U gas/slippage buffer）
- [ ] 我确认本机上没有 `lpbot-live` / `lpbot-canary` / `lpbot-paper` 或其他生产进程在跑
- [ ] 我会**先**运行 dry-run builder 并**完整 review 其 unsigned tx package** 输出**之后**再做任何执行
- [ ] 我理解批准本审批包只解锁 `LP_BSC_10_20U_PROBE_DRY_RUN_BUILDER_V1`，**不**解锁执行

## 一句话结论

```text
建议结论                  = APPROVE_DRY_RUN_BUILDER
默认结论（如您未明确批准） = DO_NOT_EXECUTE_PROBE_YET
```

含义：批准后我们进入下一只读阶段（构建 unsigned tx package 并用 eth_call 模拟）。**执行**仍被锁在再后面的、单独 spec 的阶段，本审批包**不**授权执行。

## 当前全局安全状态

```text
can_run_probe_now                  = false
manual_approval_required_for_probe = true
tiny_canary_allowed                = no
edge_proven                        = no
wallet_or_tx_touched               = false
```
