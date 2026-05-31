# Fee Velocity Rule Fix Variants

- `retention_floor_30pct`: fee/depth 软筛，目标保留率 >= 30% | cap `10/20/50` | limitation `可能仍 fee<cost`
- `retention_floor_50pct`: 更宽松的 score 保留率 >= 50% | cap `10/20/50` | limitation `tail 可能回撤`
- `false_filter_cap_50pct`: 优先降低 false filter | cap `10/20/50` | limitation `fee proxy 无改善`
- `missed_profit_cap_30pct`: 尽量不误杀正收益样本 | cap `10/20/50` | limitation `tail 改善可能有限`
- `fee_cost_nonnegative_median`: 只保留 fee_minus_exit_cost_median 有望非负的窗口 | cap `10/20/50` | limitation `过筛风险高`
- `fee_cost_nonnegative_p10`: 更严格要求 fee_minus_exit_cost p10 近非负 | cap `10/20/50` | limitation `几乎必然过筛`
- `exit_depth_soft_10usd`: 仅要求 10 USD depth 基本可出 | cap `10` | limitation `20/50 无法继承`
- `exit_depth_soft_20usd`: 20 USD depth 可出，slippage 宽松 | cap `20` | limitation `可能成本仍为负`
- `fee_velocity_rank_top30`: fee velocity 前 30% | cap `10/20/50` | limitation `rank 不看成本`
- `fee_velocity_rank_top50`: fee velocity 前 50% | cap `10/20/50` | limitation `tail 可能接近 baseline`
- `fee_depth_balanced_score`: fee/depth/slippage/price 风险加权 | cap `10/20/50` | limitation `score threshold 需调参`
- `fee_depth_tail_guard`: 只过滤最差 depth/slippage tail | cap `10/20/50` | limitation `fee proxy 不一定改善`
- `small_cap_10usd_lenient`: 10 USD 专用宽松门槛 | cap `10` | limitation `只能说明最小仓位`
- `small_cap_20usd_lenient`: 20 USD 专用宽松门槛 | cap `20` | limitation `仍可能 fee<cost`
- `hybrid_fee_depth_plus_data_freshness`: fee/depth 主导 + freshness 软约束 | cap `10/20/50` | limitation `不处理 regime 风险`
- `hybrid_fee_depth_plus_regime_soft`: fee/depth 主导 + regime soft penalty | cap `10/20/50` | limitation `soft regime 仍可能过筛`
