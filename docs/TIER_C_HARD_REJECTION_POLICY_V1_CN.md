# TIER_C_HARD_REJECTION_POLICY_V1

- `top10_holder_pct > 40% => REJECT_LOCKED`
- `top10_holder_pct > 25% => 不允许 MICRO`
- `top1_trader_volume_share > 90% => 不允许 MICRO`
- `top5_trader_volume_share > 95% => 不允许 MICRO`
- `holder_concentration_extreme => 不做 6h/12h recheck，直接等待新 discovery`
- `REJECT_LOCKED 不进入 OOS`
- `WATCH_NO_SWAP_LOGS 可在 6–12h 后重查`
- `WATCH_UNSUPPORTED_POOL 只有新增 parser 后重查`
- `WATCH_DATA_MISSING 只有关键字段自然补齐后重查`

- tiny_canary_allowed: no