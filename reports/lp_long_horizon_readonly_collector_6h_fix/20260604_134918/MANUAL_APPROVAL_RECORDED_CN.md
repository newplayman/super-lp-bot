# Stage C — 6h 审批短语校验 + MANUAL APPROVAL RECORDED

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_REAL_WALLCLOCKFIX_REPEAT_V1`
- run_id: `20260604_134918`

## 0. 校验结果

**MATCH** — 审批短语**完全匹配**任务规范要求的字符串, 6h 阶段 manual approval
**已记录** (本任务使用).

## 1. 提交短语 (本任务 stage=6h)

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
```

✅ Phrase **完全匹配**.

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
| `timestamp_utc` | `2026-06-04T13:49:18Z` (本任务执行时间) |
| `approved_by` | `manual operator (this conversation)` |
| `reason` | `per LP_LONG_HORIZON_READONLY_COLLECTOR_6H_REAL_WALLCLOCKFIX_REPEAT_V1 task spec; only 6h stage approved (real wallclock); 12h/24h/48h/72h/7d all NOT approved` |

## 5. 与上一轮 6H_RUN_APPROVAL_V1 approval 关系

| 维度 | 上一轮 (130353) | 本任务 (134918) |
|---|---|---|
| 短语 | APPROVE 6h | APPROVE 6h (同一短语) |
| sha256 | 1dd950db... | 1dd950db... (相同, 因 phrase 相同) |
| approved_next_stages | `[]` | `[]` (同样) |
| 区别 | 上一轮 short mode 跑 → WARN | 本任务要求 real 6h wallclock |

**重要**: 上一轮短模式跑未满足 6h gate (`actual_runtime_minutes=2.75 < 330`),
本任务用**同一 approval 短语** 重新走 real 6h wallclock. 不构成"forward approval"
(因同一 stage, 同一短语, 只是重新跑).

## 6. 严禁 forward / batch / cascade

```python
def is_forward_or_batch_approval(phrase: str) -> bool:
    banned = ["all stages", "through 7d", "and subsequent", "cascade", "batch"]
    return any(b in phrase.lower() for b in banned)
```

本任务 phrase 不含任何 banned token, ✅ pass.

12h / 24h / 48h / 72h / 7d **未**隐式 forward approved. 必须每个 stage 重新
走 `<STAGE>_RUN_APPROVAL_V1` 阶段.

## 7. 结论

6h approval 短语**完全匹配**, 6h 阶段 manual approval 已记录 (本任务).
仅 6h 阶段被批准. 12h/24h/48h/72h/7d 全部**未**隐式 forward approved.
`auto_advance_allowed=false` 保持 locked. Stage C 通过.
进入 Stage D (真实 6h run 配置冻结).
