# Real Fee Accrual Method Policy

- actual_fee_policy: `only if tokenId and real position lineage exist`
- pool_level_fee_policy: `allowed as read-only proxy with confidence marker`
- simulated_fee_policy: `allowed as research-only substitute when actual position fee missing`
- actual_position_fee_without_token_id: `rejected`
- transactional_methods: `future_probe_only`
- pool_level_positive_implies_edge: `no`
