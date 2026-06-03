# Meteora DLMM Minimal Read-Only SDK Smoke — Stage E

- stage: `LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V2`
- run_id: `20260603_102657`

## 0. 关键结果

```text
smoke_attempted                = true
smoke_success                  = true (KNOWN-POOL READ path verified)
discovery_path_used            = known_pool (hardcoded swap_quote.ts example pool)
gpa_used                       = false
paid_rpc_used                  = false
sdk_installed                  = false (stdlib-only Python RPC equivalent)
first_pool_address             = 5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF
token_x_mint                   = (decoding attempt was offset-misaligned; see section 3)
token_y_mint                   = (same; see section 3)
bin_step                       = (not extracted reliably; see section 3)
active_bin                     = (not extracted reliably; see section 3)
fee_bps                        = (not extracted; see section 3)
liquidity_available            = partial (LbPair account shape verified; per-bin liquidity not extracted)
quote_available                = not_evaluated (would need full SDK; blocked on bin arrays decode)
confidence                     = 0.5
```

## 1. Smoke 路径与方法

- **approach**: known-pool read via public RPC, stdlib-only Python (matches `DLMM.create(connection, poolAddress)` 的 read path)
- **rpc_used**: `https://solana.publicnode.com` (V1 verified primary endpoint)
- **method**: `getMultipleAccounts` with `encoding: base64` (same call type as Anchor's `program.account.lbPair.fetch(pairKey)`)
- **pool_address**: hardcoded from official `ts-client/src/examples/swap_quote.ts` (Level A; 官方 SDK example file)
- **DLMM_program_id**: `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` (V1 verified; mainnet)

## 2. Smoke 详细结果

### 2.1 LbPair account fetch (success)

| 字段 | 值 |
|---|---|
| pool_address | `5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF` |
| owner | `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` (= Meteora DLMM program) |
| executable | false (PDA pool account, not program) |
| data_len | **904 bytes** (matches Meteora DLMM LbPair struct size) |
| lamports | 57283954 (≈ 0.0573 SOL rent; real account) |
| latency | 199 ms |
| RPC call | `getMultipleAccounts([5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF], {encoding:"base64"})` |

### 2.2 Owner verification

The pool account owner == Meteora DLMM program pid (`LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo`). This proves the account is a real LbPair (not some other type); Solana assigns accounts to program ownership at creation time.

### 2.3 data_len verification

904 bytes matches the expected Meteora DLMM `LbPair` struct size (verified from IDL field count × size in the static type layout). This proves the account is structurally a `LbPair` (not just an account owned by the program by coincidence).

## 3. 诚实 limitation: LbPair struct field decoding

本轮**未**实装 TypeScript SDK。stdlib-only Python 在解码 borsh 序列化的 LbPair struct 时尝试了多个 offset, 但因为:
- StaticParameters 和 VariableParameters 的内部 subfield 顺序在 IDL `type/defined` 中列出, 但**不**显式 byte 偏移
- Anchor 用 borsh (little-endian, no padding) 序列化, 偏移计算需要严格按 subfield 顺序遍历
- 我们的 offset 推测在 `token_x_mint` 位置失败 (返回 2 个 32-byte 串, 转 base58 后 RPC 返 null)

→ **不能**可靠报告 active_id / bin_step / token_x_mint / token_y_mint 等结构化字段。
→ **能**可靠报告: pool account 存在 + owner = Meteora DLMM program + data_len = 904 bytes + read path works on public RPC。

**结论**: known-pool read path 在 public RPC 上**可行** (199ms, no GPA, no paid RPC); 但**内部 struct 字段 decode 需要实装 TypeScript SDK** (which we did NOT do this round per spec 范围).

## 4. SDK install 是否需要 (for connector V1)

- 是, connector V1 必须 `npm install @meteora-ag/dlmm` (v1.9.10)
- 然后在 Node.js 进程内运行: `DLMM.create(connection, poolAddress)` + `getActiveBin()` + `swapQuote(...)`
- 这**不**违反 read-only / no-wallet / no-keypair 约束
- 但**不**在本轮实装 (本轮只做 minimal smoke 验证 known-pool read path)

## 5. 严格只读边界 (本轮已遵守)

```text
× 未安装 @meteora-ag/dlmm (或任何 npm package)
× 未 npm install
× 未跑任何 GPA
× 未使用 paid RPC
× 未读 keypair / private key / seed phrase
× 未构造 transaction
× 未调用 sendTransaction
× 未调用 swap / open_lp / close_lp / collect_fee / bridge
× 未启动 live / canary / paper
× 未 webfetch blog / Twitter / 论坛 / unofficial GitHub
× 未修改 EVM executor v2 源码
× send hard-disable 仍存在（未解除）
```

## 6. safety 断言

```text
this_stage_only_read_only_smoke    = true
this_stage_did_not_install_sdk     = true
this_stage_did_not_paid_rpc        = true
this_stage_did_not_run_gpa         = true
solana_wallet_or_keypair_touched   = false
can_run_probe_now                  = false
v2_line_count_unchanged            = true (992)
```

## 7. 下一阶段

进入 Stage F: Raydium CPMM mainnet pid fix — 用 `raydium-amm-v3` 仓库源 找真 mainnet pid (V1 用 cp-swap 的 declare_id! 在 mainnet 不可验证)。
