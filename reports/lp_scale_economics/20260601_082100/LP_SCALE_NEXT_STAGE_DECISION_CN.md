# LP Scale Next Stage Decision

- recommended_next_stage: `NEW_DATA_PIPELINE_FIRST`
- can_run_probe_now: `no`
- manual_approval_required_for_probe: `yes`

理由：
- 旧 LP 研究线已经冻结，本轮只是新框架。
- 当前可做 virtual notional dry model，但 100U+ depth、真实 fee accrual、route quote 仍不够。
- 因此优先级应回到新数据管线，而不是直接 probe 或重启旧策略。
