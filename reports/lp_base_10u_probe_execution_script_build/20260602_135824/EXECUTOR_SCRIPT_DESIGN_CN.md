# Base 10U Probe Executor 脚本设计

- stage: `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_V1`
- phase: C
- run_id: `20260602_135824`
- script: `scripts/lp_base_10u_probe_executor_v1.py`

> ⚠️ **本阶段只构建 executor 脚本 skeleton。脚本默认不可执行；本轮不执行任何 probe。**

## 1. 支持的 4 种 mode

| mode | 用途 | 允许 | 禁止 | 退出码 |
|---|---|---|---|---|
| `preflight` | 只读链上状态检查 | eth_chainId, eth_getBalance, ERC20.balanceOf, ERC20.allowance, pool.slot0, pool.liquidity, QuoterV2 (best-effort), eth_estimateGas | signing, sending, approve, mint, collect, swap | 0 |
| `print-unsigned` | 输出结构化 unsigned tx JSON | 描述 approve / mint / decrease / collect / revoke calls；包含 candidate freeze + tick range + amount + deadline placeholder | signing, sending, 编码 r/s/v | 0 |
| `validate-approval` | 解析 + 验证未来执行审批短语 | regex 匹配；提取 wallet / pool / notional / hold 字段 | 存为授权；自动执行 | 0 |
| `execute-disabled` | stub；永远 abort | 输出 `EXECUTION_DISABLED_IN_BUILD_STAGE` | 任何执行 | 1 |

## 2. 被拒绝的 mode

| mode | 行为 |
|---|---|
| `execute` | **REJECTED**，exit_code=3，stderr 输出 "REJECTED: --mode execute is not allowed in this build stage." |
| `--execute` 标志 | **REJECTED**，exit_code=3 |

## 3. Hard-coded candidate freeze

| 字段 | 值 |
|---|---|
| chain | base (chain_id 8453) |
| pool | `0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38` |
| pair | WETH/USDC |
| fee_tier | 100 (0.01%) |
| tick_spacing | 1 |
| protocol | Uniswap V3 (Base) |
| npm | `0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1` |
| quoter_v2 | `0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a` |
| weth (Base canonical) | `0x4200000000000000000000000000000000000006` |
| usdc (Base canonical) | `0x833589fcd6edb6e08f4c7c32d4f71b54bda02913` |
| wallet | `0xb05b2872ace4564ff247555b6f7b097d31f3d835` |
| notional | 10 USD |
| hold | 15m |
| tick range | lower=-200643, upper=-200243 |

## 4. Approval phrase 校验

```text
^APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0x[0-9a-fA-F]{40} pool=0x[0-9a-fA-F]{40} notional=10 hold=15m$
```

任何含 **DANGEROUS_WORDS**（EXECUTE / NOW / LIVE / CANARY / PAPER / MINT / SIGN / BURN / SWAP / BRIDGE / SEND / DEPLOY / EXEC / GO / SHIP / PROCEED / 20U / 30M / USER_PROVIDED / USER_SELECTED / YES / EXECUTABLE / FUND / WITHDRAW / TRANSFER_OUT）的短语**必拒**。

**validate-approval 成功也不授权执行**；`executes_now: false`, `authorization_granted: false`。

## 5. 禁止的 env var patterns

```text
PRIVATE_KEY / MNEMONIC / SEED_PHRASE / KEYSTORE / *_PRIVATE_KEY / *_MNEMONIC
/ *_SEED / *_SECRET / *_PASSWORD / *_API_KEY / *_TOKEN
/ DATABASE_URL / POSTGRES_DSN / *DATABASE_URL / *DSN
```

任何匹配这些 pattern 的 env var 一旦存在，脚本**直接拒绝运行**（exit_code=4），stderr 输出 "REFUSING TO RUN: forbidden env var present: ..."。

## 6. Execution stubs（全部 disabled）

```python
class ExecutionDisabledInBuildStage(RuntimeError): pass

def approve_exact_usdc() -> None: raise ExecutionDisabledInBuildStage(...)
def approve_exact_weth() -> None: raise ExecutionDisabledInBuildStage(...)
def mint_position() -> None:      raise ExecutionDisabledInBuildStage(...)
def monitor_position() -> None:   raise ExecutionDisabledInBuildStage(...)
def decrease_liquidity() -> None: raise ExecutionDisabledInBuildStage(...)
def collect_fees() -> None:       raise ExecutionDisabledInBuildStage(...)
def revoke_allowance() -> None:   raise ExecutionDisabledInBuildStage(...)
```

任何 stub 调用 = `RuntimeError("EXECUTION_DISABLED_IN_BUILD_STAGE: ...")`

## 7. Telemetry skeleton artifacts

写到 `reports/lp_base_10u_probe_execution_runtime/<run_id>/`：

```text
entry_intent.json
preflight_checks.json
stop_condition_checks.json
unsigned_package.json
approval_validation.json
```

**不**写 production 表（`lp_probe_execution_ledger_v1` 等 schema 是设计稿；写 production 表是未来独立 stage 的事）。

## 8. 安全

```text
wallet_or_tx_touched    = false
can_run_probe_now       = false
tiny_canary_allowed     = no
edge_proven             = no
executor_built_this_round = true
executor_will_run_this_round = false
```
