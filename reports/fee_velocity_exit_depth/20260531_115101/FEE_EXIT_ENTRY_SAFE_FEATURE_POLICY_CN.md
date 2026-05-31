# Entry-Safe Fee / Exit-Depth Feature Policy

- `sample_start_time`: counterfactual 入场时刻。
- `feature_cutoff_time`: previous fully closed 15m bucket end，且必须 `<= sample_start_time`。
- same-bucket 和 post-entry 特征全部禁用。

允许特征：
- previous bucket fee_proxy
- previous bucket fee_velocity_proxy
- previous bucket volume proxy
- previous bucket exit_depth_10usd / 20usd / 50usd
- previous bucket slippage_10usd / 20usd / 50usd
- previous bucket price_move_5m / 15m / 30m / 1h
- previous bucket tvl_change_1h
- previous bucket data freshness
- previous bucket pool mark gap

禁止特征：
- same bucket bucket_end after sample_start
- post-entry price/volume/tvl marks
- route execution path
- signed quotes / swap tx
