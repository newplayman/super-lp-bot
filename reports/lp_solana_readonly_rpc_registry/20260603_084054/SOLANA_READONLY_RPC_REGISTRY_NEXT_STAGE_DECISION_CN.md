# Solana Readonly RPC + Registry — Next Stage Decision

- stage: `LP_SOLANA_READONLY_RPC_AND_REGISTRY_V1`
- run_id: `20260603_084054`

## 0. 决策

```text
recommended_next_stage = LP_SOLANA_RPC_REGISTRY_FIX_REPEAT
allowed_next_stages    = [
  LP_METEORA_DLMM_READONLY_CONNECTOR_V1,    # 不选 (3/4 条件不满足)
  LP_SOLANA_RPC_REGISTRY_FIX_REPEAT,         # 选
  LP_SOLANA_RPC_SETUP_REQUIRED,              # 不选 (RPC usable)
  STOP_LP_RESEARCH_NOW                       # 不选 (RPC + read-only path 仍可用)
]
```

## 1. 4 选项评估

| next stage | 触发条件 | 是否触发 |
|---|---|---|
| `LP_METEORA_DLMM_READONLY_CONNECTOR_V1` | RPC usable + program verified or enough registry confidence + account discovery feasible or SDK/API path feasible | **❌ 3/4 条件不满足**（registry confidence 仅 0.3 placeholder; verified_count=0; discovery 未跑） |
| `LP_SOLANA_RPC_REGISTRY_FIX_REPEAT` | RPC usable but program registry incomplete | **✅ 触发**（RPC usable; verified_count=0; 0 个 program id verified） |
| `LP_SOLANA_RPC_SETUP_REQUIRED` | no usable RPC or public RPC too limited | **❌ 不触发**（2/2 public RPC usable; 8/8 method 全过） |
| `STOP_LP_RESEARCH_NOW` | no safe read-only Solana path | **❌ 不触发**（read-only path 完整可行） |

## 2. 为什么选 LP_SOLANA_RPC_REGISTRY_FIX_REPEAT

### 2.1 现状

- ✅ Solana RPC 可用（publicnode latency 314ms; 8/8 method verified; 系统 program sanity check OK）
- ❌ 6 protocol program id 都未 verified（Stage D seed 故意没填；Stage E verify 没跑）
- ❌ 0 protocol GPA smoke（无 pid）
- ❌ 0 protocol token/quote test
- ✅ Token/quote reference design 完成（Stage G）
- ❌ LP_METEORA_DLMM_READONLY_CONNECTOR_V1 3/4 条件不满足

### 2.2 fix_repeat 阶段需要做的事

1. **从外部 (人类 / webfetch) 拉 6 个 protocol 官方 program id**
   - Meteora DLMM: docs.meteora.ag 或 Meteora GitHub
   - Meteora DAMM v2: 同上
   - Orca Whirlpools: docs.orca.so 或 Orca GitHub
   - Raydium CLMM / CPMM: raydium.io/docs 或 Raydium GitHub
   - Lifinity: lifinity.io (资料少; 仍标 unknown)
2. **更新 Stage D registry seed**：填入 6 个 program id
3. **重跑 Stage E on-chain verify**：每个 pid 跑 `getAccountInfo` 检查 executable=true
4. **重跑 Stage F GPA smoke**：每个 verified program 跑 bounded GPA
5. **重跑 Stage H/I readiness**：Meteora DLMM 4/4 条件；Orca + DAMM 各自 4/4 条件
6. **重跑 Stage J** → 如果 4/4 条件全过，**才**进 `LP_METEORA_DLMM_READONLY_CONNECTOR_V1`

### 2.3 fix_repeat 阶段禁止

- ❌ 不 load 任何 keypair / private key
- ❌ 不接 wallet
- ❌ 不调 sendTransaction
- ❌ 不开 LP / swap / bridge
- ❌ 不 hard-code program id **不通过官方 source**（spec 仍要求验证）

## 3. 为什么 NOT STOP_LP_RESEARCH_NOW

- Solana read-only path **完整** 存在 (RPC + GPA path + token/quote design)
- 仅缺 program id，**这是一个数据**问题，不是结构性问题
- STOP 在 1 个 spec 强制 gap 时过早
- fix_repeat 解决后即可进 connector

## 4. 为什么 NOT LP_SOLANA_RPC_SETUP_REQUIRED

- 2/2 public RPC **都**可用
- 8/8 method 都过
- 不需要 paid RPC 或 private RPC 来 read-only registry
- paid RPC 仍是 v2 优化（after program id fixed）

## 5. 为什么 NOT LP_METEORA_DLMM_READONLY_CONNECTOR_V1

- 4 个 entry 条件只满足 1 个（RPC usable）
- program id 未 verified → on-chain account **可能** 不存在或不同
- discovery 未跑 → connector 写出来没意义
- SDK/API path 仅 design 阶段，**未实际调用**
- spec connector stage 条件强制要求 verified program id

## 6. 阶段决策签名

```text
recommended_next_stage            = LP_SOLANA_RPC_REGISTRY_FIX_REPEAT
solana_rpc_readiness_ran         = true
usable_rpc_count                 = 2
protocol_registry_seed_ready    = true
program_verification_ran         = true
verified_program_count          = 0
account_discovery_feasibility_ran = true
meteora_dlmm_registry_ready     = false
orca_registry_ready             = false
damm_v2_registry_ready          = false
can_run_probe_now               = false
recommended_next_stage_in_set    = true
```

## 7. 操作员后续

- 默认下一阶段 = `LP_SOLANA_RPC_REGISTRY_FIX_REPEAT`（无需操作员声明）
- 可选改：
  - 显式提供 6 个 program id 给 fix_repeat stage（人类流程）
  - 显式 webfetch docs 给 fix_repeat stage
  - **不建议**改选 connector stage (3/4 条件不满足)
  - **不建议** STOP (data gap 是 temporary, not structural)
