# Meteora Quote Bin Array Fix Next-Stage Decision — Stage J

- stage: `LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT_V1`
- run_id: `20260603_140707`

## 0. 决策

```text
recommended_next_stage = LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT
default_when_no_explicit_choice = LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT
```

## 1. 5 选项评估

| next stage | 触发条件 | V5 状态 |
|---|---|---|
| `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1` | quote smoke success + bin liquidity + fee | ⚠️ (2/4 quote, need 4/4 first) |
| `LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT` | single-account path promising but incomplete | **✅ 触发** (2/4 quote; fix: extend bin array coverage 3 → 5-7 arrays) |
| `LP_SOLANA_PAID_RPC_SETUP_REQUIRED` | public RPC blocks bin arrays and no workaround | ❌ (single-account path works; 6/6 success on public RPC) |
| `LP_METEORA_DLMM_KNOWN_POOL_CONNECTOR_FIX_REPEAT` | connector bug | ❌ (connector V1 works; just need wider coverage) |
| `STOP_LP_RESEARCH_NOW` | no safe read-only path | ❌ (read-only path fully working) |

## 2. 为什么选 LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT

### 2.1 V5 evidence (5 stages, 全部 working)

| 阶段 | 结果 |
|---|---|
| C SDK helper audit | 12 helpers audited; single-account path identified as viable |
| D PDA derivation | 6/6 deterministic pubkeys (no RPC) |
| E single-account getAccountInfo | **6/6 success on public RPC** (V4 multi-account blocker **bypassed**) |
| G bin liquidity decode | 420 bins decoded (6 arrays × 70 bins) |
| H quote smoke v2 | **2/4 success** (V1-V4 全部 0%; V5 首次 quote 成功) |

### 2.2 剩余 2/4 quote blocked 原因

- pool 1 (SOL/USDC) bin_step=2: tight spacing; 3 bin arrays × 70 bins = 210 bins = ~4% price range; 10U-20U USDC swap 可能需要更多 bins
- pool 2 (X/USDC) bin_step=100: wide spacing; 210 bins = ~21000% range; swap 充分

→ **不是 RPC 问题, 是 SDK swapQuote 需要足够 bin arrays 覆盖 swap path**.

### 2.3 next fix_repeat 目标

- 扩展 coverage 从 3 → 5-7 arrays (offset -3..+3)
- 重跑 quote smoke; 预期 4/4 success
- 如果仍 2/4: 考虑 pool 1 太 wide; 文档化; 选 paid_rpc_setup 备选

## 3. 进步 (V4 → V5)

| metric | V4 | V5 | delta |
|---|---|---|---|
| bin array PDA derivation | 0/2 (V4 only attempted via getBinArrayForSwap) | 6/6 (pure PDA, no RPC) | **new artifact** |
| single-account getAccountInfo | not attempted | **6/6 success on public RPC** | **V4 blocker bypassed** |
| small-batch getMultipleAccounts | not attempted | not needed (single-account works) | (skipped) |
| bin liquidity decode | 0/2 | 420 bins | **decode works** |
| quote smoke | 0/4 | **2/4** | **V1-V4 全部 0%**; V5 首次成功 |
| paid_rpc_required | yes (claimed without trying) | **partial** (single-account works for read; coverage fix for full quote) | **revised** |

## 4. 风险 (per spec 边界)

- next fix_repeat risk: extending coverage to 5-7 arrays adds 2-4 more RPC calls per pool; still public RPC; should be fine
- 池 1 真实 liquidity 可能不集中在 active bin 周围; 即便 7 arrays 也可能 quote 仍 blocked; 仍需 paid RPC
- paid_rpc_setup 仍是一阶段备选 (Phase 2B)

## 5. 不在本阶段做

- ❌ 不实现 production connector
- ❌ 不接 wallet / 不读 keypair
- ❌ 不构造 transaction
- ❌ 不 paid RPC call
- ❌ 不 fake quote success
- ❌ 不修改 EVM executor v2

## 6. 安全断言

```text
this_stage_only_decision       = true
solana_wallet_or_keypair_touched = false
can_run_probe_now              = false
v2_line_count_unchanged        = true (992)
```

## 7. 操作员后续

- 默认下一阶段 = `LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT`（无需操作员声明）
- 关键 input 需求（建议下个 prompt 提供）:
  1. (默认) **同意扩展 coverage 3 → 7 arrays** (next fix_repeat 第一步, 仍 public RPC)
  2. (若 7 arrays 仍 2/4) **paid RPC 决策** (Phase 2B; Helius / Triton / QuickNode)
  3. (optional) **known pool feed 扩展** (5-10 pools; 仍公共 RPC; 验证 1-pool 1-quote)
  4. (optional) **Raydium CPMM 真 mainnet pid** (P2)
- 不建议直接进 EV preview (quote 2/4 仍 partial)
- 不建议 STOP (2/4 quote + 6/6 bin array + 420 bins decode = 显著进步)
- 即便选 fix_repeat, **仍需**新一轮 prompt 显式确认; 本阶段**未**自动做这件事.
