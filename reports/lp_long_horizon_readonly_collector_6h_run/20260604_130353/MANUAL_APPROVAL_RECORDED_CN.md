# Stage C — 6h 审批短语校验 + MANUAL APPROVAL RECORDED

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_APPROVAL_V1`
- run_id: `20260604_130353`

## 0. 校验结果

**MATCH** — 审批短语**完全匹配**任务规范要求的字符串, 6h 阶段 manual approval
**已记录**.

## 1. 提交短语 (用户原文)

```
APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=6h mode=readonly no_probe=true
```

## 2. 期望短语 (per stage_approval_templates.json 6h 模板)

```
APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=6h mode=readonly no_probe=true
```

注: 任务规范使用 `mode=readonly` (英文) 与上一阶段 staged_request 模板一致.

## 3. 校验逻辑

```python
def is_valid_approval(phrase: str, stage: str) -> bool:
    expected = f"APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage={stage} mode=readonly no_probe=true"
    return phrase.strip() == expected

assert is_valid_approval("APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=6h mode=readonly no_probe=true", "6h") is True
```

✅ Phrase **完全匹配** (含尾部空格 / 换行 trim).

## 4. 校验记录 (本任务)

| 字段 | 值 |
|---|---|
| `approved_stage` | `6h` |
| `mode` | `readonly` |
| `no_probe` | `true` |
| `approval_recorded` | `true` |
| `approved_next_stages` | `[]` (空 list, 严禁隐式 forward 批准) |
| `auto_advance_allowed` | `false` (locked) |
| `user_approval_text` | `APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=6h mode=readonly no_probe=true` |
| `user_approval_text_hash` (sha256) | `1dd950db67e3bad450d4d319c3c5e8ec3a57eb1cdb6d75027cdab307f4681b3e` |
| `timestamp_utc` | `2026-06-04T13:0X:XXZ` (本任务执行时间) |
| `approved_by` | `manual operator (this conversation)` |
| `reason` | `per LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_APPROVAL_V1 task spec` |
| `preconditions_verified` | (见 MANUAL_APPROVAL_RECORDED.json) |

## 5. 重要: 严禁 forward 批准

`approved_next_stages = []`. 任务规范明确说"只能批准 6h, 不得批准 12h 或 7d".

如果用户在后续阶段重复发送 12h / 24h 等 phrase, **必须**走**新**的
`<STAGE>_RUN_APPROVAL_V1` 阶段, 重新 read-back 6h FINAL_VERDICT + audit + manual decision.

**禁止**将本 6h approval 解释为 "approving through 7d" / "approving all stages" / "approving 6h and subsequent".

## 6. 多阶段互斥检查 (per stage_approval_templates.exclusivity)

```python
def is_forward_or_batch_approval(phrase: str) -> bool:
    # 任何 phrase 包含 "all stages" / "through 7d" / "and subsequent" → 拒绝
    banned = ["all stages", "through 7d", "and subsequent", "cascade", "batch"]
    return any(b in phrase.lower() for b in banned)
```

本任务 phrase 不含任何 banned token, ✅ pass.

## 7. 结论

6h approval 短语**完全匹配**, 6h 阶段 manual approval 已记录. 仅 6h 阶段
被批准, 12h/24h/48h/72h/7d 全部**未**隐式 forward approved. `auto_advance_allowed=false`
保持 locked. Stage C 通过. 进入 Stage D (6h run 参数冻结).
