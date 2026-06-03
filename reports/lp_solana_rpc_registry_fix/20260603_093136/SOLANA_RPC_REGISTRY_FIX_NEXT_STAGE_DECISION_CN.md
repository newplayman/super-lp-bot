# Solana RPC Registry Fix — Next Stage Decision

- stage: `LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V1`
- run_id: `20260603_093136`

## 0. 决策

```text
recommended_next_stage = LP_SOLANA_RPC_REGISTRY_FIX_REPEAT
```

## 1. 5 选项评估

| next stage | 触发条件 | 是否触发 |
|---|---|---|
| `LP_METEORA_DLMM_READONLY_CONNECTOR_V1` | Meteora verified + GPA feasible OR SDK/API path | **❌** (3/4 entry fails: GPA timeout, SDK/API not wired, Meteora only 4/5 sub-conditions) |
| `LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1` | Orca stronger than Meteora after registry fix | **❌** (Orca also blocked on GPA; -32010 program too large) |
| `LP_SOLANA_RPC_REGISTRY_FIX_REPEAT` | registry still incomplete but fixable | **✅ 触发** (Raydium CPMM pid not on mainnet; Lifinity unknown; GPA 0/4 on public RPC) |
| `LP_SOLANA_RPC_SETUP_REQUIRED` | RPC now unusable | **❌** (RPCs fully usable; 2/2 endpoints; 8/8 methods) |
| `STOP_LP_RESEARCH_NOW` | no safe read-only Solana path | **❌** (read-only path structurally viable; 4/6 verified) |

## 2. 为什么选 LP_SOLANA_RPC_REGISTRY_FIX_REPEAT

### 2.1 进步 (vs 上一轮)

| metric | 上一轮 (FIX_REPEAT) | 本轮 (FIX_REPEAT_V1) | improvement |
|---|---|---|---|
| verified_count | 0/6 | 4/6 | +4 |
| official_source_count | 0/6 | 5/6 | +5 |
| GPA success on public RPC | 0 (no pid) | 0 (GPA infra blocker) | same (blocker is GPA, not pid) |

### 2.2 仍需 fix 的 4 件事

1. **Raydium CPMM pid not on mainnet**:
   - 当前 pid `CPMMoo8L3F4NbTegBCKVNunggN7H1ZpdTHKxQB5qKP1C` from raydium-cp-swap `declare_id!` is **not** on mainnet
   - 推测: cp-swap 是新仓库; mainnet 上 AMM v4 / CPMM 实际 pid 在 `raydium-amm-v3` 仓库
   - 下一轮 fix_repeat: 用 `raydium-amm-v3` 源 或 Raydium 官方 docs
2. **Lifinity 仍 unknown**:
   - docs.lifinity.io 404; 无公开 GitHub source
   - spec 禁止凭记忆 hardcode
   - 下一轮可由 human 提供 pid (不在 connector 关键路径; OK to defer)
3. **GPA on public RPC** 0/4 success:
   - 即使 `dataSlice: 0,0`, Meteora DLMM / DAMM v2 / Orca / Raydium CLMM 都超时
   - 原因: AMM 程序 accounts 太多 (数千到数万); public RPCs 限 5MB response
   - 下一轮 fix_repeat 需要:
     - **operator 决策**: 是否接受 paid RPC (Helius / Triton / QuickNode)?
     - 或: 用 Meteora DLMM API + Raydium API + Orca SDK (无 GPA, 直接 pool list)
4. **SDK / API paths designed but not wired**:
   - 下一轮 fix_repeat 可顺带 wire 1-2 个 (Meteora SDK + Meteora DLMM API)
   - 或: 留给 connector stage wire

### 2.3 为什么 NOT 直接进 connector

- connector stage 风险: 需同时 (a) 解决 GPA 障碍 (选 paid RPC or indexer), (b) wire SDK/API, (c) 处理 CPMM "not on mainnet" 现象
- 这 3 件事**不**应该由一个 stage 一次性解决
- 先 fix_repeat 解决 1-2 件; 然后 connector stage 在干净基础上接 SDK
- **低风险入口** = 修 registry; **高风险入口** = 修 registry + wire SDK + 选 paid RPC in same stage

## 3. fix_repeat 阶段需要做的事 (高优先级)

1. **拉 Raydium CPMM 真 pid** (从 raydium-amm-v3 或 docs)
2. **operator 决策**: paid RPC vs indexer vs SDK-only pool discovery
3. (optional) **重新尝试 Lifinity pid** (human 或 webfetch)
4. **重跑 Stages D-H** (with new CPMM + Lifinity + paid RPC decision)
5. **本轮 fix_repeat 完成后**, 如果 4/4 conditions 全过, 才能进 `LP_METEORA_DLMM_READONLY_CONNECTOR_V1`

## 4. 不在本阶段做

- ❌ 不 webfetch 任何官方 source (Stage C 已做)
- ❌ 不跑 on-chain verify (Stage E 已做)
- ❌ 不跑 GPA (Stage F 已做)
- ❌ 不接 wallet / 不读 keypair
- ❌ 不调 SDK / indexer / API
- ❌ 不构造 transaction

## 5. 安全断言

```text
this_stage_only_decision       = true
this_stage_did_not_load_keypair = true
solana_wallet_or_keypair_touched = false
can_run_probe_now               = false
v2_line_count_unchanged         = true (992)
```

## 6. 操作员后续

- 默认下一阶段 = `LP_SOLANA_RPC_REGISTRY_FIX_REPEAT`（无需操作员声明）
- 关键 input 需求 (建议下个 prompt 提供):
  1. Raydium CPMM 的真 mainnet pid (从 raydium-amm-v3 或 docs)
  2. paid RPC 决策 (Helius / Triton / QuickNode / 维持 public only)
  3. (optional) Lifinity pid (如有人类来源)
  4. (optional) 是否同意 connector stage 直接 wire SDK + 选 paid RPC (而非再 fix_repeat)
- 不建议改选 connector (3/4 conditions 不满足, 1/2 协议 not found)
- 不建议 STOP (5/6 source + 4/6 verified 是显著进步; 不是 structural failure)
