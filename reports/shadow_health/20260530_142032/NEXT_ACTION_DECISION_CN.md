# Next Action Decision

- recommended_next_stage: `MATERIALIZER_SEMANTICS_FIX`

basis:

- `intent_open -> position` 不是主要故障点：
  - 24h 内 `5613/5619` 是 `reuse_shadow_position`
  - 当前 `intent_open` 更接近 “对已存在 shadow position 的继续保持/复用” 语义
- `24h` matured positions 的问题是：
  - 全部 `terminal_before_target`
  - 全部只有 `pool_mark_only`
  - strict `shadow_position_lifecycle_proof_v2` 不接受这类 fallback

所以当前最值得推进的是：

- `MATERIALIZER_SEMANTICS_FIX`

而不是：

- `SHADOW_INTENT_POSITION_WRITER_AUDIT`
- `RESEARCH_INTENT_LIFECYCLE_MATERIALIZER`
- 单纯 `CONTINUE_OOS_ACCUMULATION`

