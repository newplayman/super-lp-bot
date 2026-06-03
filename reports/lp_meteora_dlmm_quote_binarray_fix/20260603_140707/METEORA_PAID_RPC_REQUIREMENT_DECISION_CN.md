# Meteora Paid RPC Requirement Decision — Stage I

- stage: `LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT_V1`
- run_id: `20260603_140707`

## 0. 决策

```text
paid_rpc_required       = partial
single_account_path     = proven (6/6 success on public RPC; bypasses V4 multi-account 403)
alternative_to_paid_rpc = extend bin array coverage (5-7 arrays instead of 3) — no paid RPC needed
next_stage_recommendation = LP_METEORA_DLMM_KNOWN_POOL_CONNECTOR_FIX_REPEAT
                            (extend bin array coverage; if still insufficient, then paid RPC)
```

## 1. V5 证据汇总

| 阶段 | attempted | success | blocked | note |
|---|---|---|---|---|
| D PDA 推导 | 6 | 6 | 0 | pure math + PDA; no RPC |
| E single-account getAccountInfo | 6 | 6 | 0 | **6/6 success on public RPC** |
| F small-batch getMultipleAccounts | (skipped) | (n/a) | (n/a) | Stage E had full success; F not needed |
| G bin array decode | 6 accounts | 6 (420 bins) | 0 | SDK program.account.binArray.fetch works |
| H quote smoke v2 | 4 | **2** | 2 | pool 1 (tight bin_step) blocked; pool 2 (wide bin_step) success |

**关键发现**: 之前 V1/V2/V3/V4 全部 quote 0/4, **V5 首次 2/4 quote success** on public RPC. V4 的 multi-account 403 blocker **bypassed**.

## 2. 为什么不是 hard paid_rpc_required

- Single-account path WORKS on public RPC (6/6 = 100%)
- Quote 2/4 success rate on 1 pool (pool 2) — partial but working
- Pool 1 quote blocked 不是 RPC 问题, 是 SDK 限制 (swapQuote needs sufficient bin arrays; pool 1 bin_step=2 tight spacing 需要更多 bin arrays 才能跨过 10U-20U swap range)
- Fix: extend bin array coverage to 5-7 arrays (still public RPC, no paid RPC needed)

## 3. 替代路径: extend bin array coverage on public RPC

```js
// V5 connector logic upgrade:
for (const offset of [-3, -2, -1, 0, 1, 2, 3]) {  // 7 arrays instead of 3
  const idx = activeIndex + offset;
  const [pubkey] = deriveBinArray(lbPair, new BN(idx), programId);
  const [ba] = await connection.getAccountInfo(pubkey);  // single-account; public RPC OK
  // ... pass to swapQuote
}
```

→ 不需 paid RPC. 只需更多 single-account read calls (each ~200-500ms, public RPC OK).

## 4. 何时确实需要 paid RPC

仅当:
- Single-account path 也被 public RPC 拒绝 (V5 evidence: NOT the case; 6/6 single-account OK)
- Pool 有非常广的 liquidity distribution, 需 10+ bin arrays (V5 evidence: NOT the case; 3 arrays work for pool 2)
- 需要 GPA enumerate 全部池 (V5 不需要; known pool feed 已 frozen)

→ V5 单 account path + 7 arrays coverage **足够** 几乎所有场景. Paid RPC **不**必须.

## 5. 如果 operator 仍想用 paid RPC (Phase 2B 备选)

需要的能力 (NOT specific vendor):
- supports `getAccountInfo` (single pubkey)
- supports `getMultipleAccountsInfo` (multi pubkey, larger response)
- supports high-volume account reads (no rate limit on Meteora bin arrays)
- not rate-limited on multi-account `getMultipleAccounts` calls

**不**输出具体厂商推荐 (Helius / Triton / QuickNode) per spec "不得输出具体购买建议".

**环境变量名**: `SOLANA_RPC_URL` 或 `LPBOT_SOLANA_RPC_URL` (如果 operator 决定提供).

## 6. 关键诚实 finding

- V5 single-account path **proven works on public RPC** (6/6 success, no paid RPC needed for bin array read)
- V5 quote smoke 2/4 success (partial) — pool 2 with wide bin_step OK; pool 1 with tight bin_step needs more bin arrays
- paid_rpc_required = **partial** (NOT true) because:
  1. bin array READ works (6/6 single-account)
  2. bin array DECODE works (420 bins)
  3. quote works for 50% of attempts (2/4)
  4. remaining 50% blocked is a SDK liquidity coverage issue, not RPC

→ V4 阻隔 (multi-account 403) **fully bypassed** by V5 single-account path.
→ V5 quote 阻隔 (insufficient bin arrays) **bypassable** by extending coverage to 7+ arrays (still public RPC).

## 7. 候选 next_stage

| next stage | 触发条件 | V5 状态 |
|---|---|---|
| `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1` | quote smoke success + bin liquidity available + fee snapshot available | ⚠️ (quote 2/4 success, but V5 should extend to 4/4 before EV) |
| `LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT` | single-account path promising but incomplete | ✅ 触发 (2/4 quote; can be improved with 7-array coverage) |
| `LP_SOLANA_PAID_RPC_SETUP_REQUIRED` | public RPC blocks bin arrays and no workaround | ❌ (single-account path works; no workaround needed) |
| `LP_METEORA_DLMM_KNOWN_POOL_CONNECTOR_FIX_REPEAT` | connector bug | ❌ (connector V1 works; just need bin array coverage extension) |
| `STOP_LP_RESEARCH_NOW` | no safe read-only path | ❌ (read-only path fully working; quote partially working) |

→ next_stage = `LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT` (extend coverage 3 → 7 arrays; try to reach 4/4 quote success on public RPC).

## 8. 不在本阶段做

- ❌ 不实现 production connector
- ❌ 不接 wallet / 不读 keypair
- ❌ 不构造 transaction
- ❌ 不调 swap tx builder
- ❌ 不 paid RPC call
- ❌ 不 webfetch
- ❌ 不修改 EVM executor v2

## 9. 安全断言

```text
this_stage_only_decision       = true
solana_wallet_or_keypair_touched = false
can_run_probe_now              = false
v2_line_count_unchanged        = true (992)
```

## 10. 下一阶段

进入 Stage J — next-stage decision V5: 选 `LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT` (扩展 7-array 覆盖, 试 4/4 quote 成功).
