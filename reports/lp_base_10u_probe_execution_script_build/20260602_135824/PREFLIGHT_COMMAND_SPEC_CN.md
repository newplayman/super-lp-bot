# Preflight Command Spec

- stage: `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_V1`
- phase: D
- run_id: `20260602_135824`
- script: `scripts/lp_base_10u_probe_executor_v1.py --mode preflight`

## 命令

```bash
python3 scripts/lp_base_10u_probe_executor_v1.py --mode preflight --run-id <RUN_ID> [--out-dir <DIR>]
```

## 允许的调用

- `eth_chainId` — 期望 8453
- `eth_blockNumber` — log
- `eth_gasPrice` — log
- `eth_getBalance(wallet)` — 期望 ≥ 9.0e-5 ETH
- `ERC20.balanceOf(wallet, USDC)` — 期望 ≥ 12 USDC
- `ERC20.balanceOf(wallet, WETH)` — log
- `ERC20.allowance(wallet, NPM, USDC)` — log；< 10 = 需新 ApproveExact
- `ERC20.allowance(wallet, NPM, WETH)` — log
- `pool.slot0()` — current_tick 在 [-200643, -200243] 附近
- `pool.liquidity()` — > 1e15
- `QuoterV2.quoteExactInputSingle` (best-effort; publicnode 已知会 revert)
- `eth_estimateGas(mint_call)` — 180k ± 2x

## 禁止

- signing / sending / approve / mint / collect / decrease / increase / swap / bridge

## 输出

- `reports/lp_base_10u_probe_execution_runtime/<run_id>/preflight_result.json`（local only）
- stdout: 同样 JSON（方便 pipeline 消费）

## 退出码

| 情形 | code |
|---|---|
| 全部 green | 0 |
| 任意 abort_before_entry stop 触发 | 0（但 preflight_status=FAIL） |
| RPC 不可用 | 0（记录 WARN，不阻断） |
| 禁止 env var 存在 | 4 |
| `--mode execute` rejected | 3 |

## 安全

```text
wallet_or_tx_touched = false
```
