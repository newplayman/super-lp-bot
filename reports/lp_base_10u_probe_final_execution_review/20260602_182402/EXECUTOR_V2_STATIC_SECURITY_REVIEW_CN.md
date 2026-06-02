# Executor V2 Static Security Review

- stage: `LP_BASE_10U_PROBE_FINAL_EXECUTION_REVIEW_V1`
- phase: C
- run_id: `20260602_182402`
- 审查脚本: `scripts/lp_base_10u_probe_executor_v2.py` (992 lines)
- 审查方式: 全文 grep + 函数级人工 review；不执行任何 send 路径。

## 审查矩阵

| # | 检查项 | grep / 检查 | 命中行 | 结果 |
|---|---|---|---|---|
| 1 | 私钥读取 | `grep -nE "private_key\|PrivateKey\|Account\.from_key\|LocalAccount"` | 仅 docstring l.34 + l.855 ("does not load any private key") | **PASS** (无真实读取) |
| 2 | 助记词读取 | `grep -nE "mnemonic\|seed_phrase\|from_mnemonic\|from_seed"` | 仅 docstring l.34, l.855 | **PASS** |
| 3 | keystore 读取 | `grep -nE "keystore\|load_keyfile\|KeyStore"` | 仅 docstring l.34, l.855 | **PASS** |
| 4 | signer 创建 | `grep -nE "signer\|Signer\b\|create_signer"` | 仅 `no_signer_constructed` 旗 l.815, docstring l.35 | **PASS** |
| 5 | wallet client 创建 | `grep -nE "Web3\|HTTPProvider\|wallet_client"` | 仅 docstring 与 `no_wallet_client_constructed` l.816 | **PASS** |
| 6 | eth_sendTransaction 调用 | `grep -n "eth_sendTransaction\|send_transaction"` | 仅 docstring l.36 ("forbidden") | **PASS** |
| 7 | eth_sendRawTransaction 调用 | `grep -n "eth_sendRawTransaction\|sendRawTransaction"` | 仅 docstring l.36 | **PASS** |
| 8 | approve 真实发送路径 | `build_approve_exact_usdc_tx` 等只返 dict，无 transact/send | l.399-471 | **PASS** |
| 9 | mint 真实发送路径 | `build_mint_position_tx` 只返 dict，无 transact/send | l.476-521 | **PASS** |
| 10 | decrease 真实发送路径 | `build_decrease_liquidity_tx` 只返 dict | l.548-575 | **PASS** |
| 11 | collect 真实发送路径 | `build_collect_tx` 只返 dict | l.578-599 | **PASS** |
| 12 | burn 真实发送路径 | grep `burn(` 无命中 | n/a | **PASS** |
| 13 | swap 真实发送路径 | grep `swap(` 无命中 | n/a | **PASS** |
| 14 | send hard-disable 包裹 | `execute-guarded` 分支强制 raise `ExecutionSendDisabledInImplementationBuildStage` | l.964-980 | **PASS** |
| 15 | execute-guarded 默认拒绝 | argparse 强制 `choices`；任何 `--mode execute-guarded` 调用都进入第 974 行 raise；`except` 在 `__main__` 中捕获并 `sys.exit(1)` | l.834-835 + l.987-992 | **PASS** |
| 16 | `no_send` / `dry_run_only` 默认 true | `add_argument("--dry-run-only", action="store_true", default=True)` l.842；同样 `--no-send` l.843 | l.842-843 | **PASS** |
| 17 | 自动重试 / 自动执行 | `rpc_call` 重试只对 `eth_call` / `eth_chainId`（读取调用），无写入操作；无 cron 或后台循环 | l.155-173 | **PASS** |
| 18 | live/canary/paper 路径 | grep `live\|canary\|paper` 仅 docstring 提及禁区 | l.38 | **PASS** |
| 19 | 长循环 / monitor 后台 | `monitor_position_loop_stub` iterations>1 ValueError | l.532-535 | **PASS** |
| 20 | 危险 env var 自检 | `is_forbidden_env` + main loop 阻挡 PRIVATE_KEY/MNEMONIC/.../DATABASE_URL 等 15 个模式 | l.93-109, l.852-856 | **PASS** |

## 仅读取的 RPC 方法

| 方法 | 用途 | 行 |
|---|---|---|
| `eth_call` (slot0) | 读取 current_tick 与 sqrtPriceX96 | l.339 |
| `eth_chainId` | preflight 验证链 id | l.736, l.885 |

**未**调用任何写入类 RPC 方法（如 `eth_sendRawTransaction` / `eth_sign` / `eth_signTransaction` / `personal_sign`）。

## 模式矩阵

| mode | 行为 | send 可能? |
|---|---|---|
| `preflight` | read-only chain id + slot0；写 telemetry | **不可能** |
| `print-unsigned` | 构造 approve+mint dict，写 telemetry | **不可能**（无签名/广播） |
| `validate-approval` | 解析审批短语，写 telemetry | **不可能** |
| `implementation-self-check` | 上述三步组合 + execute-guarded 模拟 | **不可能** |
| `execute-guarded` | 进入分支立即 raise + exit(1) | **不可能**（hard disabled） |

## 三重门禁源代码定位

| 门禁 | 实现位置 | bypass 可能性 |
|---|---|---|
| Gate 1: 显式 mode | argparse `choices=[...]` l.834 | 不可绕过 |
| Gate 2: phrase exact match | `parse_approval_phrase` l.285 + regex l.77 + 危险词检查 l.81-90 | 不可绕过 |
| Gate 3: `--i-understand-this-sends-real-transactions` | argparse l.844, 解析后传入 `execution_approval_gate` | 不可绕过 |

## 风险评分

| 维度 | 风险 | 缓解 |
|---|---|---|
| 错误地触发 send | **零** — execute-guarded 永远 raise + 主程序 catch 后 exit(1)，未来 stage 必须在 `__main__` 之外额外解封 | 不需要 |
| 私钥泄漏 | **零** — 未读任何私钥 env | env-pattern 自检兜底 |
| 长循环挂起 | **零** — monitor iterations>1 ValueError；rpc_call 最多 5 次 backoff | 不需要 |
| 网络副作用 | **read-only RPC** — 仅 eth_call/eth_chainId | 不需要 |
| 误用 v1 | v1 文件保持不变，v2 是新文件 | 不需要 |

## verdict

| field | value |
|---|---|
| any_real_send_path_triggerable | false |
| send_hard_disabled | true |
| dry_run_only_default | true |
| no_send_default | true |
| any_dangerous_grep_hit_in_executable_code | false |
| any_signer_constructed | false |
| any_wallet_client_constructed | false |
| static_security_pass | true |

## 安全（本阶段不变量）

```text
wallet_or_tx_touched = false
can_run_probe_now    = false
tiny_canary_allowed  = no
```
