# LP Reward Decay Replay v1

Generated: 2026-08-08T17:38:32.777200+00:00

Mode: paper-only/read-only. No wallet, signing, broadcast, paid API or chain write.

The 30d headline is deliberately held at 120% while current rewards decay; both the real screener score and allocator rank must follow current evidence instead of extrapolating it.

| step | elapsed | reward APR | screener score | allocator rank | persistence | ENTER |
|---:|---:|---:|---:|---:|---|---|
| 0 | 24.0h | 100.00% | 120.00 | 115.00 | TRUSTED_24H | TRUE |
| 1 | 30.0h | 30.00% | 50.00 | 45.00 | TRUSTED_24H | TRUE |
| 2 | 36.0h | 5.00% | 25.00 | 20.00 | TRUSTED_24H | TRUE |

## Persistence gates

- 300% APR opened 30 minutes ago: ENTER=FALSE, status=TOO_YOUNG_SHADOW_ONLY.
- Missing duration on a reward-bearing pool: ENTER=FALSE, status=MISSING_FAIL_CLOSED.
- Fee-only legacy records: persistence is not applicable and remains compatible.

## Machine assertions

- required_reward_path: PASS
- scores_strictly_decrease: PASS
- allocator_scores_strictly_decrease: PASS
- main_points_enterable: PASS
- young_300pct_rejected: PASS
- missing_persistence_fail_closed: PASS
- finite_scores: PASS
- all_passed: PASS
