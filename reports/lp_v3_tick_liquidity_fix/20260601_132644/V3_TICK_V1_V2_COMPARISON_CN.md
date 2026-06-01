# V3 Tick V1 vs V2 Comparison

- `selected_pool_count` v1=`6` v2=`5` direction=`changed`
- `snapshot_success_pool_count` v1=`1` v2=`5` direction=`improved`
- `snapshot_fail_pool_count` v1=`5` v2=`0` direction=`improved`
- `high_confidence_count` v1=`1` v2=`5` direction=`improved`
- `medium_confidence_count` v1=`0` v2=`0` direction=`same_or_worse`
- `invalid_count` v1=`0` v2=`0` direction=`same_or_worse`

- `pool_state_read_failed` 主因已被收敛为 unsupported 192-byte slot0 slipstream 变体。
- v2 主要修复的是候选池选择与 prevalidation，不是对 slipstream 直接解码。
