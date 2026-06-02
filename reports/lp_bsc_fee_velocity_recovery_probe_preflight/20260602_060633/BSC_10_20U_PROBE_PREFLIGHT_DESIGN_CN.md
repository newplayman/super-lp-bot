# BSC 10/20U probe preflight DESIGN（仅设计，不执行）

- stage: `LP_BSC_FEE_VELOCITY_RECOVERY_AND_PROBE_PREFLIGHT_PIPELINE_V1`
- run_id: `20260602_060633`
- preflight_kind: `candidate_present_design_only`
- can_run_probe_now: **`False`**
- manual_approval_required_for_probe: **`True`**

## 候选目标（仅设计）

- pool: `0x172fcd41e0913e95784454622d1c3724f546f849`
- pair: `USDT/WBNB`
- fee_tier_raw: `100`
- hold_window: `15m`
- notional_usd: `10–20`
- single_pool_only: `True`
- low_risk_path_only: `True`

## 进入 probe 前必须满足的 gate（本脚本不放行）

1. precise quote ready
2. tick-liquidity ready
3. real cost ready
4. fee velocity ready
5. realistic or near-break-even positive candidate present
6. manual approval required
7. dry-run transaction builder only after approval
8. no auto-submit

## 一旦人工放行（仍需独立审计后实施），必须记录

- tokenId
- mint_tx_hash
- feeGrowthInside (entry & exit)
- tokensOwed (entry & exit)
- exit_quote
- actual_PnL_in_USD
- actual_fee_accrual_in_USD

## 严格执行边界（preflight 阶段一律禁止）

```text
max_funds_usd                                  = 20
wallet_load_allowed_in_this_phase              = False
signer_create_allowed_in_this_phase            = False
eth_sendTransaction_allowed_in_this_phase      = False
eth_sendRawTransaction_allowed_in_this_phase   = False
increaseLiquidity_allowed_in_this_phase        = False
decreaseLiquidity_allowed_in_this_phase        = False
collect_allowed_in_this_phase                  = False
approve_allowed_in_this_phase                  = False
```

- best_net_ev_proxy_usd: `-0.015560`
- best_net_ev_proxy_pct: `-0.0778`

## 全局安全

```text
edge_proven                = no
tiny_canary_allowed        = no
can_run_probe_now          = no
wallet_or_tx_touched       = false
actual_fee_ready           = false
token_id_available         = false
```
