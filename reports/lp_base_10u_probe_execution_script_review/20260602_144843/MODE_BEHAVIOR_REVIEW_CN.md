# Mode Behavior Review

- stage: `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_REVIEW_V1`
- phase: D
- run_id: `20260602_144843`

## 11 个 case 全部通过

| # | command | expected exit | actual exit | result | notes |
|---|---|---|---|---|---|
| D1 | `--mode preflight` | 0 | 0 | **PASS** | preflight_status=PASS, 0/13 stops |
| D2 | `--mode print-unsigned` | 0 | 0 | **PASS** | unsigned_only / no_signature / no_send / execution_not_authorized 全 true |
| D3 | `--mode validate-approval` (valid) | 0 | 0 | **PASS** | valid=True, **executes_now=False, authorization_granted=False** |
| D4a | `--mode validate-approval` (20U) | 0 | 0 | **PASS** | regex 不匹配 (notional=20) |
| D4b | `--mode validate-approval` (30m) | 0 | 0 | **PASS** | dangerous word `\b30m\b` |
| D4c | `--mode validate-approval` (wrong wallet) | 0 | 0 | **PASS** | cross-check: wallet != frozen |
| D4d | `--mode validate-approval` (wrong pool) | 0 | 0 | **PASS** | cross-check: pool != frozen |
| D4e | `--mode validate-approval` (EXECUTE) | 0 | 0 | **PASS** | regex 不匹配 (prefix 错) |
| D5 | `--mode execute-disabled` | **non-zero (1)** | **1** | **PASS** | EXECUTION_DISABLED_IN_BUILD_STAGE |
| D6 | `--mode execute` | non-zero (2) | 2 | **PASS** | argparse invalid choice |
| D7 | `--mode preflight --execute` | **3** | **3** | **PASS** | defense-in-depth abort |

## 关键观察

### D3 (validate-approval valid)
- valid=True（phrase 格式正确、cross-check 通过）
- **executes_now=False** ← 关键：成功校验**不**授权执行
- **authorization_granted=False** ← 关键：成功校验**不**视为已批准

### D5 (execute-disabled)
- exit_code=1
- `error: EXECUTION_DISABLED_IN_BUILD_STAGE`
- 永远不会调用任何真实执行

### D6 + D7 (--mode execute 双层防御)
- D6: argparse invalid choice → exit 2
- D7: 即使绕过 argparse（例如改 main() 顺序），`if args.execute or args.mode == "execute": exit 3` 仍兜底

## 安全

```text
no_tx_sent                  = true
no_approval_executed        = true (D3 valid=True 但 executes_now=False)
no_mint_executed            = true
no_collect_executed         = true
no_swap_executed            = true
no_bridge_initiated         = true
executor_will_run_this_round = false (脚本只跑 read-only 模式)
wallet_or_tx_touched         = false
can_run_probe_now            = false
tiny_canary_allowed          = no
```
