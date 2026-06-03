# Meteora DLMM SDK / API Source Discovery — Stage C

- stage: `LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V2`
- run_id: `20260603_102657`

## 0. 关键结论

| 项 | 结果 |
|---|---|
| 官方 npm package 名称 | `@meteora-ag/dlmm` (v1.9.10) |
| 官方 GitHub 仓库 | `MeteoraAg/dlmm-sdk` (Level A) |
| 官方 SDK 默认导出 | `DLMM` class |
| 官方 REST API endpoint (`dlmm-api.meteora.ag`) | **404 on all paths** (无公共 REST API) |
| SDK 是否绕过 public RPC GPA | **NO** — `getLbPairs()` 内部即 `program.account.lbPair.all()` (= GPA) |
| 已知 pool address + SDK 读链上元数据 | **YES** (read-only: `DLMM.create` + `getActiveBin` + `getBinArrayForSwap` + `swapQuote`) |
| 是否可作为 connector V1 的"discovery 替代" | **NO** — SDK 不替代 GPA；必须已知 pool address 才能用 SDK |

## 1. 官方 source 详情

### 1.1 npm package

- **package**: `@meteora-ag/dlmm`
- **version**: 1.9.10 (checked at 20260603_102657)
- **source**: `https://raw.githubusercontent.com/MeteoraAg/dlmm-sdk/main/ts-client/package.json`
- **main**: `./dist/index.js`
- **types**: `./dist/index.d.ts`
- **source_confidence**: high (Level A; 官方 GitHub raw 仓库)
- **fetch_success**: yes

### 1.2 GitHub repository

- **repo**: `https://github.com/MeteoraAg/dlmm-sdk`
- **path**: `ts-client/` (TypeScript client)
- **source_url**: `https://raw.githubusercontent.com/MeteoraAg/dlmm-sdk/main/ts-client/src/index.ts`
- **fetch_success**: yes
- **source_confidence**: high (Level A; 官方 org/repo)

### 1.3 SDK entry / exports

```ts
// ts-client/src/index.ts
import { DLMM } from "./dlmm";
export default DLMM;
export * from "./dlmm/helpers";
export * from "./dlmm/types";
export * from "./dlmm/error";
export * from "./dlmm/constants";
export * from "./dlmm/idl/idl";
export { default as IDL } from "./dlmm/idl/idl.json";
export * from "./dlmm/helpers/accountFilters";
```

### 1.4 官方 REST API (dlmm-api.meteora.ag)

| 探测路径 | HTTP |
|---|---|
| `/pair/all` | 404 |
| `/pairs` | 404 |
| `/lb_pairs` | 404 |
| `/v1/pair/all` | 404 |
| `/v1/pairs` | 404 |
| `/v1/pair/all_by_groups` | 404 |
| `/health` | 404 |
| `/info` | 404 |
| `/swagger.json` | 404 |
| `/openapi.json` | 404 |
| `/docs` | 404 |
| `/` | 404 |

**结论**: `dlmm-api.meteora.ag` host 存在但**不**提供公共 REST API (所有路径 404)。
**spec 决策**: 标记 `api_endpoint: none_found`；**不**使用任何第三方 Meteora API。

### 1.5 SDK helpers — read-only (已知 pool address)

源码: `ts-client/src/dlmm/index.ts` + `ts-client/src/dlmm/helpers/`

| helper | 用途 | 是否只读 | 是否需要 GPA |
|---|---|---|---|
| `DLMM.create(connection, dlmm: PublicKey)` | 构造一个 DLMM 实例: 拉 account + bin array bitmap extension + clock; 解码 LbPair + tokenX/Y + reserves + rewards | **YES** (read-only) | NO (用 `getMultipleAccountsInfo` 拉 3 个具体账户) |
| `dlmmPool.getActiveBin()` | 返回 active bin (binId, price, xAmount, yAmount) | **YES** | NO |
| `dlmmPool.getBinArrayForSwap(swapYtoX)` | 找到 swap 路径所需 bin arrays | **YES** | NO (派生地址 + `getMultipleAccountsInfo`) |
| `dlmmPool.swapQuote(...)` | 算 swap quote (consumedInAmount, outAmount) | **YES** | NO (本地计算) |
| `dlmmPool.getLbPairLockInfo()` | 拉 lock info (lockedBy, lockEndTs, ...) | **YES** | NO |
| `dlmmPool.getFeeInfo()` / `dlmmPool.calculateFeeInfo(...)` | 读 fee params (baseFeeBps, maxFeeBps, protocolFeeBps) | **YES** | NO |
| `DLMM.getLbPairs(connection, opt?)` | **list all LbPair accounts** (= GPA) | YES but calls GPA | **YES (GPA)** |
| `DLMM.getPairPubkeyIfExists(...)` | 派生地址 + 查 account | **YES** | NO |
| `DLMM.getAllPresetParameters(connection)` | 拉 preset parameters | **YES** | YES (gpa) |
| `DLMM.getAllLbPairPositionsByUser(...)` | 拉 user positions | **YES** | YES (gpa) |

**关键洞察**:
- 所有 read-only helpers (DLMM.create, getActiveBin, swapQuote, getLbPairLockInfo) 都**需要**已知 pool address。
- `getLbPairs` 是 discovery path, 但**内部**使用 `program.account.lbPair.all()` = GPA — 与本轮 V1 已证明 public RPC GPA 不可行。
- SDK 不**替代** GPA; SDK **增强**已知 pool 的读操作 (解码 / 算 quote / 找 bin arrays)。

### 1.6 SDK examples

- `ts-client/src/examples/example.ts` — initializePositionAndAddLiquidityByStrategy (写, 不在 read-only 范围)
- `ts-client/src/examples/swap_quote.ts` — **read-only quote 示例** (DLMM.create + getBinArrayForSwap + swapQuote)
- `ts-client/src/examples/fetch_lb_pair_lock_info.ts` — **read-only 拉 lock info** (DLMM.create + getLbPairLockInfo)
- `ts-client/src/examples/get_oracle.ts` — read-only oracle 拉取
- `ts-client/src/examples/initialize_bin_arrays.ts` — 写, 不在范围

read-only examples 用 known pool address + `https://api.mainnet-beta.solana.com` RPC, 验证 read-only helper 工作流可行。

### 1.7 SDK 字段覆盖矩阵

| 字段 (per spec 必答) | SDK 提供 | 备注 |
|---|---|---|
| `getLbPairs` | YES | 用 GPA |
| pool list | via `getLbPairs` | 受 GPA 限制 |
| pair account decoding | YES (`DLMM.create` 解码) | 已知 pool address |
| bin array decoding | YES (`getBinArrays` private + `getBinArrayForSwap` public) | 已知 pool + 派生地址 |
| active bin | YES (`getActiveBin`) | 已知 pool |
| fee parameters | YES (`getFeeInfo`, `calculateFeeInfo`) | 已知 pool |
| bin step | YES (`lbPair.parameters.binStep`) | 已知 pool |
| liquidity distribution | YES (`getBinArray` returns per-bin xAmount/yAmount) | 已知 pool |
| quote | YES (`swapQuote`) | 已知 pool + bin arrays |

## 2. 字段表

```json
{
  "sdk_install_needed": "yes (npm install @meteora-ag/dlmm)",
  "has_pool_discovery_method": "yes (via GPA; bounded GPA on public RPC: not feasible in V1)",
  "has_pool_decode_method": "yes (DLMM.create decodes LbPair, BinArrayBitmapExtension, tokenX/Y, reserves, rewards)",
  "has_quote_method": "yes (swapQuote)",
  "has_bin_liquidity_method": "yes (getBinArray + getActiveBin + getPriceOfBinByBinId + getBinFromBinArray)",
  "needs_paid_rpc_for_discovery": "likely (gpa on public RPC: timeout / -32010 / 429 per V1)",
  "needs_known_pool_address_for_decode": "yes (DLMM.create requires PublicKey)",
  "api_endpoint_available": "none_found (dlmm-api.meteora.ag 404 on all paths)",
  "sdk_blocker": "pool discovery still requires GPA; SDK does NOT bypass public RPC GPA"
}
```

## 3. 与 V1 readiness 对应

| V1 readiness sub-condition | V1 状态 | V2 评估 |
|---|---|---|
| Q1 program_id_officially_sourced | ✅ | ✅ (已 V1 验证) |
| Q2 program_verified_onchain | ✅ | ✅ (已 V1 验证) |
| Q3 gpa_smoke_feasible (public RPC) | ❌ | **NOT_FEASIBLE** (V1 已证; SDK 也需 GPA) |
| Q4 sdk_or_api_path_available | partial | **UPGRADED**: SDK path now identified; `dlmm-api.meteora.ag` confirmed not a public REST API |
| Q5 ready_for_readonly_connector | ❌ | 取决于 (a) 是否接受 paid RPC 用于 GPA, 或 (b) 接受 known-pool-list feed |

## 4. 不在本阶段做

- ❌ 不 webfetch 任何非官方来源 (blog / Twitter / 论坛)
- ❌ 不从模型记忆硬编码任何 program id
- ❌ 不跑链上验证 (V1 已做)
- ❌ 不接 wallet / 不读 keypair
- ❌ 不调 swap / open LP / close LP / collect fee / bridge
- ❌ 不构造 transaction
- ❌ 不实装 SDK 跑 smoke (Stage E 才做)
- ❌ 不假设 paid RPC 已就绪

## 5. 安全断言

```text
this_stage_only_source_discovery    = true
this_stage_did_not_install_sdk      = true   (只 read GitHub raw; 不 npm install)
this_stage_did_not_run_onchain      = true
this_stage_did_not_load_keypair    = true
solana_wallet_or_keypair_touched   = false
can_run_probe_now                  = false
```

## 6. 下一阶段

进入 Stage D: Meteora DLMM read-only discovery path decision — 3 条路径 (public_rpc_gpa / paid_rpc_gpa / official_sdk_api) 评估；决策 recommended_discovery_path。
