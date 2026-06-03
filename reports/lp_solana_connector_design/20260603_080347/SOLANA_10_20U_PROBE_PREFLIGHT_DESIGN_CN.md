# Solana 10/20U Probe Preflight Design — Stage J

- stage: `LP_SOLANA_LP_CONNECTOR_DESIGN_V1`
- run_id: `20260603_080347`

## 0. 严正声明

**本阶段只做 design。**

- ❌ 不读 wallet / private key / seed phrase / keypair
- ❌ 不创建 signer
- ❌ 不创建 transaction (signed or unsigned)
- ❌ 不签名
- ❌ 不发送
- ❌ 不开仓 LP
- ❌ 不关仓 LP
- ❌ 不 collect fee
- ❌ 不开 live / paper / canary
- ❌ 不桥接
- ❌ 不换币

任何 wallet pubkey 出现都是**只读**（用于 getBalance + getAccountInfo）。

## 1. probe 前置 gate (12 项)

```text
1.  no_wallet_or_keypair_in_design            (this stage constraint; always true)
2.  public_wallet_only_in_later_dry_run        (next stage: read-only dry-run)
3.  balance_check                              (getBalance >= 2.0 SOL)
4.  token_account_readiness                   (USDC balance >= 10 + slippage)
5.  rent_exemption                            (estimated rent for new accounts)
6.  transaction_simulation                    (simulateTransaction, NOT sendTransaction)
7.  priority_fee                              (compute estimate)
8.  position_account_creation                 (PDA derivation; no actual create)
9.  token_account_creation                    (ATA existence check)
10. deposit_token_ratio                        (Meteora: bin range quote)
11. exit_path                                  (claimFee + removeLiquidity path)
12. fee_collection                             (read position.unclaimedFees)
```

## 2. 详细 gate

### 2.1 balance_check

```python
# pseudo
sol_balance = solana_rpc.get_balance(wallet_pubkey)  # lamports
sol_balance_sol = sol_balance / 1e9
if sol_balance_sol < 2.0:
    return Block("insufficient_sol_for_rent_tx")
```

Required: 2.0 SOL to cover rent (3 accounts × 0.00089 = 0.0027 SOL) + tx fees (0.00001 × 4 = 0.00004) + priority (0.001) + slippage buffer (1.99 SOL).

### 2.2 token_account_readiness

```python
usdc_ata = derive_ata(wallet_pubkey, USDC_MINT)
usdc_account = solana_rpc.get_account_info(usdc_ata)
if usdc_account is None:
    ata_creation_required = True
    rent_for_ata = 0.00204  # SOL
else:
    usdc_balance = solana_rpc.get_token_account_balance(usdc_ata)
    if usdc_balance < 10_500_000:  # 10.5 USDC (10 + 0.5 slippage)
        return Block("insufficient_usdc_balance")
```

### 2.3 rent_exemption

```python
n_new_accounts = 3 if existing_ata_only else 1  # position + 2 ATAs
total_rent = n_new_accounts * 0.00089088
if sol_balance_sol - priority_fee < total_rent + 0.01:  # safety margin
    return Block("insufficient_balance_for_rent")
```

### 2.4 transaction_simulation (read-only)

```python
# Build unsigned tx (in future stage; not this stage)
# unsigned_tx = build_open_position_tx(wallet, pool, bin_range, amount_in)
# result = solana_rpc.simulate_transaction(unsigned_tx)
# Check result.err is None
# Check result.units_consumed <= 1_400_000 (compute budget)
# Check result.return_data is sensible
```

**This stage**: design only. Don't actually build unsigned tx. Don't call simulateTransaction. Leave as design spec.

### 2.5 priority_fee

```python
priority_fee_estimate_sol = (200_000 * 5000) / 1e6 / 1e9  # 200k CU * 5k micro-lamports/CU
# ~ 0.001 SOL = $0.15 at $150 SOL
```

For Meteora DLMM open + close, ~ 2-3 transactions each ~ 200k CU.
→ 2-3 × 0.001 = 0.002-0.003 SOL priority fee = $0.30-0.45

### 2.6 position_account_creation (design only)

For Meteora DLMM: position pubkey = PDA from `[DLMM program, "position", lb_pair_pubkey, lower_bin_id, upper_bin_id, owner_pubkey]`
→ derived via `Pubkey.find_program_address([...seeds...], DLMM_program)`
→ **read-only** in this stage; only compute the address

### 2.7 token_account_creation

Same as 2.2 (ATA existence check).

### 2.8 deposit_token_ratio (Meteora DLMM)

```python
# Meteora SDK: getDepositQuote(pool, amount_in_token, bin_range)
# Returns: amount_token_x, amount_token_y
amount_x, amount_y = meteora_dlmm_get_deposit_quote(
    pool=pool_pubkey,
    amount_in_raw=10_000_000,  # 10 USDC
    bin_range=[lower_bin, upper_bin]
)
```

### 2.9 exit_path (design only)

For Meteora DLMM:
- `removeLiquidity(position_pubkey, liquidity_amount, min_amount_x, min_amount_y)` — signed tx
- `claimFee(position_pubkey)` — signed tx
- `closePosition(position_pubkey)` — signed tx (recover rent)

In this stage: design only; document the path; don't build or sign.

### 2.10 fee_collection (read-only)

```python
position_state = solana_rpc.get_account_info(position_pubkey)
unclaimed_x = parse_amount(position_state.data, "unclaimedFeesX")
unclaimed_y = parse_amount(position_state.data, "unclaimedFeesY")
```

### 2.11 actual PnL telemetry (future stage)

```python
# After position open + hold + close:
actual_fee_collected = (unclaimed_x_at_open - unclaimed_x_at_close, ...) # X + Y
actual_amount_x_at_close = ... # from close tx
actual_amount_y_at_close = ... # from close tx
# PnL = (final_amount_x * price_x + final_amount_y * price_y) - initial_deposit_value
```

## 3. preflight_pass criteria

| preflight_pass | 条件 |
|---|---|
| `yes` | 12 gates 全过; tx simulation ok; cost < $0.01 round trip |
| `warn` | 1-2 gates borderline (e.g. balance 1.5 SOL; ata_creation_required) |
| `no` | 任何 hard gate fail (e.g. balance < 0.5 SOL; pool不存在; token 余额不足) |

## 4. 安全断言

```text
this_stage_only_design_preflight      = true
this_stage_does_not_execute_probe      = true
this_stage_does_not_load_keypair       = true
this_stage_does_not_sign               = true
this_stage_does_not_send               = true
solana_wallet_or_keypair_touched       = false  (仅 pubkey 用于 getBalance; pubkey 是公开)
can_run_probe_now                      = false
edge_proven                            = "no"
tiny_canary_allowed                    = "no"
```

## 5. 不在本阶段做

- ❌ 实际跑 getBalance (no RPC)
- ❌ 实际跑 getAccountInfo
- ❌ 实际跑 simulateTransaction
- ❌ 任何 transaction
- ❌ 任何 wallet 操作

## 6. 真正执行阶段 (NOT THIS STAGE)

spec 说 "本阶段不执行" — actual probe execution 在**未来** `LP_SOLANA_10_20U_PROBE_PREFLIGHT_REVIEW_V1` 之后的某个阶段：

- `LP_SOLANA_10_20U_PROBE_PREFLIGHT_REVIEW_V1` (run preflight against candidate pool)
- `LP_SOLANA_10_20U_PROBE_DRY_RUN_BUILDER_V1` (build unsigned tx, simulate, no sign)
- `LP_SOLANA_10_20U_PROBE_FIRST_EXECUTION_V1` (operator explicit approval → actual send)

本阶段**只**做 design。
