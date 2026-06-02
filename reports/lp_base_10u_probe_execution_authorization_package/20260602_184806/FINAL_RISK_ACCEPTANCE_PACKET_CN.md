# Final Risk Acceptance Packet

- stage: `LP_BASE_10U_PROBE_EXECUTION_AUTHORIZATION_PACKAGE_V1`
- phase: I
- run_id: `20260602_184806`

## 风险陈述 — 操作员必须明确接受才允许进入下一阶段

### 1. realistic EV 没有证明为正

| 事实 | 来源 |
|---|---|
| 当前 `edge_proven = no` | 所有上游 FINAL_VERDICT.json |
| 当前 `tiny_canary_allowed = no` | 所有上游 FINAL_VERDICT.json |
| 当前 LP strategy research 处于 FROZEN | `docs/LPBOT_RESEARCH_STATUS_CN.md` 与 `CLAUDE.md` |
| 历史 backtest 与 paper 无法证明正 EV | 历史 `reports/final_freeze/20260531_124000/` |

**这个 probe 是真金白银的数据采集**，不是一个被证明会赚钱的策略实验。

### 2. 本 probe 的真正目的

| 不是 | 是 |
|---|---|
| 不是赚钱实验 | 是 actual fee accrual 数据采集 |
| 不是策略验证 | 是 mint / decreaseLiquidity / collect 通道是否真的能跑通的验证 |
| 不是 canary 启动 | 是单次 isolated 一次性 probe，本轮结束后不开始第二轮 |
| 不是 production scale | 10 USD 是 sandbox 量级 |

### 3. 10U 可能亏损 — 全部情景

| 情景 | 失败模式 | 损失上限 |
|---|---|---|
| gas 损失 | mint 或 decreaseLiquidity 或 collect 任一笔 gas 浪费 | ~5-10 USD gas（如果 4 笔 tx 都跑且 gas 突然飙升） |
| slippage 损失 | mint 实际 fill 量 < amount1Min；mint 会 revert，gas 损失 | gas 不超过 amount1Min - amount1Filled |
| IL（impermanent loss） | 15 分钟内 tick 漂出 range 或 price 大幅移动 | 理论上 10U 中可能 0.x-1.x USD（窄 range 中 IL 是放大的） |
| swap pool 行情逆向 | hold 期间 price 反向 ⇒ 退出时 token mix 变成更多 WETH，USDC 价值更低 | 同上 |
| failed tx | RPC 故障 / nonce 撞 / replacement tx | gas + 部分 partial 头寸卡在 NPM |
| stuck position | decreaseLiquidity 成功但 collect 失败 | tokens stuck，需 manual collect |
| ApproveExact 后 NPM 调用失败 | USDC allowance 已给但 mint 失败 ⇒ 必须 revoke | 仅 gas 损失 |
| 最坏情景 — 全部资金 + gas 全损 | mint 成功，hold 期间 pool 出现极端事件（hack / 大单 / depeg），exit 时余下 token 价值 ~ 0 | 10 USD + ~5-10 USD gas = **~20 USD** 全损 |

### 4. **最坏 case** 操作员必须接受

```text
最坏情况下，本 probe 会损失 ~20 USD（10U 本金 + 估计 5-10 USD gas）。
操作员必须在心理上、财务上、操作上完全接受这个损失才能进下一阶段。
```

### 5. 成功标准 — 不是赚钱

| 必须达到才算"成功" | 来源 |
|---|---|
| `token_id` 提取成功（mint receipt 解析） | Stage F schema |
| `entry_fee_state` 记录完整 | Stage G schema |
| `hold_fee_state` 至少 1 次 | Stage G schema |
| `pre_exit_fee_state` 记录完整 | Stage G schema |
| `post_collect_fee_state` 记录完整 | Stage G schema |
| `actual_fee_earned_USDC_raw` 与 `actual_fee_earned_WETH_wei` 通过 collect-decrease delta 计算 | Stage G schema |
| `actual_PnL_USD` 通过 entry / exit / gas 计算 | future runner |
| 4 笔 tx 的 gas（entry / exit / approve / revoke）全部记录 | mint_receipt / collect_receipt / approve_receipt / revoke_receipt |
| telemetry 全部 7 + 4 artifact 写盘 | Stage I |
| **以上全部完成才算 probe 成功**；**实际是否赚钱、是否亏损不影响 "成功" 判定** | 本风险接受包 |

### 6. 数据将进入哪里

| 数据 | 去处 |
|---|---|
| receipt / tokenId / positions / fee state / collect amounts / PnL | 本地 `reports/lp_base_10u_probe_execution_runtime/<RUN_ID>/` |
| **不**进入 production positions 表 | 与 freeze 一致 |
| **不**覆盖 shadow 原始表 | 与 freeze 一致 |
| **不**触发 strategy / scanner / audit / pnl service | 仅一次性脚本 |

### 7. 失败时操作员必须做什么

- 接受 ~20 USD 损失（最坏 case），不要 emotionally 试图"扳回"
- 写一份 post-mortem，记录 deviation / 教训 / 是否值得重做
- 不要立即重新跑第二轮（即使代码允许，本 probe spec 也禁止 auto-repeat）
- 在 `STOP_LP_RESEARCH_NOW` 与 `LP_BASE_10U_PROBE_EXECUTION_AUTHORIZATION_PACKAGE_FIX_REPEAT` 之间冷静选择
- 不要在 hot state 下解封 hard-disable 或修改 approval gate

### 8. 操作员的明确确认 — 进下一阶段前必须心理签字

```text
[ ] 我理解 EV 没有证明为正
[ ] 我理解本 probe 不是策略验证，是数据采集
[ ] 我能承受 ~20 USD 全损（10U + ~10U gas）
[ ] 我同意"成功"指的是数据完整，不是赚钱
[ ] 我不会在第一轮完成前自动开第二轮
[ ] 我接受 manual intervention 是合法响应
[ ] 我接受 hard-disable 必须单独 commit 解除
[ ] 我接受 fresh approval 在任何 drift > 200 时都必须重新输入
```

每一项必须在心理 + 文档上确认；不要快速跳过。

## 安全（本阶段不变量）

```text
wallet_or_tx_touched          = false
can_run_probe_now             = false
tiny_canary_allowed           = no
edge_proven                   = no
execution_allowed_now         = false
risk_acceptance_packet_is_documentation_only = true
```
