# Approval Parser Review

- stage: `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_REVIEW_V1`
- phase: G
- run_id: `20260602_144843`

## 9 个测试 case 全部通过

| # | case | valid | reason | result |
|---|---|---|---|---|
| 1 | exact canonical | true | (parsed successfully) | **PASS** |
| 2 | notional=20 | false | regex 不匹配 (notional != 10) | **PASS** |
| 3 | hold=30m | false | dangerous word `\b30m\b` | **PASS** |
| 4 | wrong wallet | false | cross-check: wallet != frozen | **PASS** |
| 5 | wrong pool | false | cross-check: pool != frozen | **PASS** |
| 6 | placeholder | false | regex 不匹配 (非 40 hex) | **PASS** |
| 7 | dangerous word EXECUTE | false | regex 不匹配 (prefix EXECUTE != EXECUTION_ONE_SHOT) | **PASS** |
| 8 | 成功短语不授权执行 | n/a | executes_now=False, authorization_granted=False | **PASS** |
| 9 | approval_phrase_effective_this_round | n/a | false | **PASS** |

## 关键观察

### Dangerous-word 检测

`DANGEROUS_WORD_PATTERNS` 用 `\b` (whole-word) 边界匹配；canonical 短语里的子串 `EXEC` (在 `EXECUTION` 中) **不**触发 false-positive。

```text
DANGEROUS_WORD_PATTERNS = [
    r"\bEXECUTE\b", r"\bEXEC\b", r"\bNOW\b", r"\bLIVE\b", r"\bCANARY\b",
    r"\bPAPER\b", r"\bMINT\b", r"\bSIGN\b", r"\bBURN\b",
    r"\bSWAP\b", r"\bBRIDGE\b", r"\bSEND\b", r"\bDEPLOY\b",
    r"\bGO\b", r"\bSHIP\b", r"\bPROCEED\b",
    r"\b20U\b", r"\b20u\b", r"\b30M\b", r"\b30m\b",
    r"\bUSER_PROVIDED\b", r"\bUSER_SELECTED\b", r"\bYES\b",
    r"\bEXECUTABLE\b", r"\bFUND\b", r"\bWITHDRAW\b",
    r"\bTRANSFER_OUT\b",
]
```

### 5 步校验（顺序：dangerous-word pre-check → regex → field extract → cross-check）

1. type check
2. dangerous-word pre-check (whole-word regex via `re.search`)
3. regex match (`^APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0x[0-9a-fA-F]{40} pool=0x[0-9a-fA-F]{40} notional=10 hold=15m$`)
4. field extract (wallet / pool / notional / hold)
5. cross-check (与 frozen candidate 比对)

### 成功输出（注意：成功不授权执行）

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

`executes_now=False`, `authorization_granted=False` 是关键。**本轮审批短语不生效**。

## 安全

```text
wallet_or_tx_touched = false
executes_now = false  (ALWAYS)
authorization_granted = false  (ALWAYS)
approval_phrase_effective_this_round = false
```
