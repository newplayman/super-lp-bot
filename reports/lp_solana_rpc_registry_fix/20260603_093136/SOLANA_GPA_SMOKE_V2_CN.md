# Solana Bounded GPA Smoke v2 — Stage F

- stage: `LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V1`
- run_id: `20260603_093136`

## 0. 关键结果

```text
gpa_attempted_count = 4  (only 4 verified pids attempted; CPMM/Lifinity skipped)
gpa_success_count   = 0
```

## 1. 4 协议 GPA smoke 详细

| protocol | gpa_attempted | gpa_success | rpc_error_type | rate_limit | latency_ms | needs_paid_rpc | discovery_feasible | confidence |
|---|---|---|---|---|---|---|---|---|
| Meteora DLMM | ✅ | ❌ | `TimeoutError('The read operation timed out')` | no | 9187 | likely | unknown | 0.3 |
| Meteora DAMM v2 | ✅ | ❌ | `TimeoutError('The read operation timed out')` | no | 8071 | likely | unknown | 0.3 |
| Orca Whirlpools | ✅ | ❌ | `{"code": -32010, "message": "whirLbMiicVdio4qvUfM5KAg6Ct8Vwp..."}` | no | 484 | likely | unknown | 0.3 |
| Raydium CLMM | ✅ | ❌ | `<HTTPError 429: 'Too Many Requests'>` | **yes** | 348 | **yes** | unknown | 0.3 |
| Raydium CPMM | (skipped) | n/a | n/a | n/a | 0 | n/a | no | 0.0 |
| Lifinity | (skipped) | n/a | n/a | n/a | 0 | n/a | no | 0.0 |

## 2. 关键发现

### 2.1 GPA 在公共 RPC 上**不可用** (本轮)

- **Meteora DLMM/DAMM v2** (2 protocols): 8-9s timeout (dataSlice 0 bytes only returns counts; but RPCs themselves timed out)
- **Orca Whirlpools**: Solana JSON-RPC error `-32010` (typical for programs with too many accounts; Solana RPC has a hard cap on `getProgramAccounts` response size — ~5MB)
- **Raydium CLMM**: HTTP 429 (rate limit on public RPC)

→ **公共 RPC 上 GPA 不适用于主流 AMM 池**。spec 严格禁止 unbounded scan，且本阶段只能 bounded (`dataSlice: 0,0`)，所以只能验证 "RPC 是否能响应 GPA"，**不能**做实际 pool discovery。

### 2.2 影响

- 0/4 GPA smoke 成功 → **discovery_feasible 仍 unknown**
- 下游 connector 阶段需要：
  - **paid RPC** (Helius / Triton / QuickNode 都有 higher rate limit + larger response)
  - **或** indexer (Meteora DLMM API / Raydium API)
  - **或** 仅依赖 SDK/program-derived (无 GPA; e.g. Meteora DLMM 已知 pair list from API)

## 3. spec 一致性

- ✅ **bounded** (dataSlice 0,0)
- ✅ **timeout 8s**
- ✅ **no unbounded scan**
- ✅ **no retry on rate limit** (记录 rate_limit_seen=yes)
- ✅ **每个协议只 smoke 一次**

## 4. 不在本阶段做

- ❌ 不 unbounded GPA
- ❌ 不 retry on rate limit
- ❌ 不 paid RPC
- ❌ 不 webfetch indexer
- ❌ 不接 wallet

## 5. 安全断言

```text
this_stage_only_gpa_smoke         = true  (bounded)
this_stage_did_not_run_unbounded = true
this_stage_did_not_load_keypair  = true
solana_wallet_or_keypair_touched = false
can_run_probe_now                = false
```

## 6. 下一阶段

Stage G (Meteora DLMM readiness v2) + Stage H (P1/P2 readiness v2) — 重新评估 readiness with：
- 4 verified pids (Meteora DLMM, DAMM v2, Orca, Raydium CLMM)
- 1 not_found (Raydium CPMM)
- 1 unknown (Lifinity)
- GPA 不可用作为 1 个 "needs paid RPC" 标记
- SDK/API 作为 alternate path

readiness v2 仍**可能不**满足 LP_METEORA_DLMM_READONLY_CONNECTOR_V1 的 4/4 conditions (因为 GPA 失败)；最终 stage I 决定。
