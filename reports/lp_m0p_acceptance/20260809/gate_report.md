# M0 Shadow §12.0 Gate Report

_generated 2026-08-09T07:53:01.483867+00:00 · evidence-only · read-only/paper-only_

Overall: **INSUFFICIENT_EVIDENCE**

Fee formula: `fee_prediction_error_pct = abs(actual - predicted) / predicted * 100`。
缺失、非有限、零或负预测值均记为 `UNKNOWN`，绝不记作 0% 误差。
模拟仓按唯一 `(source_run, position_identity)` 计数，重复 tick 不增加仓数。
覆盖广度按去除尾部 `:reentry:N` 后缀的 root pool 计数；仓位闸同时要求 identity >= 50 与 root pool >= 5。
当前覆盖：unique position identities = 0；unique root pools = 0。
PnL gate 精度：`abs(raw shadow net PnL) <= 1e-09 USD` 在判定前保守归零；原值保留在 `raw_value`。

| Check | Value | Threshold | Status |
|---|---:|---:|---|
| shadow_duration_days | — | >= 14 | UNKNOWN |
| simulated_positions | 0 | >= 50 unique (source_run, position_identity) AND >= 5 unique root pools | UNKNOWN |
| fee_prediction_error_pct | — | < 20% | UNKNOWN |
| shadow_net_pnl_usd | — | > 0 | UNKNOWN |
| simulated_drawdown_pct | — | < 8% | UNKNOWN |
| rpc_severe_unresolved | 0 | = 0 | PASS |

此报告只汇总 M0 shadow 证据，不授权 M1、签名、广播或任何真实交易。
