# Execution Stubs Review

- stage: `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_REVIEW_V1`
- phase: H
- run_id: `20260602_144843`

## 7 个 disabled stubs 全部审查

| # | 函数 | raises | 抛出信息包含 | result |
|---|---|---|---|---|
| 1 | `approve_exact_usdc()` | `ExecutionDisabledInBuildStage` | `EXECUTION_DISABLED_IN_BUILD_STAGE: approve_exact_usdc() is a stub. Real execution requires LP_BASE_10U_PROBE_EXECUTION_SCRIPT_REVIEW_V1 + fresh user approval.` | **PASS** |
| 2 | `approve_exact_weth()` | `ExecutionDisabledInBuildStage` | `EXECUTION_DISABLED_IN_BUILD_STAGE: approve_exact_weth() is a stub.` | **PASS** |
| 3 | `mint_position()` | `ExecutionDisabledInBuildStage` | `EXECUTION_DISABLED_IN_BUILD_STAGE: mint_position() is a stub.` | **PASS** |
| 4 | `monitor_position()` | `ExecutionDisabledInBuildStage` | `EXECUTION_DISABLED_IN_BUILD_STAGE: monitor_position() is a stub.` | **PASS** |
| 5 | `decrease_liquidity()` | `ExecutionDisabledInBuildStage` | `EXECUTION_DISABLED_IN_BUILD_STAGE: decrease_liquidity() is a stub.` | **PASS** |
| 6 | `collect_fees()` | `ExecutionDisabledInBuildStage` | `EXECUTION_DISABLED_IN_BUILD_STAGE: collect_fees() is a stub.` | **PASS** |
| 7 | `revoke_allowance()` | `ExecutionDisabledInBuildStage` | `EXECUTION_DISABLED_IN_BUILD_STAGE: revoke_allowance() is a stub.` | **PASS** |

## 硬性保证

```text
no_stub_sends_tx        = true
no_stub_creates_signer = true
no_stub_reads_key      = true
all_7_stubs_disabled   = true
```

## 测试覆盖

`tests/test_lp_base_10u_probe_executor_v1_build.py` 有 7 个专门的 stub test case：

```python
def test_approve_exact_usdc_raises(mod): ...
def test_approve_exact_weth_raises(mod): ...
def test_mint_position_raises(mod): ...
def test_monitor_position_raises(mod): ...
def test_decrease_liquidity_raises(mod): ...
def test_collect_fees_raises(mod): ...
def test_revoke_allowance_raises(mod): ...
```

7 个 test 全部通过（已在上阶段 Phase L 验证）。

## 理由

stubs 是**未来** executor 实际实现的占位符。任何对 stub 的直接调用都是**编程错误**。

## 安全

```text
wallet_or_tx_touched = false
can_run_probe_now    = false
tiny_canary_allowed  = no
```
