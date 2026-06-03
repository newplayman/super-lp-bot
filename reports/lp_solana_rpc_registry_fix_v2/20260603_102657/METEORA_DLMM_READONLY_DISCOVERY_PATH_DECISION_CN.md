# Meteora DLMM Read-Only Discovery Path Decision — Stage D

- stage: `LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V2`
- run_id: `20260603_102657`

## 0. 决策

```text
recommended_discovery_path = paid_rpc_gpa
default_when_no_explicit_choice = paid_rpc_gpa
connector_ready_if_path_available = no   (still requires paid RPC decision from operator)
fallback_path = official_sdk_api   (used for known pool decode + quote; NOT for discovery)
```

## 1. 三条路径评估

### Path 1: public_rpc_gpa

- **V1 结果**: 0/4 success
  - Meteora DLMM: timeout 9.2s (TimeoutError)
  - Meteora DAMM v2: timeout 8.1s
  - Orca Whirlpools: json-rpc -32010 (program too large)
  - Raydium CLMM: HTTP 429 (rate limit)
- **改善可能**:
  - 增 timeout 不行 (V1 已 8s; public RPCs 在大 programs 维持 8s+ timeout)
  - dataSlice 已 0 bytes; 进一步无意义
  - 公共 RPC 限 5MB response; AMM 池数千到数万, 超 5MB
- **decision**: **not_feasible** — 0/4 V1 evidence 明确
- **operator_action_required**: NO (公共 RPC 注定不可行; 不再尝试)

### Path 2: paid_rpc_gpa

- **provider options**: Helius / Triton / QuickNode (per upstream design doc)
- **rate_limit & response_size**:
  - Helius free tier: 50 req/s, no GPA size cap mentioned
  - Helius paid (developer): higher rate, ~10MB response cap
  - Triton / QuickNode: 同样有 paid tier
- **Meteora DLMM 池数**: 估算 < 5000 (从 mainnet 实际看 ~2000 活跃 LbPair accounts)
  - 每个 LbPair account ≈ 904 bytes (LbPair struct size)
  - Total ≈ 1.8 MB raw + bin array bitmap extension
  - 在 paid RPC 5-10MB cap 范围内
- **可行性**: **likely_feasible**
- **blocker**: operator 必须提供 paid RPC URL + key (本轮**无** key)
- **decision**: **recommended** — 一旦 operator 提供 paid RPC, GPA 应能返回所有 LbPair accounts
- **operator_action_required**: **YES** — paid RPC URL 决策

### Path 3: official_sdk_api

- **SDK path**:
  - `DLMM.create(connection, poolAddress)` — 已知 pool address; read-only
  - `dlmmPool.getActiveBin()`, `getBinArrayForSwap()`, `swapQuote()`, `getLbPairLockInfo()` — 已知 pool; read-only
  - `DLMM.getLbPairs(connection, opt?)` — pool list; **本质** GPA (走 `program.account.lbPair.all()`)
- **API path**:
  - `dlmm-api.meteora.ag` 全部路径 404 — **not_available**
- **SDK 是否可绕过 GPA**:
  - **NO** for discovery (getLbPairs 内部用 GPA)
  - **YES** for decode/quote (已知 pool address)
- **decision**: **partial_path** — 适合已知 pool feed (cache / static list / indexer) 注入; 不适合首次 discovery
- **operator_action_required**: NO for SDK install; 但需 (a) 已知 pool list feed, 或 (b) 接受 paid RPC

## 2. 三条路径综合

| path | bypass_public_rpc_gpa | needs_operator_action | feasibility | discovery_capable | decode_quote_capable |
|---|---|---|---|---|---|
| public_rpc_gpa | n/a (is public) | no | **not_feasible** (V1 evidence) | yes (but timeout) | n/a |
| paid_rpc_gpa | yes | **yes** (paid RPC URL) | **likely_feasible** | yes | n/a |
| official_sdk_api | partial | no (SDK install) | partial | no (still needs GPA) | yes (known pool) |

## 3. 推荐组合 (Stage E 范围)

**主路径**: `paid_rpc_gpa` for first-time discovery
**后处理**: 落盘 pool_addresses list; 之后可用 `official_sdk_api` (DLMM.create + helpers) 持续读链上元数据, **不再**依赖 GPA

**含义**:
- Stage E (minimal smoke) **不**能跑 full discovery (无 paid RPC)
- Stage E 可跑 known-pool 路径 (1 个 hardcoded test pool) — 验证 SDK wire + decode 流程
- Connector stage 需要 operator 提供 paid RPC URL 才能做 full discovery

## 4. connector_ready_if_path_available 决策

- **public_rpc_gpa** 不可用 → connector not ready on this path
- **paid_rpc_gpa** 路径明确, 但**无 key** → connector not ready until operator supplies paid RPC
- **official_sdk_api** 部分可用, 但**仍需** pool list feed

→ `connector_ready_if_path_available = no` (在 operator 提供 paid RPC 之前)

## 5. 下一阶段依赖

- **Stage E (minimal smoke)**:
  - 如果 path 选 paid_rpc_gpa: 没 key, **不能**跑 → 改 known-pool test (用 hardcoded 1 个 Meteora DLMM pool address, 仅 SDK 读链上元数据)
  - 这是 read-only smoke, 验证 SDK wire + decode 可行性
  - **不**尝试 GPA (无 paid RPC)
  - **不**假设 paid RPC 存在

## 6. 不在本阶段做

- ❌ 不实装 paid RPC (无 key)
- ❌ 不实装 SDK (Stage E 决定)
- ❌ 不跑 smoke (Stage E 才做)
- ❌ 不接 wallet / 不读 keypair
- ❌ 不构造 transaction

## 7. 安全断言

```text
this_stage_only_decision           = true
this_stage_did_not_paid_rpc_call   = true   (无 paid RPC key)
this_stage_did_not_install_sdk     = true
solana_wallet_or_keypair_touched   = false
can_run_probe_now                  = false
```

## 8. 操作员后续

- 默认下一阶段 = `LP_SOLANA_RPC_REGISTRY_FIX_REPEAT`（如本轮 SDK smoke 失败）
- 如 Stage E minimal smoke (known-pool 路径) **成功**, 下一阶段可考虑 `LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT` 或 `LP_METEORA_DLMM_READONLY_CONNECTOR_V1` (后者需 paid RPC)
- 关键 input 需求 (建议下个 prompt 提供):
  1. **paid RPC 决策**: 选 Helius / Triton / QuickNode; 或 维持 public only + known-pool feed
  2. (optional) **是否同意 connector stage 直接 wire SDK + 选 paid RPC in one stage** (而非再 fix_repeat)
  3. (optional) **是否提供 known-pool list feed** (静态 JSON / indexer subscription), 让 connector 跳 GPA
- 不建议直接 connector 除非 (a) paid RPC 已就绪 或 (b) known-pool feed 已定义
