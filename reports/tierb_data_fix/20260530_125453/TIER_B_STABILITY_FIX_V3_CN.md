# Tier B Stability Fix V3

- targeted_pool_count: 16
- stability_fix_success_count: 11
- status_counts: {'partial': 7, 'missing': 5, 'risk_high': 2, 'ok': 2}

本轮补到了更多 `price_move_5m/15m/30m` 和 `volume_change_1h`，但 `tvl_change_1h` 仍然只有 `snapshot_only` 或缺失。
因此稳定性最多只能到 `partial`，还不能支撑 `RESEARCH_CANDIDATE`。
