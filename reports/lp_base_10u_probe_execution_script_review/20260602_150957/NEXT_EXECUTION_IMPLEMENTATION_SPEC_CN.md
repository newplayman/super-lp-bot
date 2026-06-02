# 下一阶段 Execution Implementation Spec

- stage: `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_REVIEW_V1`
- phase: J
- run_id: `20260602_150957`
- 下一阶段: `LP_BASE_10U_PROBE_EXECUTION_IMPLEMENTATION_V1`（**本轮不实现**）

> ⚠️ **本阶段只 design。下一阶段才允许实现真正 signer / transaction send 逻辑。下一阶段仍不能自动执行；执行仍需操作员在执行时点单独键入审批短语。**

## ⚠️ 本轮 re-run 新增：tick drift 提醒

本轮 re-run 在 ~13 分钟内观察到 `current_tick` 从 -200609 漂移到 -200662（53 ticks 漂移），累计漂移 219 ticks，**触发** `stop_tick_moved_outside_planned_range_before_entry`（WARN, manual_intervention_required）。

**未来 implementation stage 必须做的事**：

- 重新读 `current_tick`
- 重新计算 tick range（建议 lower_tick < -200862，upper_tick > -200462；例如 lower=-200900, upper=-200400，3x margin）
- **走新审批短语**（新 session_id；不重用 frozen 的 [-200643, -200243]）
- 不能盲目用 frozen range

**建议**未来 stage 把 tick range 纳入审批短语（新增 `lower_tick=...` `upper_tick=...` 字段），或单独的 `tick_range_reapproval` gate。

## 1. 下一阶段允许

- 构造真实 signer（`Account.from_key` 或 `LocalAccount`），key 仅在执行时点从用户显式提供的路径加载
- 构造真实 web3.py `Web3` 实例，指向用户选择的 RPC
- 调用 `contract.functions.<method>().transact()` 发送 approve / mint / decrease / collect / revoke
- 等待 12 个 block confirmations
- 解码 ERC721 Transfer event 取 tokenId
- 记录 actual fee accrual 和 final PnL

## 2. 下一阶段仍禁止

- **自动执行**
- **跳过 re-approval**
- **ApproveMax**
- **swap-back**
- **bridge**
- **live / canary / paper**
- **多池**
- **超出审批 notional**

## 3. 下一阶段默认 dry-run

| 项 | 行为 |
|---|---|
| 默认 mode | **dry-run** |
| dry-run 做什么 | load wallet + 构建所有 tx calldata + log 每步 + **不广播** |
| dry-run 不做什么 | 不广播任何 tx；不发任何 signed payload；不留任何后台进程 |

## 4. 显式审批 gate

| 项 | 值 |
|---|---|
| gate 机制 | 用户在**执行时点**键入审批短语 |
| 短语 | `APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT ...` |
| 校验 | regex + whole-word dangerous-word + cross-check |
| 短语匹配后 | 用户**额外**在单独 prompt 输入 `YES`（第二道 gate） |
| 有效期 | 15 min |
| 防止 replay | session_id 必须唯一 |

## 5. Safety invariants（继承自 build stage）

| invariant | 行为 |
|---|---|
| #3 dryrun broadcast == 0 | 独立 dry-run confirmation 阶段 |
| #4 MinOut / Deadline nonzero | **deadline 必须 now+3600**（不是 2099-01-01 placeholder） |
| #9 ApproveExact only | ApproveMax 拒绝 |
| #10 post-exit revoke | 退出后 `approve(NPM, 0)` for WETH + USDC |

## 6. Review 推荐

```text
decision = PASS
rationale = 7 个 review 维度全部通过；preflight WARN 证明 stop engine 工作正常
next_stage = LP_BASE_10U_PROBE_EXECUTION_IMPLEMENTATION_V1
if_review_fails = LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_FIX_REPEAT
```

## 安全

```text
wallet_or_tx_touched = false
can_run_probe_now    = false
tiny_canary_allowed  = no
```
