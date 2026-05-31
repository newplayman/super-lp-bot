# 已修复的 bug / 口径问题清单

- `terminal_exit_mark / pool_mark_only 误读` | fixed=`yes` | residual_risk=`low`
- `decision_trace_id join 到 trace_id 而不是 id` | fixed=`yes` | residual_risk=`medium`
- `decision_trace 重复计数污染` | fixed=`yes` | residual_risk=`low`
- `terminal_before_target 被归入 no_future_mark` | fixed=`yes` | residual_risk=`low`
- `hardcoded 10 USD entry notional 伪信号` | fixed=`yes` | residual_risk=`low`
- `pool regime temporal leakage` | fixed=`yes` | residual_risk=`medium`
- `retained_sample_count / quarantine 0.0 混入口径` | fixed=`yes` | residual_risk=`low`
- `VPS runtime env / DB DSN 加载问题` | fixed=`yes` | residual_risk=`medium`
- `Git sync / artifact publish workflow 改进` | fixed=`yes` | residual_risk=`low`
