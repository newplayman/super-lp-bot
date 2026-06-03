# Meteora Partial Survival Scope Freeze — Stage C

- stage: `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1`
- run_id: `20260603_190910`
- branch: `feat/supabase-postgres-deployment`
- head_before: `3065d23`

## 0. 关键冻结

```text
scope                = partial_pool2_only
included_pool_count  = 1  (X/USDC pool 2)
excluded_pool_count  = 1  (SOL/USDC pool 1; reason=no_quote_data)
honesty              = 本报告是 PARTIAL; not full; 不能代表所有 Meteora DLMM
reused_from          = V8 prior survival EV preview 20260603_153736
                      (same input scope, same heuristic model; re-run for verification)
```

## 1. included_pools (X/USDC pool 2)

| field | value |
|---|---|
| pool_address | `9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad` |
| pool_label | X/USDC (pool 2) |
| source_file | `fetch_lb_pair_lock_info.ts` (from official Meteora DLMM SDK examples) |
| quote_status | **ready** (V6 6/6 stable at 5/7/9 arrays; 10U=941005 raw X; 20U=1882010 raw X; not re-run) |
| bin_liquidity_status | **ready** (V6 231 bins with liquidez at 5_arrays; V7 280 bins decoded at 5_arrays sanity) |
| fee_snapshot_status | **ready** (V3+V4: base_fee_bps=1.5; max_fee_bps=10; protocol_fee_bps=null) |
| pool_snapshot_status | **ready** (V3+V4: token_x=FUAfBo2...; token_y=USDC; bin_step=100; active_bin_id=-236; active_price=0.0955) |
| effective_rate | 1 X ≈ 10.62 USDC for 10U/20U USDC swap (V6 evidence) |
| excluded | false |

## 2. excluded_pools (SOL/USDC pool 1)

| field | value |
|---|---|
| pool_address | `5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF` |
| pool_label | SOL/USDC (pool 1) |
| source_file | `swap_quote.ts` (from official Meteora DLMM SDK examples) |
| exclusion_reason | **no_quote_data** |
| exclusion_detail | V5+V6+V7 (7 stages of coverage expansion at 3/5/7/9/12/15 arrays per spec hard cap): SOL/USDC quote 0/8 cumulative. Root cause: 0 bins with liquidity at coverage 15 (21% price range, 1050 bins decoded); on-chain liquidity at active_bin_id=-12248 is concentrated even further than ±10% from active bin. This is real on-chain fact, not RPC limit. Single-account path works fine (V7 18/27 success on public RPC). |
| paid_rpc_required_for_full_scope | true |
| paid_rpc_setup_candidate | true (alternative path if 2-pool EV needed) |
| excluded | true |

## 3. Scope Honesty Assertions (per spec)

- 本报告是 **PARTIAL**; not full
- 不能代表所有 Meteora DLMM pools
- 不能代表 SOL/USDC (excluded; no_quote_data)
- 不能作为 probe / live / canary / paper 执行依据
- cannot be used for full 2-pool EV computation
- can_enter_partial_survival_ev_preview = true (per V7 final verdict)
- can_enter_full_survival_ev_preview = false (per V7 final verdict)

## 4. Data Assets (for partial preview; X/USDC only)

| asset | source | status |
|---|---|---|
| quote snapshot | V6 (meteora_quote_smoke_v2.json) | 6/6 stable |
| bin liquidity | V6 (meteora_expanded_bin_liquidity_decode.json) | 231 bins with liquidez |
| fee snapshot | V3+V4 (meteora_fee_snapshot.json) | 1.5% base / 10% max |
| pool snapshot | V3+V4 (meteora_pool_snapshot.json) | bin_step=100, active_bin_id=-236 |
| reserves | V4 (meteora_pool_snapshot.json) | 101T X / 2.2T USDC |

## 5. Data Missing (must mark "missing", not 0; per spec)

- actual on-chain trading volume
- actual realized IL/LVR
- actual realized slippage
- real token USDC supply
- actual Solana priority fee
- actual rent

→ these will be marked "missing" in stage D model input; will use scenario-based proxies for fee capture.

## 6. Re-run note (V8 → V8b)

This is a verification re-run of the prior survival EV preview (20260603_153736, commit 3065d23). Same inputs, same heuristic model, same 168 EV cells, same partial scope. The prior run has already been committed; this re-run creates a new RUN_ID directory so that:

- audit trail records the re-run timestamp (20260603_190910)
- future test runs can verify the model is deterministic and the negative EV finding is reproducible
- the same model output is recomputed without changes to v2 (line count 992 unchanged)

## 7. 不在本阶段做

- ❌ 不把 partial EV 当 full EV 报告
- ❌ 不 fake data 填充 missing 字段
- ❌ 不接 wallet / 不读 keypair
- ❌ 不构造 transaction
- ❌ 不 modify EVM executor v2

## 8. 安全断言

```text
this_stage_only_scope_freeze     = true
partial_scope_explicitly_marked  = true
solana_wallet_or_keypair_touched = false
can_run_probe_now                = false
v2_line_count_unchanged          = true (992)
```

## 9. 下一阶段

进入 Stage D — survival EV model input build (X/USDC only; 6 notionals × 7 hold_windows × 4 scenarios = 168 cells; 缺失字段标记 'missing').
