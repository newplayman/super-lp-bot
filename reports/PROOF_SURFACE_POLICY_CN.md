# Proof Surface Policy

## Definitions

### Raw Proof Surface
- 输入范围：`shadow_outcome_labels_repaired_terminal_v1` 中 `selected=true` 且 `intent_open=true` 的全部样本。
- 特点：保留所有原始 repaired/terminal-inclusive 样本，包括 `entry_untrusted`、`pool_mark_only`、`terminal_value_zero_bug` 等问题样本。
- 用途：事实保全、问题发现、阻断判定。

### Clean Proof Surface
- 输入范围：从 raw proof surface 中排除不可接受的证明污染样本。
- 必须排除：
  - `entry_untrusted`
  - `terminal_value_zero_bug`
  - `pool_mark_only`
  - `only_pre_target_mark`
  - `entry_value_source untrusted`
  - `net_pnl_pct not calculable`
- 额外要求：
  - `outcome_type in ('future_position_mark', 'terminal_exit_mark')`
  - `mark_source != 'pool_mark_only'`
  - `terminal_value_usd > 0 if terminal_exit_mark`
  - `entry_value_confidence in ('high','trusted')`

### Candidate Proof Surface
- 输入范围：clean proof surface。
- 用途：候选级别分析，只能用于“是否值得继续研究”的讨论。
- 禁止用途：不能直接当作生产级 edge 证明，不能直接触发 canary/live。

## Policy
- `clean_proof_gate PASS` 不等于 `edge_proven`。
- `clean_proof_gate PASS` 只允许进入 `candidate review`。
- 即使 candidate-level 指标为正，也不允许自动开启 `tiny canary`。
- `tiny_canary_allowed` 仍必须保持 `no`，直到 raw proof surface 的 entry/mark/reality 污染完成修复并通过人工二次审计。
