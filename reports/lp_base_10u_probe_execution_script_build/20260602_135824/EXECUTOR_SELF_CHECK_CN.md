# Executor Self-Check 报告

- stage: `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_V1`
- phase: J
- run_id: `20260602_135824`

> 全部 self-check 都在 read-only 模式下运行。本轮**未执行**任何 probe；未发任何交易。

## Self-check 11 个 case 全部通过

| # | case | status | 退出码 | 备注 |
|---|---|---|---|---|
| 1 | `--mode preflight` | PASS | 0 | chain_id=8453, block=46810094, current_tick=-200501, all stops 0/13 |
| 2 | `--mode print-unsigned` | PASS | 0 | unsigned_only / no_signature / no_send / execution_not_authorized 全部 true |
| 3 | `--mode validate-approval` (valid) | PASS | 0 | valid=True, **executes_now=False, authorization_granted=False** |
| 4 | `--mode validate-approval` (20U) | REJECTED | 0 | regex 不匹配（notional=20 != 10） |
| 5 | `--mode validate-approval` (EXECUTE) | REJECTED | 0 | regex 不匹配（前缀错） |
| 6 | `--mode validate-approval` (30m) | REJECTED | 0 | dangerous word `\b30m\b` |
| 7 | `--mode validate-approval` (wrong wallet) | REJECTED | 0 | cross-check: wallet != frozen |
| 8 | `--mode validate-approval` (wrong pool) | REJECTED | 0 | cross-check: pool != frozen |
| 9 | `--mode validate-approval` (placeholder USER_PROVIDED) | REJECTED | 0 | regex 不匹配 |
| 10 | `--mode execute-disabled` | STUB OK | **1** | 输出 EXECUTION_DISABLED_IN_BUILD_STAGE，exit 1 |
| 11 | `--mode execute` | REJECTED at argparse | 2 | argparse invalid choice（"execute" 不在 {preflight, print-unsigned, validate-approval, execute-disabled}） |

## Preflight 详情（来自 self_check #1）

| 字段 | 值 |
|---|---|
| chain_id | 8453 |
| block | 46810094 |
| current_tick | -200501（frozen -200443，漂移 58 ticks < 200 threshold） |
| current_liquidity | 611,751,674,894,800,076 (6.12e17) > 1e15 ✓ |
| USDC balance | 21.774783 (≥ 12 ✓) |
| WETH balance | 0.002470 WETH (≥ 0 ✓) |
| USDC → NPM allowance | 5.0 (≤ 50M, no stop triggered) |
| ETH native | 0.0000905 ETH (≥ 9e-5 ✓) |
| preflight_status | **PASS** |
| stops triggered | 0 / 13 |

## 关键 deviation

```text
DANGEROUS_WORD_PATTERNS 起初是 substring 匹配；这导致 canonical 短语
("APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT ...") 因为包含子串 "EXEC"（在 "EXECUTION" 中）
而被错误地拒绝。

修复：换成 whole-word regex via re.search(pat, phrase)，例如 r"\bEXEC\b" 而非 "EXEC"。
9 个 validate-approval 测试 case 全部产生正确 accept/reject 结果。
```

## 严格守住

```text
no_tx_sent                  = true
no_approval_executed        = true
no_mint_executed            = true
no_collect_executed         = true
no_swap_executed            = true
no_bridge_initiated         = true
executor_will_run_this_round = false
approval_phrase_effective_this_round = false
wallet_or_tx_touched         = false
can_run_probe_now            = false
tiny_canary_allowed          = no
```

## Artifacts

```text
reports/lp_base_10u_probe_execution_runtime/20260602_135824/preflight_result.json
reports/lp_base_10u_probe_execution_runtime/20260602_135824/unsigned_package.json
reports/lp_base_10u_probe_execution_runtime/20260602_135824/approval_validation.json
```
