# 输入证据审计

- stage: `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_V1`
- phase: B
- run_id: `20260602_135824`
- 上一阶段: `LP_BASE_10_20U_PROBE_EXECUTION_SPEC_REVIEW_V1` (20260602_133221)

## 1. 上游门禁校验

| 门禁 | 期望 | 实际 | 通过 |
|---|---|---|---|
| 上一阶段 status | PASS | PASS | ✓ |
| execution_script_allowed_next | true | true | ✓ |
| can_run_probe_now | false | false | ✓ |
| approval_phrase_effective_this_round | false | false | ✓ |
| recommended_next_stage | LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_V1 | LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_V1 | ✓ |
| executor_built_this_round_upstream | false | false | ✓ |
| executor_will_run_this_round_upstream | false | false | ✓ |
| edge_proven | no | no | ✓ |
| tiny_canary_allowed | no | no | ✓ |
| actual_fee_ready | false | false | ✓ |
| token_id_available | false | false | ✓ |
| fabrication_blocked | true | true | ✓ |

## 2. 继承的关键事实

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
| notional_first | 10 USD |
| notional_max | 20 USD |
| hold_initial | 15m |
| hold_max_extension | 30m |
| tick_lower | -200643 |
| tick_upper | -200243 |
| tick_tier | medium |
| current_tick_at_freeze | -200443 |
| weth_usd_anchor | $1,973.88 |

## 3. 上游已读 artifacts (8 大类)

| 类别 | 路径 | 关键事实 |
|---|---|---|
| spec FINAL_VERDICT | `reports/lp_base_probe_execution_spec_review/20260602_133221/FINAL_VERDICT.json` | status=PASS; execution_script_allowed_next=true |
| spec candidate freeze | `.../base_probe_execution_candidate_freeze.json` | frozen=true; authorized_this_round=false |
| spec runbook | `.../base_probe_execution_runbook.json` | 6 steps (sanity / approve / mint / hold / exit / cleanup) |
| spec stop conditions | `.../base_probe_stop_conditions.json` | 22 stops; no_auto_retry=true |
| spec telemetry | `.../base_probe_actual_telemetry_spec.json` | 6 schemas; no production tables |
| spec script boundary | `.../base_probe_execution_script_boundary.json` | 7 allowed + 11 forbidden |
| spec approval template | `.../base_probe_execution_approval_template.json` | regex 校验未来执行短语 |
| spec risk acceptance | `.../base_probe_risk_acceptance.json` | EV 负；不是盈利策略 |
| + CN 文档 6 项 | `.../BASE_PROBE_*.md` | human-readable 配套 |

## 4. 本轮范围

```text
build_base_10u_probe_executor_skeleton_only
```

### 允许

- 创建 `scripts/lp_base_10u_probe_executor_v1.py` skeleton
- 实现 `--mode preflight`（read-only eth_call + balanceOf + allowance + slot0 + QuoterV2 + estimateGas + stop condition checks）
- 实现 `--mode print-unsigned`（structured JSON；no signing, no send）
- 实现 `--mode validate-approval`（regex parser；成功**不**授权执行）
- 实现 `--mode execute-disabled`（stub aborts with EXECUTION_DISABLED_IN_BUILD_STAGE）
- abort `--mode execute` with clear error
- 读取公开链上状态（eth_call、eth_getBalance、balanceOf、allowance、slot0）
- 调用 eth_estimateGas（不签名不发送）
- 构造 structured unsigned tx JSON
- 写 telemetry 到本地 reports/ 目录（no production tables）
- 运行 read-only self-check preflight

### 禁止

- 加载私钥 / 助记词 / keystore
- 创建 signer / wallet client
- 发送 `eth_sendTransaction` / `eth_sendRawTransaction`
- 执行 approve / mint / increaseLiquidity / decreaseLiquidity / collect / burn / swap
- 启动 lpbot-live / lpbot-canary / lpbot-paper
- 自动 bridge / swap
- 翻转 `can_run_probe_now` / `tiny_canary_allowed` / `edge_proven`
- 即使审批短语匹配 regex 也不执行
- 实现真正的 `--mode execute` 逻辑（must remain disabled stub）
- 写 production lpbot 表
- 改任何策略执行路径

## 5. 通过

```text
all 8 upstream artifact categories read = yes
all upstream gates aligned                 = yes
previous status = PASS                     = yes
proceed_to_phase_C                         = true
```
