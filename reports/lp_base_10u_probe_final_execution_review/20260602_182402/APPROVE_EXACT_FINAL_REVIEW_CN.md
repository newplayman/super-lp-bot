# ApproveExact / no ApproveMax Final Review

- stage: `LP_BASE_10U_PROBE_FINAL_EXECUTION_REVIEW_V1`
- phase: F
- run_id: `20260602_182402`
- 审查源码:
  - `build_approve_exact_usdc_tx` l.399-424
  - `build_revoke_usdc_tx` l.427-450
  - `build_revoke_weth_tx` l.453-471
  - `build_revoke_allowance_tx` l.602-613
  - 阈值 `UINT256_MAX = (1 << 256) - 1` l.137；校验 `amount_raw >= UINT256_MAX // 2` l.406-407
  - `encode_allowance` l.209-210（helper 已就位）

## 静态审查矩阵

| # | 审查项 | 期望 | 源代码定位 | 实际 | 结果 |
|---|---|---|---|---|---|
| 1 | ApproveMax forbidden | true | l.406-407 `if amount_raw >= UINT256_MAX // 2: raise ValueError` | true | **PASS** |
| 2 | approve exact only | true | l.404-405 `if amount_raw <= 0: raise ValueError`；output `approve_exact_only=True`, `policy="ApproveExact (never ApproveMax)"` (l.420-421) | true | **PASS** |
| 3 | USDC approval amount bounded | true | l.404 + l.406 双侧 bound；典型值 `10_000_000` (10 USDC * 1e6) | true | **PASS** |
| 4 | WETH approval only if required | true | 当前 v2 中 `build_revoke_weth_tx` 仅 revoke(0)；mint 路径不构造 WETH approve（因为 `amount0_desired_wei=0` 仅 USDC 单边 deposit） | true | **PASS** |
| 5 | post-exit revoke planned | true | `build_revoke_usdc_tx` / `build_revoke_weth_tx` / `build_revoke_allowance_tx` 全部存在；policy 字段标记 `"post-exit revoke"` | true | **PASS** |
| 6 | no approve execution this review | true | 所有 builder 返 dict, 设 `no_send:true, transaction_sent:false, unsigned_only:true` | true | **PASS** |
| 7 | approve tx object can be built but not sent | true | 见 #6；本 review 已生成 unsigned_approve_package 文件（来自 Stage D preflight 调用 print-unsigned 路径） | true | **PASS** |
| 8 | 若 allowance 已足够，无需 approve | partial | `encode_allowance` helper 存在 (l.209-210)，但 v2 没有 caller-level skip 逻辑。**实际 send 阶段（未来 authorization package）必须显式 wire `allowance` 读取 + skip approve_tx 构造**。本 stage 永远 hard-disabled，所以暂无危险。 | partial — **deviation 记录** | **WARN（非阻断）** |

## deviation 详情

**deviation_id**: `approve_skip_if_already_sufficient_not_wired`

- **现象**: `encode_allowance` 已经实现，但 v2 在 `build_approve_exact_usdc_tx` / print-unsigned 路径中没有先调用 `eth_call(USDC, encode_allowance(wallet, NPM))` 检查 `current_allowance >= amount_raw`，因此每轮都会输出 `unsigned_approve_package`，不论 NPM 是否已被授权过。
- **影响（实质）**: 在 hard-disable 阶段为 0。在未来 `LP_BASE_10U_PROBE_EXECUTION_AUTHORIZATION_PACKAGE_V1` 阶段必须新增 `skip_approve_if_allowance_sufficient` 逻辑 OR 在 ops-runbook 明确说明：操作员需先手工 `eth_call` 检查 allowance，若已 >= 10_000_000 则跳过签 approve_tx。
- **当前阶段是否阻断**: **否** — 本阶段 send 已 hard-disabled，且 `build_approve_exact_usdc_tx(10_000_000)` 本身没有副作用。建议作为 authorization package 阶段的强制 prerequisite。

## 5 项测试 cross-reference (来自 implementation stage 已通过)

| # | test | result |
|---|---|---|
| 1 | build_approve_exact_usdc_tx(10 USDC) | PASS — amount_raw=10000000, approvemax_forbidden=True, no_send=True |
| 2 | build_revoke_usdc_tx() | PASS — amount_raw=0, no_send=True |
| 3 | build_revoke_weth_tx() | PASS — amount_raw=0, no_send=True |
| 4 | build_approve_exact_usdc_tx(UINT256_MAX // 2) | PASS rejected — ValueError "ApproveMax forbidden" |
| 5 | build_approve_exact_usdc_tx(0) | PASS rejected — ValueError "must be > 0" |

## 本轮 review 生成的 unsigned_approve_package 摘要

写入 `reports/lp_base_10u_probe_execution_runtime/20260602_182402/unsigned_approve_package.json`（来自 Stage D preflight 调用）：默认 schema-only 占位，实际 approve 包结构待 Stage H print-unsigned 模式生成。

## verdict

| field | value |
|---|---|
| approvemax_forbidden | true |
| approve_exact_only | true |
| usdc_amount_bounded | true |
| weth_approval_only_if_required | true |
| post_exit_revoke_planned | true |
| no_approve_execution_this_review | true |
| approve_tx_can_be_built_not_sent | true |
| allowance_sufficient_skip_wired | false (deviation logged) |
| approve_exact_review_pass | **true** (deviation 非阻断；需在 authorization package 阶段补) |

## 安全（本阶段不变量）

```text
wallet_or_tx_touched          = false
can_run_probe_now             = false
tiny_canary_allowed           = no
approve_executed              = false
allowance_check_executed_in_this_review = false
```
