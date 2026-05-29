# Recent Mark Gap Causal

- scope: recent 6h / recent 24h rows relative to latest decision trace in each horizon

| Recent Window | Root Cause Category | Count | Share % |
| --- | --- | ---: | ---: |
| recent_24h | terminal_before_target | 2631 | 100.000 |
| recent_6h | terminal_before_target | 716 | 100.000 |

## Judgment

- `recent_6h` 与 `recent_24h` 都是 `100% terminal_before_target`。
- 这说明当前 pipeline 的主问题不是 active 持仓 mark writer 没跟上。
- 当前主问题是：持仓在 horizon target 前已终止，但 repaired_v2 仍坚持只接受 `future_position_mark`，没有把可审计的 `terminal_exit_mark` 纳入 strict reality 语义。
- 因此后续优先级应从“修 mark writer”切换为“补 terminal outcome proof 语义”。
