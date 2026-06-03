# Meteora Known-Pool Connector Next-Stage Decision — Stage J

- stage: `LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1`
- run_id: `20260603_134202`

## 0. 决策

```text
recommended_next_stage = LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT
default_when_no_explicit_choice = LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT
```

## 1. 5 选项评估

| next stage | 触发条件 | 是否触发 |
|---|---|---|
| `LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT` | pool snapshot works + fee snapshot works + bin/quote blocked but fixable | **✅ 触发** (V4 connector 2/2 + 2/2; bin/quote blocked on public RPC, but single-account `getMultipleAccountsInfo` + computed binArrayIndex might bypass; fix_repeat round can verify) |
| `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1` | quote snapshot works + fee/bin data enough | ❌ (quote 0/4; bin 0/2; EV 缺数据) |
| `LP_SOLANA_PAID_RPC_SETUP_REQUIRED` | public RPC blocks bin array / quote and no workaround | ❌ (single-account path 没试; 试之前不要选 paid_rpc_setup) |
| `LP_METEORA_DLMM_KNOWN_POOL_CONNECTOR_FIX_REPEAT` | connector implementation has bugs | ❌ (connector V1 工作; 2/2 pools decoded; 2/2 fee extracted; bin/quote 阻断是 RPC 不是 connector bug) |
| `STOP_LP_RESEARCH_NOW` | no safe read-only connector path | ❌ (read-only path 完全可行; 3/6 tables ready; 2/2 pools decoded) |

## 2. entry conditions for LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1 (本轮; 全部满足)

| condition | V4 状态 |
|---|---|
| known_pool_connector_built | ✅ (scripts/lp_meteora_dlmm_known_pool_connector_v1_readonly.js) |
| known_pool_count | 2 |
| pool_snapshot_success_count | 2 |
| fee_snapshot_success_count | 2 |
| bin_liquidity_snapshot_success_count | 0 (blocked) |
| quote_snapshot_success_count | 0 (blocked) |
| connector_readonly_ready | true (3/6 tables) |
| quote_ready | false |
| needs_paid_rpc | true (for unblocking bin + quote) |

→ Connector V1 本轮完成. **下一阶段不是 connector V1 自身, 而是 quote/binarray fix**.

## 3. 进步 (V3 → V4)

| metric | V3 (FEASIBILITY) | V4 (CONNECTOR V1) | delta |
|---|---|---|---|
| connector script | single-use smoke | **reusable** (--mode snapshot/quote-smoke/all) | **new artifact** |
| pool_snapshot | 2/2 single-use | **2/2 via connector V1**; CSV/JSON | repeatable |
| fee_snapshot | embedded in smoke | **standalone** CSV/JSON | repeatable |
| bin_liquidity | 0/2 smoke | **0/2 via connector V1**; honest blocker | documented |
| quote | 0/4 smoke | **0/4 via connector V1**; honest blocker | documented |
| readiness matrix | schema design only | **6 tables judged** (3 ready / 2 blocked / 1 blocked_missing) | **new artifact** |

## 4. risk (per spec 边界)

- 下一阶段 (QUOTE_BINARRAY_FIX_REPEAT) risk: single-account `getMultipleAccountsInfo` 在 public RPC 上也可能被 403 (同一 restriction); 试之前不能保证 work
- 若 single-account path 也 fail, 下一轮 fix_repeat **必须** 选 `LP_SOLANA_PAID_RPC_SETUP_REQUIRED` 或停于此
- connector V1 已固化; quote / EV 阻隔是 public RPC 限制, **不是** connector 设计问题

## 5. 不在本阶段做

- ❌ 不实现任何 production connector
- ❌ 不接 wallet / 不读 keypair
- ❌ 不构造 transaction
- ❌ 不 paid RPC call
- ❌ 不 fake quote / bin_liquidity
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
  1. **是否同意 single-account bin array path 试一次**（next fix_repeat 第一步）
  2. (若 single-account path 失败) **paid RPC 决策** (Phase 2B; Helius / Triton / QuickNode)
  3. (optional) **known pool feed 扩展** (5-10 pools; 仍走公共 RPC)
  4. (optional) **Raydium CPMM 真 mainnet pid** (P2; 不在 Meteora DLMM critical path)
- 不建议改选 EV preview (quote 缺数据)
- 不建议 STOP (3/6 tables ready; 2/2 pools decoded; connector V1 工作)
- 即便选 fix_repeat, **仍需**新一轮 prompt 显式确认; 本阶段**未**自动做这件事.
