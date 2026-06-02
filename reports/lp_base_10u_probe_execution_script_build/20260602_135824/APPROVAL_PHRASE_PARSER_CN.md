# Approval Phrase Parser Spec

- stage: `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_V1`
- phase: F
- run_id: `20260602_135824`
- script: `scripts/lp_base_10u_probe_executor_v1.py --mode validate-approval`

## 命令

```bash
python3 scripts/lp_base_10u_probe_executor_v1.py --mode validate-approval \
    --approval "APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0x<...> pool=0x<...> notional=10 hold=15m" \
    --run-id <RUN_ID>
```

## 校验正则

```text
^APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0x[0-9a-fA-F]{40} pool=0x[0-9a-fA-F]{40} notional=10 hold=15m$
```

## 5 步校验

1. **type check**: 短语必须是非空字符串
2. **dangerous-word pre-check**: 任何 DANGEROUS_WORDS 命中 → 拒绝 + 原因
3. **regex match**: 必须完全匹配 canonical template
4. **field extract**: 提取 wallet / pool / notional / hold
5. **cross-check**: 与 frozen candidate 一致
   - `wallet == 0xb05b2872ace4564ff247555b6f7b097d31f3d835`
   - `pool == 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38`
   - `notional == 10`
   - `hold == 15m`

## DANGEROUS_WORDS

```
EXECUTE / NOW / LIVE / CANARY / PAPER / MINT / SIGN / BURN
SWAP / BRIDGE / SEND / DEPLOY / EXEC / GO / SHIP / PROCEED
20U / 20u / 30M / 30m / USER_PROVIDED / USER_SELECTED / YES
EXECUTABLE / FUND / WITHDRAW / TRANSFER_OUT
```

任何含上述词**必拒**。

## 必须被拒的替代短语

```text
APPROVE_BASE_10U_LP_PROBE_EXECUTE     (前缀错)
APPROVE_BASE_10U_LP_PROBE_NOW        (NOW)
APPROVE_BASE_10U_LP_PROBE_MINT       (MINT)
APPROVE_BASE_10U_LP_PROBE_LIVE       (LIVE)
APPROVE_BASE_10U_LP_PROBE_CANARY     (CANARY)
APPROVE_BASE_20U_LP_PROBE_EXECUTION_ONE_SHOT ...  (20U)
... notional=20 hold=15m             (20U)
... notional=10 hold=30m             (30m)
... wallet=0xUSER_PROVIDED_WALLET_ADDRESS  (placeholder)
GO / SHIP_IT / PROCEED               (无前缀)
```

## 成功输出（注意：成功不授权执行）

```json
{
  "valid": true,
  "reason": null,
  "parsed": {
    "wallet": "0xb05b2872ace4564ff247555b6f7b097d31f3d835",
    "pool": "0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38",
    "notional": 10,
    "hold": "15m"
  },
  "executes_now": false,
  "authorization_granted": false,
  "next_step_even_if_valid": "user_must_reapprove_at_execution_time_after_review_stage"
}
```

## 输出位置

`reports/lp_base_10u_probe_execution_runtime/<run_id>/approval_validation.json`（local only）

## 安全

```text
wallet_or_tx_touched = false
executes_now = false  (ALWAYS)
authorization_granted = false  (ALWAYS)
```
