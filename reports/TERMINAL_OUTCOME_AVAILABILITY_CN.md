# Terminal Outcome Availability

- scope: `terminal_before_target` rows from mark-gap causal audit

| Horizon | terminal_before_target count | shadow_exit_decision | shadow_exit_action | closed position mark | terminal net_pnl_usd | terminal net_pnl_pct | terminal outcome auditable |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 6h | 5683 | 5683 | 5655 | 5683 | 5683 | 5683 | 5655 |
| 24h | 14047 | 14047 | 14019 | 14047 | 14047 | 14047 | 14019 |

## Decision

- `terminal_exit_mark` 可以作为独立 `outcome_type` 进入研究层。
- 当前 terminal 样本的可审计覆盖率已经非常高：
  - `6h`: `5655 / 5683`，约 `99.51%`
  - `24h`: `14019 / 14047`，约 `99.80%`
- 因此，若 strict proof 接受 `terminal_exit_mark` 且要求 exit decision/action 完整，`terminal_outcome_gate` 可以判 `PASS`。

## Strict-valid requirements for terminal_exit_mark

1. `shadow_exit_decision` 可审计
2. `shadow_exit_action` 可审计
3. 存在 closed/terminal position mark
4. terminal `net_pnl_usd` 与 `net_pnl_pct` 可计算

## If terminal outcome is incomplete

- 剩余缺口主要是少量没有 `shadow_exit_action` 的样本。
