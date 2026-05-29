# Tier C Manual Candidate Audit

- Source verdict: `FAIL`
- Proof unit: `position_lifecycle` only
- Scope: `MICRO_CANDIDATE + WATCH` pools only

| pool_id | original_verdict | best_horizon | best_entry_size | median | p10 | p5 | p1 | win_rate | survival_rate | quarantine_trigger_rate | root_cause |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `0x7cb770d0513c30e0cb45e4899e4a2cbeed6f9830` | MICRO_CANDIDATE | 30m | 10.00 | 0.001924 | -0.019040 | -0.021230 | -0.029241 | 0.604167 | 0.979592 | 0.000000 | TAIL_TOO_HEAVY |
| `0x82dbe18346a8656dbb5e76f74bf3ae279cc16b29` | WATCH | 2h | 10.00 | -0.000273 | -0.009440 | -0.016855 | -0.017922 | 0.439024 | 0.931818 | 1.000000 | EXIT_DEPTH_BAD |
| `0xc9034c3e7f58003e6ae0c8438e7c8f4598d5acaa` | WATCH | 6h | 10.00 | 0.037044 | -0.054554 | -0.068894 | -0.080366 | 0.600000 | 0.416667 | 1.000000 | EXIT_DEPTH_BAD |
| `0xe47f7dba68a00dc1a6f11458bcdfca810e1cfebf` | WATCH | 6h | 10.00 | 0.038812 | -0.007769 | -0.021183 | -0.032221 | 0.833333 | 0.631579 | 1.000000 | EXIT_DEPTH_BAD |

结论：当前 4 个候选池里，没有任何池在 best combo 下同时满足 tail 可接受与 quarantine 可接受。
