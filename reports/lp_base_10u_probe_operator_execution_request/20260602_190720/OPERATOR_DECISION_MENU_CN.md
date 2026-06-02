# Operator Decision Menu

- stage: `LP_BASE_10U_PROBE_OPERATOR_EXECUTION_REQUEST_V1`
- phase: D
- run_id: `20260602_190720`

## 仅 3 个合法选项

> **当前阶段不得选择「直接执行」**。任何要求直接 send 的回复都会被拒绝。本菜单中没有 D（直接执行）选项。

---

### 选项 A — `APPROVE_BUILD_EXECUTION_RUNNER`

进入下一阶段：**`LP_BASE_10U_PROBE_EXECUTION_RUNNER_ARMED_BUILD_V1`**

```text
下一阶段会做什么：
  ✓ 在新增独立 commit 中解除 send hard-disable（仅源代码层）
  ✓ 构造 armed runner（仍默认 no-send / dry-run-only）
  ✓ 接入 skip_approve_if_allowance_sufficient 真实 wire
  ✓ 接入 mint_receipt schema 真实解析
  ✓ 接入 actual_fee telemetry 真实落盘
  ✓ 接入 abort_before_entry 路径
  ✓ 接入 emergency stop 路径

下一阶段不会做什么：
  × 不发送任何交易
  × 不构造 signer / 不加载私钥
  × 不接受 one-shot execution phrase
  × 不调用 eth_sendRawTransaction
```

下一阶段使用的接受短语：
```text
APPROVE_BUILD_BASE_10U_PROBE_EXECUTION_RUNNER wallet=0xb05b2872ace4564ff247555b6f7b097d31f3d835 pool=0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 notional=10 hold=15m
```

**A 不是执行授权** — 它只授权构建一个能在更晚阶段执行的工具；执行还要再走一阶段。

---

### 选项 B — `REQUEST_AUTH_PACKAGE_FIX`

进入 **`LP_BASE_10U_PROBE_EXECUTION_AUTHORIZATION_PACKAGE_FIX_REPEAT`**

适合以下情景：
- 操作员想 **调整** 27 项 pre-execution checklist 中某些 gate 的阈值（如 gas / slippage / hold）
- 操作员想 **修改** tick range margin（当前固定 ±200 ticks）
- 操作员想 **改写** mint receipt schema 或 fee telemetry 时间点
- 操作员想 **改写** 6 项允许 tx whitelist 或 13 项禁止 blacklist
- 操作员想 **重写** 最坏 case 风险接受标准（当前 ~20 USD）

返回上一阶段，修改后再走一遍 final review → authorization package → operator request。

---

### 选项 C — `STOP`

进入 **`STOP_LP_RESEARCH_NOW`**

适合以下情景：
- 操作员决定本 probe 不值得做
- 操作员资金不允许 ~20 USD 损失
- 操作员决定 LP 研究永久 / 暂时停止
- 操作员发现某项 deviation 不可接受

**保留所有 artifacts** — 报告、telemetry、test、commit、push 历史全部留存。可日后用 LP_BASE_10U_PROBE_EXECUTION_AUTHORIZATION_PACKAGE_FIX_REPEAT 或新 stage 重启。

---

## 决策矩阵

| 用户意图 | 选项 |
|---|---|
| 我要继续，但仍要更多保护层 | **A** |
| 我看到包里某项不对，想改 | **B** |
| 我不想做 | **C** |
| **我想现在就发交易** | **NOT_ALLOWED IN THIS STAGE** |

## 选择后的下一阶段链

```text
A → LP_BASE_10U_PROBE_EXECUTION_RUNNER_ARMED_BUILD_V1
       (build only; still no-send by default)
    → LP_BASE_10U_PROBE_EXECUTION_RUNNER_FINAL_REVIEW_V1
       (review armed runner)
    → LP_BASE_10U_PROBE_FIRST_EXECUTION_REQUEST_V1
       (request operator confirmation to actually send)
    → LP_BASE_10U_PROBE_FIRST_EXECUTION_RUN_V1
       (now and only now, actual send may happen if operator types one-shot phrase)

B → LP_BASE_10U_PROBE_EXECUTION_AUTHORIZATION_PACKAGE_FIX_REPEAT
    → (repeat final review → authorization package → operator request)

C → STOP_LP_RESEARCH_NOW
    → (artifacts preserved; no further action)
```

## 本阶段不解析任何用户输入

```text
this_stage_accepts_a_b_c_choice_directly = false
this_stage_executes_selected_branch      = false
this_stage_writes_chain_state            = false
operator_choice_recorded_in_this_run     = false  # 等下一个由用户启动的 stage
```

操作员要选 A/B/C，须在下一个 stage 命令的 prompt 中明确表达。当前 run 仅展示菜单。

## 安全（本阶段不变量）

```text
wallet_or_tx_touched          = false
can_run_probe_now             = false
execution_allowed_now         = false
hard_disable_still_active     = true
tiny_canary_allowed           = no
edge_proven                   = no
operator_choice_recorded      = false
```
