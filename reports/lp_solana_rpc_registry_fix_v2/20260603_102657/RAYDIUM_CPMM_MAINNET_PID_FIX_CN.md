# Raydium CPMM Mainnet PID Fix — Stage F

- stage: `LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V2`
- run_id: `20260603_102657`

## 0. 关键结果

```text
candidate_pid                = CPMMoo8L3F4NbTegBCKVNungguN7H1ZpdTHKxQB5qKP1C
candidate_pid_source         = raydium-cp-swap/programs/cp-swap/src/lib.rs declare_id!  (mainnet cfg path)
mainnet_label                = yes (declared as mainnet in source; cfg(not(feature="devnet")))
devnet_label                 = yes (DRaycpLY18LhpbydsBWbVJtxpNv9oXPgjRSfpF2bWpYb)
onchain_getAccountInfo_mainnet  = null (pid NOT deployed on mainnet)
onchain_getAccountInfo_devnet   = null (devnet pid also NOT deployed)
verified                     = no
status                       = deferred (real on-chain finding; pid declared in source but not yet deployed)
does_not_block_meteora_dlmm  = true
```

## 1. V1 finding 复述

- V1 用 `raydium-cp-swap` 仓库 `lib.rs` 中 `declare_id!("CPMMoo8L3F4NbTegBCKVNungguN7H1ZpdTHKxQB5qKP1C")` 作为 mainnet pid。
- V1 跑 `getAccountInfo` 在 `https://solana.publicnode.com` 和 `https://api.mainnet-beta.solana.com` 均返 `value: null`。
- V1 结论: "cp-swap pid not on mainnet"。

## 2. V2 fix attempt 详情

### 2.1 重新核对 source 中的 pid

```rust
// https://raw.githubusercontent.com/raydium-io/raydium-cp-swap/master/programs/cp-swap/src/lib.rs
22: #[cfg(feature = "devnet")]
23: declare_id!("DRaycpLY18LhpbydsBWbVJtxpNv9oXPgjRSfpF2bWpYb");
24: #[cfg(not(feature = "devnet"))]
25: declare_id!("CPMMoo8L3F4NbTegBCKVNungguN7H1ZpdTHKxQB5qKP1C");
```

字符级别校对: V1 报告的 pid `CPMMoo8L3F4NbTegBCKVNungguN7H1ZpdTHKxQB5qKP1C` 与当前 `lib.rs` 第 25 行**完全一致** (45 字符)。
→ V1 **没有** typo; 也不是 source 已变更。

### 2.2 检查 raydium-amm-v3 仓库

`raydium-amm-v3/programs/amm/src/lib.rs` 的 `declare_id!` 宏:
```rust
24: #[cfg(feature = "devnet")]
25: declare_id!("DRayAUgENGQBKVaX8owNhgzkEDyoHTGVEGHVJT1E9pfH");  ← CLMM devnet
26: #[cfg(not(feature = "devnet"))]
27: declare_id!("CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK");  ← CLMM mainnet (= V1 verified)
```

→ `raydium-amm-v3` 是 **CLMM 仓库**, 不是 CPMM 仓库. 其 pid 与 V1 一致 (CLMM).

### 2.3 检查 raydium-sdk-v2 SDK 源码

`src/raydium/cpmm/*.ts` 中 `programId` 全部作为**参数**传入, 不硬编码 pid. 这说明 Raydium SDK v2 故意**不**在源码中固定 mainnet pid (与链上可升级的程序 design 一致).

### 2.4 检查 raydium-cp-swap README

```
README size: 1407 bytes
program id mentions: 0
```

README **不**包含任何 program id 字符串. 这是真实情况: cp-swap README 只描述 usage, 不发布 deployed pid.

### 2.5 检查 raydium 官方 docs

- `https://docs.raydium.io/raydium/protocol/developers/addresses` → 404
- `https://docs.raydium.io/raydium/protocol/overview` → 200 (1.4MB Next.js JS bundle, **不**含可机读 pid)
- WebFetch / WebSearch on official Raydium 域名 → 不可用 / API 400 errors

→ 官方 docs **不**以机器可读方式发布 CPMM pid. (Raydium 官方 docs 站点是 mintlify; 动态渲染; 抓不出 pid 字符串).

### 2.6 链上 verify (this round)

| pid | network | result | latency |
|---|---|---|---|
| `CPMMoo8L3F4NbTegBCKVNungguN7H1ZpdTHKxQB5qKP1C` (mainnet declare) | mainnet-beta | `null` (account doesn't exist) | 0.5s |
| `CPMMoo8L3F4NbTegBCKVNungguN7H1ZpdTHKxQB5qKP1C` (mainnet declare) | devnet | `null` (account doesn't exist) | n/a |
| `DRaycpLY18LhpbydsBWbVJtxpNv9oXPgjRSfpF2bWpYb` (devnet declare) | mainnet-beta | `null` (account doesn't exist) | 0.5s |
| `DRaycpLY18LhpbydsBWbVJtxpNv9oXPgjRSfpF2bWpYb` (devnet declare) | devnet | `null` (account doesn't exist) | n/a |

**关键 finding**: **两个** pid 在 mainnet **和** devnet 上**均** `null` (account 根本不存在). 这意味着 cp-swap 仓库的 `declare_id!` 写的是一个**计划中**的 pid, 但这个 pid 在公开链上**尚未**部署任何 program account.

## 3. 实情 (honest finding)

- 公开 chain 上**没有** deploy `CPMMoo8L3F4NbTegBCKVNungguN7H1ZpdTHKxQB5qKP1C` 的 BPFLoaderUpgradeable account.
- `DRaycpLY18LhpbydsBWbVJtxpNv9oXPgjRSfpF2bWpYb` 同样未 deploy.
- raydium-sdk-v2 SDK **不**在源码中固定 pid (设计选择).
- 官方 docs 不以机器可读方式发布 pid.
- 任何 "the real Raydium CPMM pid" 都需要:
  - 官方 Raydium 团队 (非模型记忆可获取)
  - 或 Solscan / Solana Explorer 上找 actual deployed program
  - 或 paid RPC 抓 getProgramAccounts + reverse-engineer (但同样需要已知 owner pid)

## 4. 决策

per spec "如果仍无法验证，标记 deferred，不要阻塞 Meteora DLMM":

- **raydium_cpmm_pid_fixed = false**
- **raydium_cpmm_status = deferred**
- **does_not_block_meteora_dlmm = true**
- **raydium_cpmm still P2 in priority; not on Meteora DLMM (P0) critical path**

## 5. 候选 follow-up (operator input required)

- 候选 1: 由 operator 提供 Raydium CPMM mainnet pid (从 Raydium 官方 Discord / 公告 / Solscan)
- 候选 2: 用 paid RPC + 已知 token pair 反查 (e.g. SOL/USDC CPMM pool owner pid)
- 候选 3: 接受 deferred 状态; Raydium CPMM 不在 V1/V2 critical path; 后续 stage 视需要再开 fix
- 候选 4: 用 Solscan / explorer 抓 deployed program (Level A explorer; 但 V1 spec "explorer only guess" → forbidden, 仍需官方确认)

## 6. 不在本阶段做

- ❌ 不凭模型记忆填 mainnet pid
- ❌ 不 webfetch blog / Twitter / 论坛 / 非官方 fork
- ❌ 不跑 GPA
- ❌ 不接 wallet / 不读 keypair
- ❌ 不构造 transaction

## 7. 安全断言

```text
this_stage_only_did_source_audit_and_onchain_verify  = true
this_stage_did_not_hard_code_pid_from_memory        = true
this_stage_did_not_run_gpa                          = true
solana_wallet_or_keypair_touched                    = false
can_run_probe_now                                   = false
v2_line_count_unchanged                             = true (992)
```

## 8. 下一阶段

进入 Stage G: Lifinity pid decision — 若 docs 仍 404 / 无 GitHub source, 显式 deferred, 不阻塞 P0/P1.
