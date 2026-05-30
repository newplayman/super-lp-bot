# Next Action Decision

- recommended_next_stage: `SHADOW_MARK_COVERAGE_FIX`

basis:

- shadow daemon is healthy and running
- DB writes are fresh for `shadow_decision_trace`, `shadow_position_marks`, and `positions`
- selected / intent_open are not zero, so selector starvation is not the primary issue
- new positions do exist, but recent positions have `0` future `6h/12h/24h` marks in proof
- materializer itself is writing stable run_ids without duplicate `position_id+horizon`

why not the others:

- `CONTINUE_OOS_ACCUMULATION`: too passive; current evidence shows a coverage bottleneck, not just slow growth
- `EXTEND_SHADOW_RUNTIME`: insufficient by itself because even recent `48h` positions still show `0` future mark coverage in current proof
- `SHADOW_SELECTOR_GATE_REVIEW`: not primary; selected and intent_open counts are high
- `MATERIALIZER_FIX`: not primary; materializer run/write pattern looks healthy
- `SHADOW_DAEMON_RECOVERY_REQUIRED`: excluded; daemon is running and tables are fresh
