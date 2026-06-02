# Next Execution Command Draft

- stage: `LP_BASE_10U_PROBE_EXECUTION_AUTHORIZATION_PACKAGE_V1`
- phase: J
- run_id: `20260602_184806`
- **本阶段不运行；仅展示草案。**

## 未来命令模板

```bash
# === DO NOT RUN IN THIS STAGE ===
# 这是 LP_BASE_10U_PROBE_FIRST_EXECUTION_RUN_V1 阶段的草案命令；
# 不能在本 stage 跑；executor v2 当前 stage 中 execute-guarded 永远 raise hard-disable。

python3 scripts/lp_base_10u_probe_executor_v2.py \
  --mode execute-guarded \
  --run-id <NEW_RUN_ID_GENERATED_AT_EXECUTION_TIME> \
  --wallet 0xb05b2872ace4564ff247555b6f7b097d31f3d835 \
  --notional 10 \
  --hold 15m \
  --approval "APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0xb05b2872ace4564ff247555b6f7b097d31f3d835 pool=0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 notional=10 hold=15m" \
  --i-understand-this-sends-real-transactions
```

`NEW_RUN_ID_GENERATED_AT_EXECUTION_TIME` 必须在执行那一刻通过 `date -u +%Y%m%d_%H%M%S` 生成；不允许复用任何旧 RUN_ID。

## 本阶段不运行 — 行为预期

如果**意外** 在当前 commit (`c18176f` 或本 commit 之后但 hard-disable 未解除) 执行了该命令：

```text
expected_returncode = 1
expected_stderr     = "EXECUTION_SEND_DISABLED_IN_IMPLEMENTATION_BUILD_STAGE\n..."
expected_tx_sent    = 0
```

(本 review 已经在 Stage H runtime self-check 中独立验证过两次，都是 exit 1 / 无 tx。)

## 下一阶段（execution runner）启动前还必须

| 必须 | 说明 |
|---|---|
| **1. 检查 send hard-disable 是否仍存在** | `grep -n "raise ExecutionSendDisabledInImplementationBuildStage" scripts/lp_base_10u_probe_executor_v2.py` 必须命中 line 974。若仍命中 ⇒ executor 不会发送，再多 flag 也无用 |
| **2. 重新读取 chain 实时状态** | 重读 chain_id / slot0 / NPM code / pool code |
| **3. 重算 dynamic tick range** | 不可信赖任何 cached snapshot |
| **4. 重新生成 approval phrase 输入** | 即使是同样字符串，也必须每次手动 re-type，确保操作员主观确认 |
| **5. 实时 USDC.allowance 检查** | 不足才 ApproveExact；足够则 skip |
| **6. 实时 gas / balance 检查** | gas 估算 < 600_000；balance USDC ≥ 10_000_000；wallet ETH ≥ 0.001 |
| **7. 操作员对 risk acceptance packet 八项确认** | 见 Stage I 八条 |

## hard-disable 解除流程（仅供未来参考；本阶段不解除）

任何 unblocking commit 必须：

1. **单独 commit**，专门处理 hard-disable 解除，**不**与其它代码改动混杂
2. commit message 包含 `unseal:` 前缀 + 详细 rationale
3. PR / commit 由第二名 reviewer (or 第二个 audit pipeline) 显式审批
4. 解除后的 executor 必须重新通过 implementation 与 final review 两个阶段
5. 解除 commit 必须附带新的 `EXECUTION_HARD_DISABLE_RELEASE_AUDIT.md` 文档

**当前 commit `c18176f` 与 本 stage 任何 commit 都不解除 hard-disable**。

## 本阶段不运行 — 强制确认

```text
this_stage_does_not_run_executor = true
this_stage_does_not_call_executor_subprocess = true
this_stage_does_not_construct_signer = true
this_stage_does_not_send_tx = true
```

## 草案 dry-run（仅展示，本阶段不实际执行）

如果未来想先做 dry-run preflight（仍是 read-only），可以用：

```bash
# safe read-only preflight (does not send tx; ok in any stage)
python3 scripts/lp_base_10u_probe_executor_v2.py \
  --mode preflight \
  --run-id <NEW_RUN_ID> \
  --wallet 0xb05b2872ace4564ff247555b6f7b097d31f3d835 \
  --notional 10 \
  --hold 15m \
  --dry-run-only \
  --no-send
```

此命令在所有阶段都是 read-only 的（仅 `eth_chainId` + `eth_call slot0`），但 **本 stage 也不主动执行它** — 上轮 review 阶段已经独立跑过；本 stage 仅生成文档。

## 安全（本阶段不变量）

```text
wallet_or_tx_touched          = false
this_stage_did_not_execute    = true
can_run_probe_now             = false
execution_allowed_now         = false
hard_disable_still_active     = true
```
