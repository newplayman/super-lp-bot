# 静态安全审查

- stage: `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_REVIEW_V1`
- phase: C
- run_id: `20260602_150957`
- 审查脚本: `scripts/lp_base_10u_probe_executor_v1.py` (845 行, 31493 字节)

> Re-run note: 与上一轮 `596b411` 审查结果一致。脚本源文件未变（`script_changed_since_last_review=false`）。

## 1. 文件元数据

| 字段 | 值 |
|---|---|
| 路径 | `scripts/lp_base_10u_probe_executor_v1.py` |
| 行数 | 845 |
| 字节 | 31493 |

## 2. 11 项检查

| # | 检查 | matches | 结果 |
|---|---|---|---|
| 1 | private_key 加载 | **0** | **PASS** |
| 2 | eth_sendTransaction | **0** | **PASS** |
| 3 | approve/mint/decreaseLiquidity/collect 执行 | **0** | **PASS** |
| 4 | private_key env lookup | **0** | **PASS** |
| 5 | default mode 是 preflight | n/a | **PASS** |
| 6 | `--mode execute` 被拒绝 | 0 | **PASS** |
| 7 | execution stubs disabled | 7 | **PASS** |
| 8 | forbidden env-var patterns 已列 | 15 | **PASS** |
| 9 | dangerous word patterns 已列 | 27 | **PASS** |
| 10 | 无 hidden auto-run | n/a | **PASS** |
| 11 | 无 subprocess 调用 | 0 | **PASS** |

## 3. argparse choices 审计

```python
p.add_argument("--mode", required=True,
               choices=["preflight", "print-unsigned", "validate-approval", "execute-disabled"],
               help="Mode of operation. 'execute' is REJECTED ...")
```

`--mode execute` **不在** choices 内，argparse 直接拒绝（exit 2）。

## 4. defense-in-depth

main() 函数开头有：

```python
if args.execute or args.mode == "execute":
    sys.stderr.write("REJECTED: --mode execute is not allowed in this build stage.\n")
    return 3
```

这是**第二道**防线，即使 argparse 误配也兜底。

## 5. execution stub 全部 disabled

7 个 stub：`approve_exact_usdc`, `approve_exact_weth`, `mint_position`, `monitor_position`, `decrease_liquidity`, `collect_fees`, `revoke_allowance`

每个 stub 都 `raise ExecutionDisabledInBuildStage(...)`。

## 6. 总体结果

```text
overall = PASS
any_dangerous_match = false
```

无任何危险命中。脚本**安全可作为**未来执行实现阶段的基础。

## 安全

```text
wallet_or_tx_touched = false
can_run_probe_now    = false
tiny_canary_allowed  = no
```
