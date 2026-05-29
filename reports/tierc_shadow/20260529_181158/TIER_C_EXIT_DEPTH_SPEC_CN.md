# Tier C Exit Depth Research Spec

- `exit_depth_usd`: at target horizon, estimated executable size before slippage breaches threshold.
- `exit_slippage_10usd`: estimated exit slippage for 10 USD probe.
- `exit_slippage_20usd`: estimated exit slippage for 20 USD probe.
- `exit_slippage_50usd`: estimated exit slippage for 50 USD probe.
- `route_available`: whether a research-only swap route exists from token to major quote.
- `token_to_major_depth`: route depth from token to major asset.
- `max_safe_position_usd`: max size that keeps exit slippage under research threshold.
- `exit_depth_status`: `OK` / `THIN` / `ROUTE_MISSING` / `SLIPPAGE_TOO_HIGH` / `UNKNOWN`.

约束：只做 research estimate，不构造 swap，不调用交易路径，不写生产 order。
