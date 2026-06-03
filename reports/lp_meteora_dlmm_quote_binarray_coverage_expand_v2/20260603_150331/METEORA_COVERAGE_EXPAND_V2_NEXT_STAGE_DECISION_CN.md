# Meteora Coverage Expand V2 Next-Stage Decision — Stage I

- stage: `LP_METEORA_DLMM_QUOTE_BINARRAY_COVERAGE_EXPAND_V2`
- run_id: `20260603_150331`

## 0. 决策

```text
recommended_next_stage = LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1
default_when_no_explicit_choice = LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1
alternative_if_paid_rpc_decision = LP_SOLANA_PAID_RPC_SETUP_REQUIRED
```

## 1. 5 选项评估

| next stage | 触发条件 | V7 状态 |
|---|---|---|
| `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1` | partial quote data enough + bin liquidity + fee | **✅ 触发** (pool 2 V6 6/6 stable; pool 1 blocked; partial EV for pool 2 only) |
| `LP_SOLANA_PAID_RPC_SETUP_REQUIRED` | public RPC cannot support enough bin array reads OR quote impossible without wider data | ✅ alternative (pool 1 has 0 bins with liquidez at 15 arrays; only paid RPC GPA can find) |
| `LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT` | coverage expansion improved but still partial | ❌ (V7 hit spec hard cap 15; cannot expand) |
| `LP_METEORA_DLMM_KNOWN_POOL_CONNECTOR_FIX_REPEAT` | connector bug | ❌ (connector V1 + expand V1 + expand V2 all work; no bug) |
| `STOP_LP_RESEARCH_NOW` | no safe read-only path | ❌ (read-only path fully working) |

## 2. 为什么选 LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1 (partial, pool 2 only)

### 2.1 满足 entry conditions

- **partial quote data enough**: pool 2 V6 6/6 stable; pool 1 no_quote_data
- **bin liquidity available**: pool 2 V6 231 bins with liquidez; pool 1 0 bins
- **fee snapshot available**: V3 fee 2/2 stable

→ partial EV possible for pool 2; pool 1 cannot compute EV.

### 2.2 per spec "pool2-only survival EV preview" exit

Per spec Stage I:
> "如果 SOL/USDC 仍失败，但 X/USDC 成功：can_enter_partial_survival_ev_preview = true; recommended_scope = pool2_only_partial_preview"

→ V7 matches this exactly. Recommended scope = pool 2 only partial EV preview.

## 3. 备选: LP_SOLANA_PAID_RPC_SETUP_REQUIRED

如果 operator 想要 2-pool EV (而非 pool 2 only), 需要:
- operator 提供 SOLANA_RPC_URL 或 LPBOT_SOLANA_RPC_URL (paid RPC key)
- 下一 stage paid_rpc_setup 重新跑 GPA, 找到 pool 1 actual liquidez
- 预期: pool 1 quote success with paid RPC

## 4. 进步 (V6 → V7)

| metric | V6 | V7 | delta |
|---|---|---|---|
| max coverage | 9 arrays | 15 arrays (spec hard cap) | 1.67x |
| SOL/USDC quote | 0/6 | 0/4 | unchanged (0/10 combined) |
| Pool 2 quote | 6/6 | (V6 stable, not re-run) | unchanged |
| bins with liquidez (pool 1) | 0/630 | 0/1260 | 0 (no liquidity in range) |
| bins with liquidez (pool 2) | 231 | (V6 stable, not re-run) | unchanged |
| single-account path | 33/42 | 18/27 (SOL/USDC) | scales |
| spec compliance | 9/9 (V6) | 15/15 (V7) | hit cap |

## 5. 风险 (per spec 边界)

- partial EV preview 风险: 只 1 池 (X/USDC); 不是 full 2-pool EV
- paid_rpc_setup 备选 风险: operator 必须显式提供 paid RPC key
- 不建议再 fix_repeat (V7 hit spec hard cap)

## 6. 不在本阶段做

- ❌ 不实现 production connector
- ❌ 不接 wallet / 不读 keypair
- ❌ 不构造 transaction
- ❌ 不 paid RPC call (无 key)
- ❌ 不 compute EV (下一阶段)
- ❌ 不修改 EVM executor v2

## 7. 安全断言

```text
this_stage_only_decision       = true
solana_wallet_or_keypair_touched = false
can_run_probe_now              = false
v2_line_count_unchanged        = true (992)
```

## 8. 操作员后续

- 默认下一阶段 = `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1` (partial, pool 2 only)
- 关键 input 需求:
  1. (默认) **接受 partial EV preview** (pool 2 only; X/USDC only; mark pool 1 as no_quote_data)
  2. (若 operator 想要 2-pool EV) **提供 paid RPC key** (Helius / Triton / QuickNode); 选 `LP_SOLANA_PAID_RPC_SETUP_REQUIRED`
  3. (可选) **扩展 known pool feed** (找更易 quote 的 Meteora DLMM 池; 但仍 public RPC)
- 不建议再 fix_repeat (V7 hit spec cap)
- 不建议 STOP (read-only path fully working; partial EV possible)
- 即便选 survival EV preview, **仍需**新一轮 prompt 显式确认; 本阶段**未**自动做这件事.
