# Executor v2 脚本设计

- stage: `LP_BASE_10U_PROBE_EXECUTION_IMPLEMENTATION_V1`
- phase: C
- run_id: `20260602_163036`
- script: `scripts/lp_base_10u_probe_executor_v2.py` (961 lines)

> ⚠️ **本轮实现执行能力代码，但绝对不执行 probe。** send 函数**存在**但**默认被三重门禁 + 双重 default safety flag 包裹**；`--mode execute-guarded` 在本 stage 永远 abort 1 + 抛 `ExecutionSendDisabledInImplementationBuildStage`。
> v1 (`scripts/lp_base_10u_probe_executor_v1.py`, 845 lines, build-stage skeleton) **保持不变**。

## 1. v2 支持的 5 种 mode

| mode | 用途 | 写文件 | 退出码 |
|---|---|---|---|
| `preflight` | read-only 链上状态 + 动态 tick range recompute | `preflight.json`, `dynamic_tick_range.json` | 0 |
| `print-unsigned` | 构造 unsigned approve + mint tx 包（dynamic tick range） | `unsigned_approve_package.json`, `unsigned_mint_package.json` | 0 |
| `validate-approval` | 解析 + 验证审批短语 + 计算 3-gate 状态 | `approval_check.json` | 0 |
| `implementation-self-check` | 综合 self-check（preflight + unsigned + approval + execute-guarded abort）| 7 schema files | 0 |
| `execute-guarded` | 校验 3-gate；**永远 abort** | n/a | **1** |

## 2. 被拒绝的 mode

| mode | 行为 |
|---|---|
| `execute` | argparse invalid choice（不在 choices 内） |

## 3. 三重执行门禁

| gate | 描述 | 实现 | 是否可绕过 |
|---|---|---|---|
| **gate_1** | 显式 `--mode execute-guarded` | argparse choices 强制 | 不可 |
| **gate_2** | 审批短语 regex 精确匹配 | `parse_approval_phrase()` + 27 个 whole-word dangerous-word pattern | 不可（whole-word 匹配，不命中 canonical EXEC 子串） |
| **gate_3** | `--i-understand-this-sends-real-transactions` 第二道 flag | argparse `action="store_true"` | 不可（无 flag 默认 False） |

## 4. 两个 default safety flags

| flag | default | 含义 |
|---|---|---|
| `--dry-run-only` | **true** | 只构造 tx；不广播 |
| `--no-send` | **true** | 不发送任何 signed payload |

## 5. 实现的"真实 send 路径"（**全部不 send**）

| 函数 | 描述 | send？ |
|---|---|---|
| `build_approve_exact_usdc_tx` | ERC20.approve(USDC, NPM, amount)；输出结构化 tx | **否** |
| `build_revoke_usdc_tx` | approve(USDC, NPM, 0) | **否** |
| `build_revoke_weth_tx` | approve(WETH, NPM, 0) | **否** |
| `build_mint_position_tx` | NPM.mint(...recipient=wallet, deadline=**now+3600**) | **否** |
| `build_decrease_liquidity_tx` | NPM.decreaseLiquidity(tokenId, ...) | **否** |
| `build_collect_tx` | NPM.collect(tokenId, recipient=wallet, ...) | **否** |
| `build_revoke_allowance_tx` | 合并 revoke-USDC + revoke-WETH | **否** |
| `monitor_position_loop_stub` | 单次 stub（iterations<=1） | **否** |

## 6. 动态 tick range recompute

```text
read slot0 → current_tick
drift = current_tick - LEGACY_FROZEN_TICK (-200443)
proposed_range = (current_tick - 200, current_tick + 200)

abort if:
  - current_tick outside proposed range
  - |drift| > 200 (require fresh approval)
```

**不**直接用 frozen [-200643, -200243]；**不**硬编码 tick range 到 tx。Tick range 在 runtime 重算。

## 7. Deadline

```text
deadline = int(time.time()) + 3600  # now + 1h
deadline_is_now_plus_3600 = true
deadline_is_NOT_legacy_placeholder_2099 = true
```

deadline 实时生成；**不是** v1 的 placeholder `4070908800 (2099-01-01)`。

## 8. Telemetry runtime writer

写到 `reports/lp_base_10u_probe_execution_runtime/<run_id>/`：

```text
preflight.json
dynamic_tick_range.json
approval_check.json
unsigned_approve_package.json
unsigned_mint_package.json
stop_conditions.json
execution_gates.json
```

**不**写 production DB / shadow 表 / positions。

## 9. execute-guarded 永远 abort

```python
raise ExecutionSendDisabledInImplementationBuildStage(
    "EXECUTION_SEND_DISABLED_IN_IMPLEMENTATION_BUILD_STAGE: ..."
)
```

`sys.exit(1)`。**不广播任何 signed tx**。

## 10. 安全

```text
wallet_or_tx_touched     = false
can_run_probe_now        = false
tiny_canary_allowed      = no
edge_proven              = no
executor_v2_built         = true
executor_will_run_this_round = false
send_hard_disabled        = true (regardless of 3-gate status in this stage)
```
