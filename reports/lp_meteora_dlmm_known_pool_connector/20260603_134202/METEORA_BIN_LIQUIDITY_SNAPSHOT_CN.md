# Meteora Bin Liquidity Snapshot Attempt — Stage G

- stage: `LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1`
- run_id: `20260603_134202`

## 0. 关键结果

```text
pools_attempted              = 2
bin_array_success_count      = 0
bin_array_failed_count       = 2
blocker                      = 403 Forbidden on public RPC (getBinArrayForSwap)
sdk_method                   = dlmmPool.getBinArrayForSwap(swapForY=true, count=1)
no_data_fabricated           = true
```

## 1. Per-pool 结果

### 1.1 Pool 1: `5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF`

| field | value | notes |
|---|---|---|
| active_bin_id | -12248 | from `lbPair.activeId` |
| bin_array_attempted | true | — |
| bin_array_success | **false** | blocked |
| bin_count | 0 | no data |
| total_x_amount | (not available) | — |
| total_y_amount | (not available) | — |
| blocker | `403 Forbidden: blocked parameter: params.0.#` | public RPC (publicnode) restricts `getMultipleAccounts` for many accounts |
| rpc_error_type | rpc_403_forbidden | — |
| confidence | 0.0 | blocked |
| latency_ms | (logged in connector_output/run.log) | — |

### 1.2 Pool 2: `9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad`

| field | value | notes |
|---|---|---|
| active_bin_id | -236 | — |
| bin_array_attempted | true | — |
| bin_array_success | **false** | blocked |
| bin_count | 0 | — |
| total_x_amount | (not available) | — |
| total_y_amount | (not available) | — |
| blocker | `403 Forbidden: blocked parameter: params.0.#` | same as pool 1 |
| rpc_error_type | rpc_403_forbidden | — |
| confidence | 0.0 | — |
| latency_ms | (logged) | — |

## 2. 根因 (per spec "如果 SDK 调用失败，必须给 root cause")

`dlmmPool.getBinArrayForSwap(swapForY, count)` 内部:
1. 读 `lbPair.binArrayBitmap` (16 个 u64, 128 bits) 找 next bin array with liquidity
2. 派生 bin array PDA(s) from `(pairAddress, binArrayIndex)`
3. 调 `chunkedGetMultipleAccountInfos(connection, binArrayPubkeys)` 拉多个 bin array accounts

第 3 步是**blocker**: public RPC (publicnode) 对 `getMultipleAccounts` with many accounts 返回 403. mainnet-beta 对同样调用返回 410 "disabled". 这是 public RPC 限制, **不是** SDK bug, **不是** pool missing.

## 3. 候选 fix (per spec "如果需要 fix 路径，明确写")

| 解 | 描述 | 状态 |
|---|---|---|
| paid RPC (Helius / Triton / QuickNode) | higher rate limit + larger response | needs operator key |
| known bin array index | 预计算 binArrayIndex 后直接调 `getMultipleAccounts` with single pubkey | needs operator input |
| Solana getProgramAccounts with paid RPC | back to GPA path | needs paid RPC |
| smaller swap (single bin) | 不调 getBinArrayForSwap; 手动 derive active bin | theoretical; SDK API not directly support |

## 4. 不在本阶段做

- ❌ 不 instantiate Keypair
- ❌ 不调用 pos-create / tx-builder
- ❌ 不 paid RPC (无 key)
- ❌ 不 webfetch
- ❌ 不 fake data (V4 honest finding: bin_count=0; total_x/y=null; blocker=403)
- ❌ 不修改 EVM executor v2

## 5. 安全断言

```text
bin_liquidity_attempted    = true
no_data_fabricated         = true
solana_wallet_or_keypair_touched = false
transaction_sent          = false
can_run_probe_now         = false
v2_line_count_unchanged   = true (992)
```

## 6. 下一阶段

进入 Stage H — quote snapshot attempt: 用 SDK swapQuote (read-only); 预期同样被 bin_arrays 阻断, 记录 blocker.
