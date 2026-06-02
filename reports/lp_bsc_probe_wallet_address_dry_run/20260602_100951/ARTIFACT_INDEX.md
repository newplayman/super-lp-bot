# Artifact Index — `20260602_100951` (REJECTED)

Stage: `LP_BSC_10_20U_PROBE_WALLET_ADDRESS_DRY_RUN_V1`
Status: **FAIL**（Phase A 审批短语被拒绝）
recommended_next_stage: `LP_BSC_10_20U_PROBE_WALLET_ADDRESS_DRY_RUN_FIX_REPEAT`

## 报告文件（只 4 份，因为本轮没有进入链上读取阶段）

| 文件 | 用途 |
|---|---|
| `APPROVAL_PHRASE_REJECTED_CN.md` | 拒绝原因 + 字段级诊断 + 重发短语格式 |
| `approval_phrase_rejected.json` | 机器可读 rejection record |
| `FINAL_VERDICT.json` | status=FAIL，含 fail_reason 与 decision_notes |
| `ONEPAGE_CN.md` | 单页总览 |

## 未生成（因为短语在 Phase A 被拒）

```text
- INPUT_EVIDENCE_AUDIT (Phase C)
- BSC_WALLET_READONLY_BALANCE_ALLOWANCE (Phase D)
- BSC_WALLET_DRY_RUN_MARKET_REFRESH (Phase E)
- BSC_WALLET_BOUND_TOKEN_AMOUNT_RECALC (Phase F)
- BSC_WALLET_DRY_RUN_GAS_ESTIMATE (Phase G)
- BSC_WALLET_BOUND_UNSIGNED_PACKAGE (Phase H)
```

## 上游引用（仅作背景，本轮未读这些以避免暗示已进入审计阶段）

- `reports/lp_bsc_probe_dry_run_builder/20260602_094727/FINAL_VERDICT.json`（status PASS, recommended_next_stage = 本阶段）
- `reports/lp_bsc_probe_dry_run_builder/20260602_094727/bsc_probe_manual_approval_checkpoint.json`（提供 phrase_validation_regex）

## 测试

`tests/test_lp_bsc_probe_wallet_address_dry_run_v1_readonly.py` — 验证拒绝路径产生本应有的文件 + 安全字段。
