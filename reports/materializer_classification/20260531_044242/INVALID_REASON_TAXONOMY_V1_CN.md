# INVALID_REASON_TAXONOMY_V1_CN

- completed_strict_future_mark
  active_at_target=true, entry_trusted=true, future_position_mark_exists=true
- horizon_not_mature
  target_time > now
- terminal_before_target
  close_time < target_time
- active_at_target_no_future_position_mark
  active_at_target=true, horizon matured=true, no future position mark
- pool_mark_only_counterfactual
  pool mark exists near target, no future position mark, counterfactual only
- no_mark_available
- entry_untrusted
- unknown

- clean proof eligibility: only completed_strict_future_mark
- terminal_before_target cannot be clean proof
- pool_mark_only_counterfactual cannot be clean proof
- horizon_not_mature cannot be clean proof
