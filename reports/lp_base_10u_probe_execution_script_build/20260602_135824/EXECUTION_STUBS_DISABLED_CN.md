# Execution Stubs (Disabled) Spec

- stage: `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_V1`
- phase: I
- run_id: `20260602_135824`

## 7 个 disabled stubs

每个 stub 都 `raise ExecutionDisabledInBuildStage("EXECUTION_DISABLED_IN_BUILD_STAGE: ...")`

| # | 函数 | 抛出信息 |
|---|---|---|
| 1 | `approve_exact_usdc()` | `EXECUTION_DISABLED_IN_BUILD_STAGE: approve_exact_usdc() is a stub. Real execution requires LP_BASE_10U_PROBE_EXECUTION_SCRIPT_REVIEW_V1 + fresh user approval.` |
| 2 | `approve_exact_weth()` | `EXECUTION_DISABLED_IN_BUILD_STAGE: approve_exact_weth() is a stub.` |
| 3 | `mint_position()` | `EXECUTION_DISABLED_IN_BUILD_STAGE: mint_position() is a stub.` |
| 4 | `monitor_position()` | `EXECUTION_DISABLED_IN_BUILD_STAGE: monitor_position() is a stub.` |
| 5 | `decrease_liquidity()` | `EXECUTION_DISABLED_IN_BUILD_STAGE: decrease_liquidity() is a stub.` |
| 6 | `collect_fees()` | `EXECUTION_DISABLED_IN_BUILD_STAGE: collect_fees() is a stub.` |
| 7 | `revoke_allowance()` | `EXECUTION_DISABLED_IN_BUILD_STAGE: revoke_allowance() is a stub.` |

## Exception 类

```python
class ExecutionDisabledInBuildStage(RuntimeError): pass
```

## 硬性保证

```text
no_signer_constructed        = true
no_wallet_client_constructed = true
no_tx_sent                    = true
no_approval_executed          = true
no_mint_executed              = true
no_collect_executed           = true
no_swap_executed              = true
no_bridge_initiated           = true
no_live_loop_started          = true
no_background_process_left    = true
```

## 理由

stubs 是**未来** executor 实际实现的占位符。未来 executor 必须由**独立 review stage** 构建 + 在**执行时点**要求**操作员重新键入审批短语**。本轮任何对 stub 的直接调用都是**编程错误**；test 套件断言每个 stub 都 raise。

## 安全

```text
wallet_or_tx_touched = false
can_run_probe_now    = false
tiny_canary_allowed  = no
edge_proven          = no
```
