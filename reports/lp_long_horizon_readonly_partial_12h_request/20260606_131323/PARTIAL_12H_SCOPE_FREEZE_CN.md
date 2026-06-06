# Partial 12h Scope Freeze

- stage: `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_PARTIAL_REAL_UNIVERSE_REQUEST_V1`
- section: partial_12h_scope_freeze
- run_id: `20260606_131323`
- branch: `feat/supabase-postgres-deployment`
- frozen_at_utc: `2026-06-06T13:15:00Z`

## 0. 总结

✅ **Partial 12h scope 已 frozen**. 12h 只读观察将覆盖 Solana + BSC 真实池 (49 池, 5 protocols). 显式标记 `coverage_scope=partial_solana_bsc_real_universe, full_coverage_ready=false, do_not_treat_as_full_universe=true`. Base 链保持 missing (RPC 不可达), 任何 12h result **不** 能外推到 Base 链.

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `coverage_scope` | **`partial_solana_bsc_real_universe`** |
| `full_coverage_ready` | **false** |
| `do_not_treat_as_full_universe` | **true** |
| `observed_chains` | `["solana", "bsc"]` |
| `missing_chains` | `["base"]` |
| `observable_pool_count_at_freeze` | **49** |
| `observable_chain_count_at_freeze` | **2** |
| `observable_protocol_count_at_freeze` | **5** |
| `placeholder_pool_count_at_freeze` | **0** |
| `expanded_universe_pool_count` | **72** (本 stage 启动 49) |
| `non_observable_pool_count_at_freeze` | **23** (10 Base + 13 BSC + 0 Meteora pending) |
| `approval_required` | **true** |
| `approval_phrase` | `APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=12h mode=readonly no_probe=true scope=partial_solana_bsc` |
| `auto_advance_to_24h` | **false** |
| `long_run_started` | **false** (启动时变 true) |
| `can_run_probe_now` | **false** (LOCKED) |
| `tiny_canary_allowed` | `"no"` (LOCKED) |

## 2. Missing reason (诚实披露)

### 2.1 Base chain 不可达

- **primary public endpoint** `https://mainnet.base.org` → 403 Forbidden (9890ms)
- **fallback 1** `https://base-rpc.publicnode.com` → 403 Forbidden (528ms)
- **fallback 2** `https://base.llamarpc.com` → 403 Forbidden (434ms)
- **fallback 3** `https://1rpc.io/base` → Connection reset (991ms)
- 0/4 Base endpoints reachable in this env.
- **Not adapter code issue**: 4 Base adapters (UniV3, Aerodrome classic) + 1 verify (Slipstream) 全部 self-check clean. 将在能 reach Base RPC 的 env 再 smoke.

### 2.2 Meteora DLMM RPC return empty

- Solana public RPC `https://api.mainnet-beta.solana.com` **reachable** (59ms healthcheck)
- 但 `getMultipleAccountsInfo` 5/5 verified DLMM pools returned empty
- **Not adapter code issue**: 16 Meteora pools 已通过 prior private RPC 验证 on-chain. 当前 public RPC 拿不到 data.

## 3. Partial 12h 启动原则

1. **覆盖范围**: 仅 Solana + BSC. **不** 包括 Base 链任何池.
2. **诚实披露**: 任何 12h result 必须用 `coverage_scope=partial_solana_bsc_real_universe` 解释. **不** 标记为 full coverage.
3. **不自动 24h**: `auto_advance_to_24h=false`. 12h 完成后必须显式审批才能进 24h.
4. **Base/Meteora 池 0**: 49 池 **不** 含任何 Base / Meteora 池 (rpc blocked or empty).
5. **placeholder=0**: 所有 49 池都真实 on-chain, **不** 用 placeholder 替补.

## 4. Partial 12h 启动序列

```
1. Stage A (input evidence)   ✓
2. Stage B (scope freeze)     ✓ (this stage)
3. Stage C (universe build)   → partial_observable_real_pool_universe_for_12h.{csv,json}
4. Stage D (approval record)  → MANUAL_APPROVAL_RECORDED.json
5. Stage E (run config)       → TWELVE_HOUR_PARTIAL_RUN_CONFIG.json
6. Stage F (safety check)     → all checks pass (else abort)
7. Stage G (launch)           → tmux/noHup launch
8. Stage H (finalize)         → 12h 后 stage runner 自动触发
9. Stage I (tests)            → pytest + go test
10. Stage J (git publish)     → commit + push
```

## 5. 锁定字段 (5 项全 false/no + 2 additional)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `long_run_started` | `false` (启动时变 true) |
| `auto_advance_to_24h` | `false` |
| `do_not_treat_as_full_universe` | `true` |
| `no_collector_started_pre_safety_check` | `true` |
| `no_paid_rpc_key_committed` | `true` |
| `no_real_secret_committed` | `true` |

## 6. 严禁 (本轮全部不触发, 启动后仍不触发)

- ❌ 不启动 24h / 48h / 72h / 7d (auto_advance_to_24h=false)
- ❌ 不启动并行 collector (单 stage runner only)
- ❌ 不启用 cron / systemd / daemon
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / seed / keypair / signer
- ❌ 不发送 transaction / approve / mint / swap / bridge
- ❌ 不写 production positions
- ❌ 不覆盖 shadow 原始表
- ❌ 不接 paid RPC / paid indexer
- ❌ **不** 写真实 RPC key / private_key / mnemonic / seed
- ❌ **不**修改 12h data_dir (84 文件, 0 修改)
- ❌ **不**修改 6h data_dir (42 文件, 0 修改)
- ❌ **不**修改 v2 12h FINAL_VERDICT / v2 6h FINAL_VERDICT / corrected verdicts / 12h node report
- ❌ **不**修改 supervisor stage runner
- ❌ **不**修改 collector

## 7. 下游

进入 Stage C (构建 partial observable universe file) → D (审批记录) → E (run config) → F (safety check) → G (launch).
