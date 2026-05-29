# TIER_C_NEXT_STAGE_POLICY

- 当前 batch 不再做 12h recheck。
- 当前 batch 不进入 OOS。
- 当前 batch 不进入 micro candidate review。
- 下一步只允许 `TIER_C_REDISCOVERY_AFTER_MARKET_CHANGE` 或 `TIER_C_STOP_RESEARCH`。
- 未来重新 discovery 前必须先应用 `TIER_C_HARD_REJECTION_POLICY_V1_CN.md`。
- tiny_canary_allowed: no