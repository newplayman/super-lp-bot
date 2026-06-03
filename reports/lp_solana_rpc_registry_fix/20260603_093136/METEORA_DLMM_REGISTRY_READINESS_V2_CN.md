# Meteora DLMM Registry Readiness v2 — Stage G

- stage: `LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V1`
- run_id: `20260603_093136`

## 0. 5 必答问题（与上一轮对比）

| question | v1 (上一轮) | v2 (本轮) |
|---|---|---|
| Q1 program_id_officially_sourced | ❌ (unknown) | ✅ (docs.meteora.ag) |
| Q2 program_verified_onchain | ❌ | ✅ (executable=true; BPFLoaderUpgradeable; data_len=48) |
| Q3 gpa_smoke_feasible | ❌ (no pid) | ⚠️ (path verified; but 9s timeout on public RPC) |
| Q4 sdk_or_api_path_available | partial (design) | partial (design) — Meteora SDK exists; Meteora DLMM API exists at dlmm-api.meteora.ag; not yet wired in v1 |
| Q5 ready_for_readonly_connector | ❌ | ⚠️ (3/4 verified; GPA 边界 timeout) |
| next_connector_blocker | pid missing + GPA not run | **GPA 不能在公共 RPC 跑** (dataSlice 0 仍 8-9s; bigger response would be 100% timeout); SDK/API 未 wire |

## 1. Q1 详细: program_id_officially_sourced

- **YES** (per Stage C official source discovery)
- **Source URL**: `https://docs.meteora.ag/core-products/dlmm`
- **Source Type**: `oficial_docs` (Level A)
- **Source Confidence**: **high**
- **Source Fetch Success**: yes
- **Source Excerpt (短)**: docs.meteora.ag/core-products/dlmm page returned the program id directly
- **Program ID**: `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo`
- **Confidence**: 0.95 (Level A; single source but high-quality)

## 2. Q2 详细: program_verified_onchain

- **YES** (per Stage E on-chain verifier)
- **Method**: `getAccountInfo` on `https://solana.publicnode.com` (primary) and `https://api.mainnet-beta.solana.com` (secondary)
- **Retry**: 2 attempts (initial + 1 retry) with 0.5s backoff
- **Result**:
  - `account_exists`: ✅
  - `executable`: ✅
  - `owner`: `BPFLoaderUpgradeab1e11111111111111111111111` (BPF Loader Upgradeable)
  - `data_len`: 48 (binary programdata header)
  - `lamports`: 9400580 (≈ 0.0094 SOL rent)
  - `verification_status`: **verified**
  - `confidence`: 0.95

## 3. Q3 详细: gpa_smoke_feasible

- **PATH verified**: GPA endpoint itself works (System Program sanity check passed in earlier stage)
- **Meteora DLMM GPA on public RPC**: ❌ **timeout** (9.2s) — `TimeoutError('The read operation timed out')`
- 即使 `dataSlice: 0,0` (0 bytes), response body 包含 account 数量 metadata; public RPCs 慢/不稳定
- **Implication**: 在**公共 RPC** 上 GPA 对 Meteora DLMM **不**可行
- **Possible fixes (NOT this stage)**:
  - **paid RPC** (Helius, Triton, QuickNode): higher rate limit + larger response
  - **Meteora DLMM API** at `https://dlmm-api.meteora.ag` (provides pool list via REST; SPEC 设计阶段已 documented)
  - **subset GPA** with dataSlice + memcmp filter (would need exact offsets; not v1)
- **Confidence**: 0.3 (path works; smoke fails on public RPC)

## 4. Q4 详细: sdk_or_api_path_available

- **Meteora SDK exists** (TypeScript `@meteora-ag/dlmm`; upstream design 提到)
- **Meteora DLMM API** at `https://dlmm-api.meteora.ag` (公开 HTTP GET; upstream design 提到)
- **但**: 本阶段**没有**实际 wire SDK or call API (设计阶段)
- **Confidence**: 0.5 (设计 ready; **未**实证)
- **Implication**: connector 阶段需要先 wire SDK or API

## 5. Q5 详细: ready_for_readonly_connector

**部分 ready** — 5 项中 2 项 verified; GPA 失败 1 项; SDK/API 未 wire 1 项; 1 项 not started

| sub_condition | status | confidence |
|---|---|---|
| program_id_officially_sourced | ✅ | 0.95 |
| program_verified_onchain | ✅ | 0.95 |
| gpa_smoke_feasible (public RPC) | ❌ | 0.3 |
| sdk_or_api_path_available (designed only, not wired) | ⚠️ | 0.5 |
| overall | ⚠️ | **0.5 (avg of 0.95+0.95+0.3+0.5 = 2.7/4)** |

→ **NOT ready for LP_METEORA_DLMM_READONLY_CONNECTOR_V1** in this round (because GPA fails on public RPC).

## 6. next_connector_blocker

1. **GPA 不可行 on public RPC** — 必须切换到 paid RPC 或 indexer/API path
2. **SDK / API path 未 wire** — connector 阶段需要 wire Meteora SDK or DLMM API

## 7. 备选 next stage 决策

- 如果选 `LP_METEORA_DLMM_READONLY_CONNECTOR_V1`:
  - 必须解决 GPA 障碍 (选 paid RPC or indexer)
  - 必须 wire Meteora SDK
  - connector 阶段会引入 cost & complexity
- 如果选 `LP_SOLANA_RPC_REGISTRY_FIX_REPEAT`:
  - 重新尝试 Raydium CPMM pid (在 mainnet 上找不到; 用 raydium-amm-v3 or docs)
  - 不解决 GPA 障碍
- 真实情况: **Meteora DLMM 这 4 个** verified pids + 4 个 chain 的 readiness v2 评估**只有 GPA 障碍**。这是个 data source 限制，**不是** registry 或 SDK 限制。
- **next stage recommendation**: `LP_METEORA_DLMM_READONLY_CONNECTOR_V1` (低风险入口; 但**必须先** select paid RPC or indexer)

## 8. 安全断言

```text
meteora_dlmm_registry_ready_v2   = ⚠️ partial (program verified, but GPA blocked on public RPC)
program_id_officially_sourced    = true
program_verified_onchain         = true
gpa_smoke_feasible_public_rpc    = false
sdk_or_api_path_available        = partial_design
solana_wallet_or_keypair_touched = false
can_run_probe_now                = false
```
