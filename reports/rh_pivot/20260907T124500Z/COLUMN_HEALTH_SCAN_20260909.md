# 全库列健康扫描 — 2026-09-09 09:3x UTC

由 `scripts/lp_rh_column_health_v1_readonly.py`（RH-02r）自动生成，只读。
复现：`python scripts/lp_rh_column_health_v1_readonly.py --db reports/lp_rh/scanner.db`

```
Column health report
========================================================================
rh_assets (total_rows=194)
  chain_id                     nulls=0        distinct=1        CONSTANT   4663
  address                      nulls=0        distinct=194      POPULATED  0x03bc731ffb162cdd7b98d3c6542bfc291126075d
  metadata_version             nulls=0        distinct=1        CONSTANT   1
  symbol_display               nulls=194      distinct=0        EMPTY      -
  uid                          nulls=194      distinct=0        EMPTY      -
  underlying                   nulls=194      distinct=0        EMPTY      -
  decimals                     nulls=0        distinct=1        CONSTANT   18
  multiplier_raw               nulls=194      distinct=0        EMPTY      -
  status                       nulls=194      distinct=0        EMPTY      -
  capability_json              nulls=0        distinct=2        POPULATED  {"extended": "TRADABLE", "market": "TRADABLE", "overnight": 
  source_payload_hash          nulls=194      distinct=0        EMPTY      -
  updated_at                   nulls=0        distinct=1        CONSTANT   2026-09-09T07:40:17Z
rh_bucket_reservations (total_rows=0)
  intent_id                    nulls=0        distinct=0        NO_ROWS    -
  policy_version               nulls=0        distinct=0        NO_ROWS    -
  bucket                       nulls=0        distinct=0        NO_ROWS    -
  amount_usd                   nulls=0        distinct=0        NO_ROWS    -
  status                       nulls=0        distinct=0        NO_ROWS    -
  created_at                   nulls=0        distinct=0        NO_ROWS    -
  released_at                  nulls=0        distinct=0        NO_ROWS    -
  derived_block_hash           nulls=0        distinct=0        NO_ROWS    -
  derived_block_number         nulls=0        distinct=0        NO_ROWS    -
rh_contract_attestations (total_rows=193)
  chain_id                     nulls=0        distinct=1        CONSTANT   4663
  address                      nulls=0        distinct=193      POPULATED  0x03bc731ffb162cdd7b98d3c6542bfc291126075d
  block_hash                   nulls=0        distinct=1        CONSTANT   0x8ebb7bd0aaee7ffe2e6410ee662cea38359efba498ddf6c149e0490d2e
  policy_version               nulls=0        distinct=1        CONSTANT   v1
  code_hash                    nulls=0        distinct=1        CONSTANT   dd432f8669cd184fee419f471467af361774d24acb9ea1e25501c8283a55
  implementation               nulls=0        distinct=1        CONSTANT   0xb35490d6f9163de4f80d88dc75c3516eb64c5ae2
  abi_version                  nulls=193      distinct=0        EMPTY      -
  attestation_status           nulls=0        distinct=1        CONSTANT   ATTESTED_SAME_BLOCK
  evidence_json                nulls=193      distinct=0        EMPTY      -
  expires_at                   nulls=193      distinct=0        EMPTY      -
  created_at                   nulls=0        distinct=1        CONSTANT   2026-09-09T07:41:11Z
rh_economic_evaluations (total_rows=0)
  candidate_key                nulls=0        distinct=0        NO_ROWS    -
  snapshot_id                  nulls=0        distinct=0        NO_ROWS    -
  model_version                nulls=0        distinct=0        NO_ROWS    -
  policy_version               nulls=0        distinct=0        NO_ROWS    -
  horizon_hours                nulls=0        distinct=0        NO_ROWS    -
  position_usd                 nulls=0        distinct=0        NO_ROWS    -
  fee_ev                       nulls=0        distinct=0        NO_ROWS    -
  reward_ev                    nulls=0        distinct=0        NO_ROWS    -
  cost_components_json         nulls=0        distinct=0        NO_ROWS    -
  netcover                     nulls=0        distinct=0        NO_ROWS    -
  abs_profit                   nulls=0        distinct=0        NO_ROWS    -
  q_min                        nulls=0        distinct=0        NO_ROWS    -
  q_max                        nulls=0        distinct=0        NO_ROWS    -
  missing_inputs_json          nulls=0        distinct=0        NO_ROWS    -
  evaluated_at                 nulls=0        distinct=0        NO_ROWS    -
  derived_block_hash           nulls=0        distinct=0        NO_ROWS    -
  derived_block_number         nulls=0        distinct=0        NO_ROWS    -
rh_gate_decisions (total_rows=0)
  decision_id                  nulls=0        distinct=0        NO_ROWS    -
  candidate_key                nulls=0        distinct=0        NO_ROWS    -
  target_mode                  nulls=0        distinct=0        NO_ROWS    -
  primary_status               nulls=0        distinct=0        NO_ROWS    -
  terminal_bits_json           nulls=0        distinct=0        NO_ROWS    -
  dominant_blocker             nulls=0        distinct=0        NO_ROWS    -
  reasons_json                 nulls=0        distinct=0        NO_ROWS    -
  snapshot_ids_json            nulls=0        distinct=0        NO_ROWS    -
  decided_at                   nulls=0        distinct=0        NO_ROWS    -
  derived_block_hash           nulls=0        distinct=0        NO_ROWS    -
  derived_block_number         nulls=0        distinct=0        NO_ROWS    -
rh_journal (total_rows=0)
  event_id                     nulls=0        distinct=0        NO_ROWS    -
  idempotency_key              nulls=0        distinct=0        NO_ROWS    -
  account_debit                nulls=0        distinct=0        NO_ROWS    -
  account_credit               nulls=0        distinct=0        NO_ROWS    -
  asset                        nulls=0        distinct=0        NO_ROWS    -
  amount_raw                   nulls=0        distinct=0        NO_ROWS    -
  is_external_flow             nulls=0        distinct=0        NO_ROWS    -
  ref_json                     nulls=0        distinct=0        NO_ROWS    -
  booked_at                    nulls=0        distinct=0        NO_ROWS    -
rh_market_states (total_rows=6498)
  asset_address                nulls=0        distinct=1        CONSTANT   0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca
  sample_time                  nulls=0        distinct=6498     POPULATED  2026-09-09T09:21:40.234767Z
  chain_id                     nulls=0        distinct=1        CONSTANT   4663
  source_payload_hash          nulls=0        distinct=6489     POPULATED  af37f198fde146f936b2673794e9a9b272e6b11358cc3e37d8a08b739a4a
  session                      nulls=0        distinct=1        CONSTANT   UNKNOWN
  health_flags_json            nulls=0        distinct=2        POPULATED  []
  reference_bid                nulls=6498     distinct=0        EMPTY      -
  reference_ask                nulls=6498     distinct=0        EMPTY      -
  reference_mid                nulls=38       distinct=6460     POPULATED  2476.507705
  reference_age_secs           nulls=39       distinct=14       POPULATED  0
  multiplier_human             nulls=6498     distinct=0        EMPTY      -
  oracle_paused                nulls=6498     distinct=0        EMPTY      -
  derived_block_hash           nulls=6498     distinct=0        EMPTY      -
  derived_block_number         nulls=6498     distinct=0        EMPTY      -
rh_pool_events (total_rows=0)
  chain_id                     nulls=0        distinct=0        NO_ROWS    -
  block_hash                   nulls=0        distinct=0        NO_ROWS    -
  tx_hash                      nulls=0        distinct=0        NO_ROWS    -
  log_index                    nulls=0        distinct=0        NO_ROWS    -
  block_number                 nulls=0        distinct=0        NO_ROWS    -
  pool_key                     nulls=0        distinct=0        NO_ROWS    -
  event_type                   nulls=0        distinct=0        NO_ROWS    -
  amount0_raw                  nulls=0        distinct=0        NO_ROWS    -
  amount1_raw                  nulls=0        distinct=0        NO_ROWS    -
  liquidity_raw                nulls=0        distinct=0        NO_ROWS    -
  tick                         nulls=0        distinct=0        NO_ROWS    -
  observed_at                  nulls=0        distinct=0        NO_ROWS    -
rh_pool_registry (total_rows=1)
  chain_id                     nulls=0        distinct=1        CONSTANT   4663
  protocol                     nulls=0        distinct=1        CONSTANT   v3
  pool_key                     nulls=0        distinct=1        CONSTANT   0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca
  pool_address                 nulls=0        distinct=1        CONSTANT   0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca
  pool_id                      nulls=1        distinct=0        EMPTY      -
  token0                       nulls=1        distinct=0        EMPTY      -
  token1                       nulls=1        distinct=0        EMPTY      -
  fee                          nulls=1        distinct=0        EMPTY      -
  tick_spacing                 nulls=1        distinct=0        EMPTY      -
  hooks                        nulls=1        distinct=0        EMPTY      -
  attestation_status           nulls=0        distinct=1        CONSTANT   DISCOVERED_NOT_ATTESTED
  discovered_at                nulls=0        distinct=1        CONSTANT   2026-09-09T07:40:17Z
rh_position_marks (total_rows=0)
  position_id                  nulls=0        distinct=0        NO_ROWS    -
  mark_time                    nulls=0        distinct=0        NO_ROWS    -
  price_snapshot_id            nulls=0        distinct=0        NO_ROWS    -
  reference_nav                nulls=0        distinct=0        NO_ROWS    -
  liquidation_nav              nulls=0        distinct=0        NO_ROWS    -
  accrued_fee                  nulls=0        distinct=0        NO_ROWS    -
  unvalued_risk_json           nulls=0        distinct=0        NO_ROWS    -
  derived_block_hash           nulls=0        distinct=0        NO_ROWS    -
  derived_block_number         nulls=0        distinct=0        NO_ROWS    -
rh_reconciliation_runs (total_rows=0)
  run_id                       nulls=0        distinct=0        NO_ROWS    -
  started_at                   nulls=0        distinct=0        NO_ROWS    -
  finished_at                  nulls=0        distinct=0        NO_ROWS    -
  evidence_json                nulls=0        distinct=0        NO_ROWS    -
  delta_json                   nulls=0        distinct=0        NO_ROWS    -
  verdict                      nulls=0        distinct=0        NO_ROWS    -
  derived_block_hash           nulls=0        distinct=0        NO_ROWS    -
  derived_block_number         nulls=0        distinct=0        NO_ROWS    -
rh_rpc_health (total_rows=6498)
  provider                     nulls=0        distinct=1        CONSTANT   https://rpc.mainnet.chain.robinhood.com
  method                       nulls=0        distinct=1        CONSTANT   pool_state_round
  sample_time                  nulls=0        distinct=6498     POPULATED  2026-09-09T09:21:40.234767Z
  latency_ms                   nulls=0        distinct=720      POPULATED  281
  error                        nulls=6416     distinct=38       POPULATED  eth_getBlockByNumber:{"transport": "URLError: <urlopen error
  last_good_block              nulls=0        distinct=6460     POPULATED  57432804
  state                        nulls=0        distinct=3        POPULATED  NORMAL
rh_shadow_positions (total_rows=0)
  strategy_episode             nulls=0        distinct=0        NO_ROWS    -
  position_id                  nulls=0        distinct=0        NO_ROWS    -
  pool_key                     nulls=0        distinct=0        NO_ROWS    -
  profile                      nulls=0        distinct=0        NO_ROWS    -
  bucket                       nulls=0        distinct=0        NO_ROWS    -
  initial_token0_raw           nulls=0        distinct=0        NO_ROWS    -
  initial_token1_raw           nulls=0        distinct=0        NO_ROWS    -
  tick_lower                   nulls=0        distinct=0        NO_ROWS    -
  tick_upper                   nulls=0        distinct=0        NO_ROWS    -
  virtual_liquidity_raw        nulls=0        distinct=0        NO_ROWS    -
  opened_at                    nulls=0        distinct=0        NO_ROWS    -
  closed_at                    nulls=0        distinct=0        NO_ROWS    -
rh_source_snapshots (total_rows=6489)
  source                       nulls=0        distinct=1        CONSTANT   rh_rpc:pool_state
  payload_hash                 nulls=0        distinct=6489     POPULATED  00027d6716feef2fe32456867740e6488ef33b417af2ba018fa35d3dbf1e
  source_event_time            nulls=6489     distinct=0        EMPTY      -
  fetch_time                   nulls=0        distinct=6489     POPULATED  2026-09-08T05:15:14.435446Z
  schema_kind                  nulls=0        distinct=1        CONSTANT   JSON_RPC_V1
  raw_ref                      nulls=6489     distinct=0        EMPTY      -
  quality                      nulls=0        distinct=2        POPULATED  OK
rh_tx_intents (total_rows=0)
  request_id                   nulls=0        distinct=0        NO_ROWS    -
  idempotency_key              nulls=0        distinct=0        NO_ROWS    -
  chain_id                     nulls=0        distinct=0        NO_ROWS    -
  wallet_id                    nulls=0        distinct=0        NO_ROWS    -
  position_id                  nulls=0        distinct=0        NO_ROWS    -
  nonce                        nulls=0        distinct=0        NO_ROWS    -
  state                        nulls=0        distinct=0        NO_ROWS    -
  calldata_hash                nulls=0        distinct=0        NO_ROWS    -
  policy_hash                  nulls=0        distinct=0        NO_ROWS    -
  expires_at                   nulls=0        distinct=0        NO_ROWS    -
  created_at                   nulls=0        distinct=0        NO_ROWS    -
rh_tx_receipts (total_rows=0)
  request_id                   nulls=0        distinct=0        NO_ROWS    -
  tx_hash                      nulls=0        distinct=0        NO_ROWS    -
  block_hash                   nulls=0        distinct=0        NO_ROWS    -
  block_number                 nulls=0        distinct=0        NO_ROWS    -
  status                       nulls=0        distinct=0        NO_ROWS    -
  gas_used                     nulls=0        distinct=0        NO_ROWS    -
  reorg_detected               nulls=0        distinct=0        NO_ROWS    -
  observed_at                  nulls=0        distinct=0        NO_ROWS    -

empty_columns (23):
  rh_assets.multiplier_raw
  rh_assets.source_payload_hash
  rh_assets.status
  rh_assets.symbol_display
  rh_assets.uid
  rh_assets.underlying
  rh_contract_attestations.abi_version
  rh_contract_attestations.evidence_json
  rh_contract_attestations.expires_at
  rh_market_states.derived_block_hash
  rh_market_states.derived_block_number
  rh_market_states.multiplier_human
  rh_market_states.oracle_paused
  rh_market_states.reference_ask
  rh_market_states.reference_bid
  rh_pool_registry.fee
  rh_pool_registry.hooks
  rh_pool_registry.pool_id
  rh_pool_registry.tick_spacing
  rh_pool_registry.token0
  rh_pool_registry.token1
  rh_source_snapshots.raw_ref
  rh_source_snapshots.source_event_time
constant_columns (24):
  rh_assets.chain_id
  rh_assets.decimals
  rh_assets.metadata_version
  rh_assets.updated_at
  rh_contract_attestations.attestation_status
  rh_contract_attestations.block_hash
  rh_contract_attestations.chain_id
  rh_contract_attestations.code_hash
  rh_contract_attestations.created_at
  rh_contract_attestations.implementation
  rh_contract_attestations.policy_version
  rh_market_states.asset_address
  rh_market_states.chain_id
  rh_market_states.session
  rh_pool_registry.attestation_status
  rh_pool_registry.chain_id
  rh_pool_registry.discovered_at
  rh_pool_registry.pool_address
  rh_pool_registry.pool_key
  rh_pool_registry.protocol
  rh_rpc_health.method
  rh_rpc_health.provider
  rh_source_snapshots.schema_kind
  rh_source_snapshots.source
```
