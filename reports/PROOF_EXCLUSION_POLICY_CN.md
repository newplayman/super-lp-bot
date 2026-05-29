# Proof Exclusion Policy

## Permanent Proof-Layer Exclusions
- `entry_untrusted`
- `historical lineage gap`
- `missing intended_notional_usd`
- `terminal_value_zero_bug`
- `pool_mark_only`
- `only_pre_target_mark`
- `net_pnl_pct not calculable`
- `entry_value_source untrusted`

## Known Contaminated Objects
- `shadow-pos-b56917c6282e10d8858782aa`
- `shadow-canary-live-pos-36bbaf9a2860d133daa0e42a`
- `shadow-canary-live-pos-299da787e60301c7c2c61c0f`

## Scope Note
- 这是 proof 层排除，不是策略过滤。
- 不改变交易逻辑，不改变打分，不改变线上执行路径。
- 仅用于研究口径、证据口径、候选 proof surface 口径。
