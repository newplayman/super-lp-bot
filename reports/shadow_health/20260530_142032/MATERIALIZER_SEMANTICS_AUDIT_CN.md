# Materializer Semantics Audit

- `6h` strict_future_mark_count=`42`, no_future_mark=`26`, pool_mark_only=`13`, terminal_excluded=`3`
- `12h` strict_future_mark_count=`40`, no_future_mark=`28`, pool_mark_only=`14`, terminal_excluded=`2`
- `24h` strict_future_mark_count=`8`, no_future_mark=`60`, pool_mark_only=`41`, terminal_excluded=`0`

- materializer_semantics_status: `OVER_STRICT_RESEARCH_FALLBACK_POSSIBLE`

回答：

- fixed-horizon proof 现在事实上要求严格 `future position mark`
- 对于 research-only 层，可以考虑 `pool_mark_only` fallback 的独立 proof v3
- `terminal-before-target` 不应和 fixed-horizon 正样本混在一起，应该显式分类
- 当前并不是 “same-position marks 被漏掉” 的主问题；`6h/12h` 可以正常命中
- 真正的缺口是：`24h` matured positions terminal 后只剩 pool-level mark，而 strict v2 不接受这个

建议：

- 若继续推进 fixed-horizon 研究，优先级高于 mark worker repair 的是：
  - `MATERIALIZER_SEMANTICS_FIX`
  - 在 research-only 层评估 `pool_mark_only` fallback 的影响

