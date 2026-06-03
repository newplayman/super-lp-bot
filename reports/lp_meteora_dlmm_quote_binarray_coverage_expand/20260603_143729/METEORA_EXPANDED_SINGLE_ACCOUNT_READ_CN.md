# Meteora Expanded Single-Account Read — Stage E

- stage: `LP_METEORA_DLMM_QUOTE_BINARRAY_COVERAGE_EXPAND_V1`
- run_id: `20260603_143729`

## 0. 关键结果

```text
attempted_count          = 42
success_count            = 33 (78.6%)
account_null_count       = 9  (un-initialized bin array accounts; honest finding)
public_rpc_403_count     = 0
public_rpc_410_count     = 0
```

→ Single-account path **scales** with 5x more requests (V5: 6/6; V6: 33/42). V5's "1-account OK, 2-account 403" finding **holds at scale**.

## 1. Per-coverage 结果

| coverage | attempted | success | account_null |
|---|---|---|---|
| 5_arrays | 10 (2 pools × 5) | 9 (1 account_null at offset -2 pool 1) | 1 |
| 7_arrays | 14 (2 pools × 7) | 11 (3 account_null at offsets -3, +3 pool 1) | 3 |
| 9_arrays | 18 (2 pools × 9) | 13 (5 account_null at far offsets pool 1) | 5 |
| **total** | **42** | **33** | **9** |

## 2. 关键发现: account_null 是真实 finding，不是 RPC 限制

`account_null` = `getAccountInfo` returned null = account doesn't exist at this PDA.

- 原因: bin array accounts 是 lazy-initialized; 只有当 liquidity 被 deposit 时才会创建
- pool 1 (SOL/USDC) 在 far offsets (-4, -3, -4) 处的 bin array accounts 还没创建
- 反映真实 on-chain 状态; **不**代表 connector bug

## 3. 与 V5 关键比较

| metric | V5 (3 arrays) | V6 (5/7/9 arrays) | delta |
|---|---|---|---|
| single-account success | 6/6 | 33/42 | 5.5x |
| 0 RPC errors | yes | yes | same |
| account_null | 0 | 9 | 9 honest findings (V5 didn't try these offsets) |

→ V5 evidence holds: public RPC allows single-account read; multi-account read (chunked) was the 403 cause. V6 confirms.

## 4. 不在本阶段做

- ❌ 不调 GPA
- ❌ 不读 keypair
- ❌ 不构造 transaction
- ❌ 不 paid RPC
- ❌ 不 fake success (account_null is honest, not failure)
- ❌ 不修改 EVM executor v2

## 5. 安全断言

```text
this_stage_only_rpc_read      = true
rpc_method_used               = connection.getAccountInfo (single pubkey)
no_gpa_used                   = true
no_keypair                    = true
no_transaction                = true
solana_wallet_or_keypair_touched = false
can_run_probe_now             = false
v2_line_count_unchanged       = true (992)
```

## 6. 下一阶段

进入 Stage F — expanded bin liquidity decode: 用 SDK `program.account.binArray.fetch(pubkey)` 解析 33 个 successful bin array accounts; 预期 ~33 × 70 = 2310 bins (V5: 6 × 70 = 420; V6 期望 5.5x).
