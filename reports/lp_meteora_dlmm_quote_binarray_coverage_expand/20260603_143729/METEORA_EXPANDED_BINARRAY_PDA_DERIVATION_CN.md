# Meteora Expanded Bin Array PDA Derivation — Stage D

- stage: `LP_METEORA_DLMM_QUOTE_BINARRAY_COVERAGE_EXPAND_V1`
- run_id: `20260603_143729`

## 0. 关键结果

```text
pools_attempted          = 2
coverage_tiers           = 3 ([5, 7, 9])
pda_derivation_total     = 42 (2 pools × (5+7+9) = 42)
pda_derivation_success   = 42/42
no_rpc_used              = true (pure PDA)
```

## 1. PDA 推导结果（per pool, per coverage tier）

### 1.1 Pool 1: `5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF` (active_bin_id=-12248, bin_step=2, active_index=-175)

| coverage | offsets | success |
|---|---|---|
| 5_arrays | [-2, -1, 0, +1, +2] | 5/5 |
| 7_arrays | [-3, -2, -1, 0, +1, +2, +3] | 7/7 |
| 9_arrays | [-4, -3, -2, -1, 0, +1, +2, +3, +4] | 9/9 |
| **total** | | **21/21** |

### 1.2 Pool 2: `9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad` (active_bin_id=-236, bin_step=100, active_index=-4)

| coverage | offsets | success |
|---|---|---|
| 5_arrays | [-2, -1, 0, +1, +2] | 5/5 |
| 7_arrays | [-3, -2, -1, 0, +1, +2, +3] | 7/7 |
| 9_arrays | [-4, -3, -2, -1, 0, +1, +2, +3, +4] | 9/9 |
| **total** | | **21/21** |

## 2. 方法

```js
const activeIndex = bnIdToBinArrayIndex(new BN(activeBinId));
for (const arr of [5, 7, 9]) {
  for (const offset of offsetsForCoverage(arr)) {
    const idx = activeIndex + offset;
    const [pubkey] = deriveBinArray(lbPair, new BN(idx), DLMM_PROGRAM_ID);
    // pure PDA; no RPC
  }
}
```

## 3. 关键观察

- 42/42 = 100% success on PDA derivation; deterministic; no RPC cost
- 跨 2 pools × 3 coverage tiers; 总 42 个 pubkeys
- pool 1 (bin_step=2 tight): 9 arrays = 9×70 = 630 bins ≈ 12% price range
- pool 2 (bin_step=100 wide): 9 arrays = 9×70 = 630 bins ≈ 57600% price range (覆盖全)

## 4. 不在本阶段做

- ❌ 不调 RPC (本阶段仅 PDA 推导)
- ❌ 不读 keypair
- ❌ 不构造 transaction
- ❌ 不调 getProgramAccounts
- ❌ 不修改 EVM executor v2

## 5. 安全断言

```text
derivation_method        = pure PDA (deterministic)
no_rpc_used              = true
no_wallet                = true
solana_wallet_or_keypair_touched = false
can_run_probe_now        = false
v2_line_count_unchanged  = true (992)
```

## 6. 下一阶段

进入 Stage E — expanded single-account read: 对 42 个 derived pubkey 各调一次 `connection.getAccountInfo(pubkey)`, 验证 public RPC 仍允许单账户 read (V5 evidence: 6/6 success; V6 待 verify 42 reads).
