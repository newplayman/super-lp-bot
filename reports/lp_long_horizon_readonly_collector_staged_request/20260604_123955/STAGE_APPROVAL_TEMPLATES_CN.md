# Stage E — Stage Approval Templates (审批短语模板)

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_STAGED_RUN_REQUEST_V1`
- run_id: `20260604_123955`

## 0. 目的

定义 6 阶段 (6h/12h/24h/48h/72h/7d) 的 manual approval 短语模板.
**本轮不记录任何 approval 为 true**; 仅生成模板.

每个模板包含:
1. 唯一的 approval phrase (string 匹配)
2. 必须填写的 approval record 字段
3. 锁定项 + 验证项 (验证审批是否合规)

## 1. 6 阶段 APPROVE phrase 模板

### 1.1 6h

```
APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=6h mode=readonly no_probe=true
```

完整 approval record (6H_RUN_APPROVAL_V1 阶段实装):
```yaml
approval_record:
  phrase: APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN
  stage: 6h
  mode: readonly
  no_probe: true
  approved_at: <ISO 8601 UTC>
  approved_by: <manual operator name or initials>
  reason: <1-2 句话说明为何批准>
  preconditions_verified:
    - 5-stage prev final_verdict: PASS / WARN_ACCEPTABLE
    - all 13 core gate checks: PASS / WARN_ACCEPTABLE
    - no production write observed
    - no wallet / tx / signer touched
    - no daemon leak
  risk_acknowledged: |
    manual operator acknowledges 6h run is read-only,
    no probe / canary / live / paper, no probe enables
    even if data quality is high. Any decision to enable
    probe / canary requires separate PAUSE_LP_RESEARCH
    and reopen LP_RESEARCH_FINAL_FREEZE_AND_HANDOFF.
```

### 1.2 12h

```
APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=12h mode=readonly no_probe=true
```

approval record 同 6h, 字段:
- `stage: 12h`
- `preconditions_verified`: 包含"6h 跑成功 + manual audit + 6h 跑出来的 data_quality PASS"

### 1.3 24h

```
APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=24h mode=readonly no_probe=true
```

approval record:
- `stage: 24h`
- `preconditions_verified`: 包含"12h 跑成功 + manual audit + 12h data_quality PASS"

### 1.4 48h

```
APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=48h mode=readonly no_probe=true
```

approval record:
- `stage: 48h`
- `preconditions_verified`: 包含"24h 跑成功 + manual audit + 24h data_quality PASS"

### 1.5 72h

```
APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=72h mode=readonly no_probe=true
```

approval record:
- `stage: 72h`
- `preconditions_verified`: 包含"48h 跑成功 + manual audit + 48h data_quality PASS + 72h 期间 paid RPC 配额已实装"

### 1.6 7d

```
APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=7d mode=readonly no_probe=true
```

approval record:
- `stage: 7d`
- `preconditions_verified`: 包含"72h 跑成功 + manual audit + 72h data_quality PASS + 7d 期间 paid RPC 配额充足 + disk archive 计划已 review"

## 2. 拒绝短语模板 (用于 audit 拒绝)

```
REJECT_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=<STAGE> reason=<SHORT_REASON>
```

例:
```
REJECT_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=6h reason=disk_usage_exceeded
REJECT_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=12h reason=error_rate_above_20pct
REJECT_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=24h reason=consecutive_429_streak_5
```

rejection record 字段:
- `phrase: REJECT_LP_LONG_HORIZON_READONLY_STAGE_RUN`
- `stage: <STAGE>`
- `reason: <SHORT_REASON>`
- `rejected_at: <ISO 8601 UTC>`
- `rejected_by: <manual operator>`
- `next_action: fix_repeat / pause / stop`

## 3. 暂停短语模板 (用于全局暂停)

```
PAUSE_LP_LONG_HORIZON_READONLY_STAGE_RUN reason=<SHORT_REASON>
```

例:
```
PAUSE_LP_LONG_HORIZON_READONLY_STAGE_RUN reason=data_quality_regression_across_3_stages
PAUSE_LP_LONG_HORIZON_READONLY_STAGE_RUN reason=external_market_shock
PAUSE_LP_LONG_HORIZON_READONLY_STAGE_RUN reason=manual_audit_required
```

pause 后, 任何 stage 都不允许 advance, 必须重启新 LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT_V1.

## 4. 审批记录文件 (per stage)

每阶段的 approval record 必须存到独立文件:
- `reports/lp_long_horizon_readonly_collector_<STAGE>_run/<run_id>/APPROVAL_RECORD.json`
- 字段: `phrase / stage / mode / no_probe / approved_at / approved_by / reason /
  preconditions_verified[] / risk_acknowledged / next_action`

文件存在 = approval 已收到. 文件不存在 = approval 未收到, 阶段**不**advance.

## 5. 审批 valid 验证 (programmatic check)

任何 STAGE_RUN_APPROVAL_V1 实装, 验证逻辑必须包含:

```python
def is_valid_approval(phrase: str, stage: str) -> bool:
    expected = f"APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage={stage} mode=readonly no_probe=true"
    return phrase.strip() == expected
```

phrase 不匹配 → 拒绝 (audit 警告).

## 6. 多次审批语义

同一 stage 可有多次 approval (e.g. 第一次失败 fix_repeat, 第二次重新批).
每次 approval 写**独立** APPROVAL_RECORD.json, 命名:
- `APPROVAL_RECORD_<RUN_ID>.json` (per attempt)

operator 可比对最新一份与历史, 避免错批.

## 7. 跨 stage 互斥

任何 stage approval 必须**显式**仅针对该 stage. 不接受:
- "approving all stages" (批量批准, 禁止)
- "approving through 7d" (一路批到 7d, 禁止)
- "approving 24h and all subsequent" (隐式 forward, 禁止)

每 stage 单独签发 phrase + 单独 APPROVAL_RECORD.json.

## 8. 审计追溯 (audit trail)

每阶段 FINAL_VERDICT.json 必须引用对应 APPROVAL_RECORD.json 路径:

```json
{
  "approval_record_path": "reports/lp_long_horizon_readonly_collector_<STAGE>_run/<run_id>/APPROVAL_RECORD.json",
  "approval_status": "approved" | "rejected" | "pending"
}
```

## 9. 本轮 status (per task spec)

- 本轮**不记录**任何 approval 为 true
- 本轮仅生成模板 (本文件)
- 实际 approval 留待 6H_RUN_APPROVAL_V1 阶段

## 10. 结论

6 阶段 APPROVE phrase 模板 + 拒绝 / 暂停 phrase 模板 + APPROVAL_RECORD.json
格式 + 验证逻辑. 本轮仅生成模板, 不实装 approval 流程. Stage E 通过.
进入 Stage F (Runtime budget).
