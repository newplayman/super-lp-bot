# 静态安全审查

- stage: `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_REVIEW_V1`
- phase: C
- run_id: `20260602_144843`
- 审查脚本: `scripts/lp_base_10u_probe_executor_v1.py` (845 行, 31493 字节)

## 1. 文件元数据

| 字段 | 值 |
|---|---|
| 路径 | `scripts/lp_base_10u_probe_executor_v1.py` |
| 行数 | 845 |
| 字节 | 31493 |

## 2. 11 项检查

| # | 检查 | search terms | matches | 结果 | 理由 |
|---|---|---|---|---|---|
| 1 | private_key 加载 | `Account.from_key` `LocalAccount` `load_keyfile` `load_keystore` `from_key` `from_mnemonic` `from_seed` `PrivateKey` `privateKey` `Web3` `Web3Provider` | **0** | **PASS** | 无 signer / wallet client 构造 |
| 2 | eth_sendTransaction | `.send_transaction(` `.sendRawTransaction(` `.sendTransaction(` `w3.eth.send` `web3.eth.send` | **0** | **PASS** | 无任何 tx-send 模式 |
| 3 | approve/mint/decreaseLiquidity/collect 执行 | `.transact(` `.build_transaction(` `contract.functions.approve/mint/decreaseLiquidity/collect` | **0** | **PASS** | 无 `.transact()` 或 `.build_transaction()` |
| 4 | private_key env lookup | `os.environ["PRIVATE_KEY"]` / `["MNEMONIC"]` / `["SEED_PHRASE"]` / `["KEYSTORE"]` | **0** | **PASS** | 无直接 `os.environ` 读敏感 key |
| 5 | default mode 是 preflight | (argparse required=True) | n/a | **PASS** | `--mode` 是 required；safe mode 必须显式选择 |
| 6 | `--mode execute` 被拒绝 | argparse choices 不含 `execute` | 0 | **PASS** | choices = `["preflight", "print-unsigned", "validate-approval", "execute-disabled"]`；外加 defense-in-depth：`if args.execute or args.mode == "execute": exit 3` |
| 7 | execution stubs disabled | grep `raise ExecutionDisabledInBuildStage` | 7 | **PASS** | 7 个 stub 全部 raise |
| 8 | forbidden env-var patterns 已列 | `FORBIDDEN_ENV_PATTERNS` | 15 | **PASS** | 15 个 crypto / wallet / secret-store regex；main() 启动时扫 env 匹配则 exit 4 |
| 9 | dangerous word patterns 已列 | `DANGEROUS_WORD_PATTERNS` | 27 | **PASS** | 27 个 whole-word regex；parse_approval_phrase 用 re.search 命中即 reject |
| 10 | 无 hidden auto-run | `__main__` 块结构 | n/a | **PASS** | 无 cron / nohup / background Popen；`__main__` 调 main() with explicit args |
| 11 | 无 subprocess 调用 | `subprocess` / `os.system` / `os.popen` | 0 | **PASS** | 仅用 `urllib.request` 做 RPC；`json` 做序列化 |

## 3. argparse choices 审计

```python
p.add_argument("--mode", required=True,
               choices=["preflight", "print-unsigned", "validate-approval", "execute-disabled"],
               help="Mode of operation. 'execute' is REJECTED (use 'execute-disabled' to see the disabled stub).")
```

`--mode execute` **不在** choices 内，argparse 直接拒绝（exit 2）。

## 4. defense-in-depth

main() 函数开头有：

```python
# Defense in depth: if --execute is present OR --mode == execute, abort
if args.execute or args.mode == "execute":
    sys.stderr.write("REJECTED: --mode execute is not allowed in this build stage.\n")
    return 3
```

这是**第二道**防线，即使 argparse 误配也兜底。

## 5. execution stub 全部 disabled

| # | 函数 | 抛出信息 |
|---|---|---|
| 1 | `approve_exact_usdc()` | `EXECUTION_DISABLED_IN_BUILD_STAGE: ...` |
| 2 | `approve_exact_weth()` | `EXECUTION_DISABLED_IN_BUILD_STAGE: ...` |
| 3 | `mint_position()` | `EXECUTION_DISABLED_IN_BUILD_STAGE: ...` |
| 4 | `monitor_position()` | `EXECUTION_DISABLED_IN_BUILD_STAGE: ...` |
| 5 | `decrease_liquidity()` | `EXECUTION_DISABLED_IN_BUILD_STAGE: ...` |
| 6 | `collect_fees()` | `EXECUTION_DISABLED_IN_BUILD_STAGE: ...` |
| 7 | `revoke_allowance()` | `EXECUTION_DISABLED_IN_BUILD_STAGE: ...` |

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
