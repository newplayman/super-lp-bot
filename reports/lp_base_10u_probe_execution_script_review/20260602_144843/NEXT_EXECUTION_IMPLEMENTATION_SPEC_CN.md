# 下一阶段 Execution Implementation Spec

- stage: `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_REVIEW_V1`
- phase: J
- run_id: `20260602_144843`
- 下一阶段: `LP_BASE_10U_PROBE_EXECUTION_IMPLEMENTATION_V1`（**本轮不实现**）

> ⚠️ **本阶段只 design。下一阶段才允许实现真正 signer / transaction send 逻辑。下一阶段仍不能自动执行；执行仍需操作员在执行时点单独键入审批短语。**

## 1. 下一阶段允许

- 构造真实 signer（`Account.from_key` 或 `LocalAccount`），key 仅在执行时点从用户显式提供的路径加载
- 构造真实 web3.py `Web3` 实例，指向用户选择的 RPC
- 调用 `contract.functions.<method>().transact()` 发送 approve / mint / decrease / collect / revoke
- 等待 12 个 block confirmations
- 解码 ERC721 Transfer event 取 tokenId
- 记录 actual fee accrual 和 final PnL

## 2. 下一阶段仍禁止

- **自动执行**：下一阶段不自行跑 probe；它实现执行能力；执行仍需用户在执行时点重新键入审批短语
- **跳过 re-approval**：任何真实 send 都要求用户在**执行时点**（不是 build 时点）重新键入审批短语
- **ApproveMax**：必须 ApproveExact
- **swap-back**：不自动 WETH → USDC
- **bridge**：不跨链
- **live / canary / paper**：不启动
- **多池**：只动 frozen `0x72ab388e..`
- **超出审批 notional**

## 3. 下一阶段默认 dry-run

| 项 | 行为 |
|---|---|
| 默认 mode | **dry-run** |
| dry-run 做什么 | load wallet（after approval）+ 构建所有 tx calldata（approve + mint + decrease + collect + revoke）+ log 每步 + **不广播** |
| dry-run 不做什么 | 不广播任何 tx；不发任何 signed payload；不留任何后台进程 |
| dry-run 退出码 | 0（带 summary report） |

## 4. 显式审批 gate

| 项 | 值 |
|---|---|
| gate 机制 | 用户在**执行时点**键入审批短语（不是 build 时点） |
| 短语 | `APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0x<...> pool=0x... notional=10 hold=15m`（不变） |
| 校验 | regex + whole-word dangerous-word + cross-check（与 build stage 一致） |
| 短语匹配后是否自动执行 | **不**自动执行；要求用户**额外**在单独 prompt 输入 `YES`（第二道 gate） |
| 短语有效期 | 15 min |
| 防止 replay | session_id 必须唯一；重用 session_id 拒绝 |

## 5. 审计 trail

| 项 | 行为 |
|---|---|
| 每步 structured JSON log | ✓ |
| 每个 signed tx hash | log |
| 重新跑 forbidden env-var check | ✓（执行时点） |
| 不静默 retry | ✓（retry 需新审批） |

## 6. Safety invariants（继承自 build stage）

| invariant | 行为 |
|---|---|
| #3 dryrun broadcast == 0 | 执行时点也必须 hold（独立 dry-run confirmation 阶段） |
| #4 MinOut / Deadline nonzero | **deadline 必须 now+3600**（不是 2099-01-01 placeholder） |
| #9 ApproveExact only | ApproveMax 拒绝 |
| #10 post-exit revoke | 退出后 `approve(NPM, 0)` for WETH + USDC |

## 7. Review 推荐

```text
decision = PASS
rationale = 6 个 review 维度（static security / mode behavior / preflight / unsigned / approval / stubs / telemetry）全部通过
next_stage = LP_BASE_10U_PROBE_EXECUTION_IMPLEMENTATION_V1
if_review_fails = LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_FIX_REPEAT
```

## 安全

```text
wallet_or_tx_touched = false
can_run_probe_now    = false
tiny_canary_allowed  = no
```
