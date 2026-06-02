# Armed Runner Build — LP_BASE_10U_PROBE_OVERNIGHT_ARMED_RUNNER_BUILD_AND_READONLY_MONITOR_V1

- stage: `LP_BASE_10U_PROBE_OVERNIGHT_ARMED_RUNNER_BUILD_AND_READONLY_MONITOR_V1`
- run_id: `20260602_193517`
- file: `scripts/lp_base_10u_probe_armed_runner_v1.py`
- v2 source: `scripts/lp_base_10u_probe_executor_v2.py` — **未修改 (line count 992)**

## 1. 设计目标

构建一个 armed runner 代码工件，但**不在本阶段真正发任何交易**。本阶段的 armed runner 行为是：

1. 默认 `--no-send`，`--dry-run-only`；
2. 复用 v2 的 read-only 路径（`dynamic_tick_range_recompute`、`encode_balance_of`、`encode_allowance`、`build_approve_exact_usdc_tx`、`build_mint_position_tx`、`build_revoke_*_tx`、`parse_approval_phrase`）；
3. **不**修改 v2 源码，**不**复制任何 v2 函数（v2 仍是 source of truth）；
4. `execute-armed` 模式**硬退出**本阶段，输出 `EXECUTION_NOT_AUTHORIZED_IN_OVERNIGHT_BUILD_STAGE`，exit code 1。

## 2. 6 个 mode

| mode | 行为 | 状态 |
|---|---|---|
| `status` | 打印自我安全断言（v2 hard-disable 仍存在、send 不可用） | OK（已 smoke） |
| `preflight` | 读链上状态：chain_id / ETH / USDC / WETH 余额 / USDC / WETH allowance / pool slot0 / liquidity / tickSpacing / dynamic tick range / stop conditions | OK（已 smoke） |
| `print-unsigned` | 用 v2 builder 生成 **unsigned** approveExact / mint / revoke envelopes（**不签、不发**） | OK（已编译） |
| `validate-approval` | 复用 v2 `parse_approval_phrase`；本阶段显式拒绝 one-shot phrase (`one_shot_accepted_in_this_stage=false`) | OK（已 smoke） |
| `monitor-readonly` | 一次性只读 preflight（不是长 monitor；长 monitor 在另一脚本） | OK |
| `execute-armed` | **硬退出**本阶段，stderr 写明 4 条 unseal 条件，stdout 0 字节，exit 1 | OK（已 smoke） |

## 3. 关键安全断言（v2 不可被改）

armed runner v1 在 `mode_status` 中运行 `_verify_v2_hard_disable_intact()`：

```python
{
  "v2_path": "/opt/lpbot/lp-bot-v3-origin-check/scripts/lp_base_10u_probe_executor_v2.py",
  "class_defined": True,                                # ExecutionSendDisabledInImplementationBuildStage
  "raise_site_present": True,                           # line 974
  "execute_guarded_mode_present": True,                 # --mode execute-guarded
  "v2_unmodified_by_this_build": True,
  "send_hard_disable_active": True
}
```

任何篡改 v2 源码让硬退出失效的尝试都会让此断言报警。

## 4. argparse 门禁（main 早退）

armed runner v1 的 `main()` 在 dispatcher 前先做 3 项硬检查：

- `args.wallet.lower() != "0xb05b2872ace4564ff247555b6f7b097d31f3d835"` → exit 2
- `args.notional != 10` → exit 2
- `args.hold != "15m"` → exit 2

任何错误参数组合（即便绕过 CLI 直接调 main）都会被这 3 项挡住。

## 5. 默认值表

| 标志 | 默认 | 不可被本阶段翻成 False |
|---|---|---|
| `--no-send` | True | 是（除非未来阶段 unseal + i-understand + 显式覆盖） |
| `--dry-run-only` | True | 同上 |
| `--i-understand-this-sends-real-transactions` | False | 同上 |
| `SEND_HARD_DISABLE_ACTIVE` | True | 同上 |
| `EXECUTION_ALLOWED_NOW` | False | 同上 |
| `CAN_RUN_PROBE_NOW` | False | 同上 |
| `TINY_CANARY_ALLOWED` | `"no"` | 同上 |

## 6. 本轮产物签名

```text
armed_runner_built                   = true
send_hard_disable_still_active       = true  (v2 line 974 raise 保留)
default_no_send                      = true
execute_armed_cannot_send_this_stage = true  (硬退出 EXECUTION_NOT_AUTHORIZED_IN_OVERNIGHT_BUILD_STAGE)
signer_path_not_called               = true  (v1 内无 Account.from_key / LocalAccount / sign_transaction)
wallet_client_not_created            = true  (v1 内无 Web3 / HTTPProvider)
can_run_probe_now                    = false
```

## 7. 不在本轮做的事

- **不** unseat v2 hard-disable（在 `unseal:` prefix commit 里做）
- **不**写一个独立 `executor_v3_armed.py`（armed runner v1 已存在并跑通）
- **不**接受 one-shot execution phrase（`is_one_shot_phrase=true` 仍被拒绝）
- **不**把任何 RPC 调用升级为 send（仅 eth_call / eth_getBalance / eth_chainId / 显式 eth_estimateGas 也不在 v1 中调用，留给 monitor）
- **不**触碰 monitor 子模块
- **不**调用 `v2.main()` 的 `--mode execute-guarded`（保留更小审计面）
