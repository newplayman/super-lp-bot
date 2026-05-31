# Fee Exit Data Readiness

| feature | coverage | source | entry_safe | notes |
|---|---:|---|---|---|
| fee_velocity_proxy | 97.58% | shadow_position_marks + pools | yes | previous closed bucket |
| exit_depth_10usd | 97.58% | shadow_position_marks + pools proxy | yes | proxy only |
| exit_depth_20usd | 97.58% | shadow_position_marks + pools proxy | yes | proxy only |
| exit_depth_50usd | 97.58% | shadow_position_marks + pools proxy | yes | proxy only |
| slippage_10usd/20usd/50usd | 97.58% | proxy model | yes | no route API |
| price_move_15m/30m/1h | 96.78% | shadow_position_marks | yes | mark-based |
| tvl_change_1h | 96.78% | shadow_position_marks | yes | mark-based |
| volume_change_1h | 96.78% | shadow_position_marks | yes | mark-based |
| data freshness / pool mark gap | 97.58% | shadow_position_marks | yes | gap from feature cutoff |
