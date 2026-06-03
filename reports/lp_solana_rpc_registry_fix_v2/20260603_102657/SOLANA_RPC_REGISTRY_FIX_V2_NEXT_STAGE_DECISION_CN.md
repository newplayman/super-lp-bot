# Solana RPC Registry Fix V2 — Next Stage Decision

- stage: `LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V2`
- run_id: `20260603_102657`

## 0. 决策

```text
recommended_next_stage                = LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT
default_when_no_explicit_choice       = LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT
```

## 1. 5 选项评估

| next stage | 触发条件 | 是否触发 |
|---|---|---|
| `LP_METEORA_DLMM_READONLY_CONNECTOR_V1` | Meteora source verified + onchain verified + SDK/API path identified + minimal smoke success OR path feasible | **❌** (smoke partial; needs full SDK install + struct decode; full discovery needs paid RPC; entry conditions not fully met) |
| `LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT` | SDK/API path promising but smoke incomplete | **✅ 触发** (Stage C identified SDK path; Stage E smoke partial; needs another fix_repeat to (a) install SDK + run full struct decode, (b) decide paid RPC vs known-pool feed) |
| `LP_SOLANA_PAID_RPC_SETUP_REQUIRED` | no SDK/API path and GPA requires paid RPC | **❌** (SDK/API path IS identified; we just need to wire it; paid RPC is a sub-decision, not a stage gate) |
| `LP_SOLANA_RPC_REGISTRY_FIX_REPEAT` | official sources still incomplete | **❌** (5/6 official sources complete; 4/6 verified on-chain; pid registry essentially complete for non-Lifinity protocols) |
| `STOP_LP_RESEARCH_NOW` | no safe Solana read-only path | **❌** (read-only path is structurally viable: 4/6 verified, 5/6 sourced, SDK path identified, known-pool read smoke works) |

## 2. 为什么选 LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT

### 2.1 进步 (V1 → V2)

| metric | V1 (FIX_REPEAT_V1) | V2 (FIX_REPEAT_V2) | improvement |
|---|---|---|---|
| Meteora DLMM Q1 (source) | ✅ | ✅ | — |
| Meteora DLMM Q2 (verified) | ✅ | ✅ | — |
| Meteora DLMM Q3 (gpa smoke) | ❌ public RPC timeout | ⚠️ known-pool read verified; full discovery needs paid RPC | **partial fix** |
| Meteora DLMM Q4 (sdk/api path) | partial (designed) | ✅ SDK package identified + read-only helpers listed + API not_found | **full fix** |
| Meteora DLMM Q5 (minimal smoke) | ❌ | ⚠️ known-pool read path verified; struct fields not extracted | **partial fix** |
| Raydium CPMM | not_found (mainnet) | not_found (mainnet **AND** devnet) | same (worse on devnet) |
| Lifinity | unknown (V1 said 404) | deferred (V2 re-probed: docs 200 but SPA; no pid) | same overall, but more thorough |

### 2.2 为什么 NOT 直接进 connector

- connector V1 要求 (per spec): "minimal smoke success OR clear SDK/API connector feasibility"
- 5/5 sub-conditions 都被**接触**; 但 2/5 仍需 operator action:
  - paid RPC (or known-pool feed) for first-time discovery
  - SDK install + struct decode for full read
- 这 2 个**不**应该**不**经 operator 就直接接; 应该再 fix_repeat 把 2 个补完

### 2.3 下一阶段 (FIX_REPEAT) 需要做什么

按优先级:
1. **Install `@meteora-ag/dlmm` v1.9.10** (npm install) and run full struct decode on `5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF` (and at least 1-2 more known pools) to get active_id, bin_step, token mints, fees
2. **Operator decision on paid RPC vs known-pool feed** for full discovery (and connector stage)
3. **(optional)** Try to extract Raydium CPMM real mainnet pid (from operator source)
4. **(optional)** Try to extract Lifinity pid (from operator browser-rendered source) — OR remove Lifinity from P2
5. **Re-run registry v4** with the new info

### 2.4 风险 (per spec 边界)

- connector stage 风险: 需同时 (a) SDK install + full decode, (b) 选 paid RPC OR known-pool feed, (c) 处理 Raydium CPMM "not deployed"
- 这 3 件事**不**应该由一个 stage 一次性解决
- 先 fix_repeat 解决 1-2 件; 然后 connector stage 在干净基础上接 SDK
- **低风险入口** = 修 registry (V1, V2 都在做); **高风险入口** = 修 registry + wire SDK + 选 paid RPC in same stage

## 3. 不在本阶段做

- ❌ 不 webfetch 任何官方 source (Stage C 已做)
- ❌ 不跑 on-chain verify (V1 已做)
- ❌ 不跑 GPA (V1 + V2 Stage E 已做)
- ❌ 不接 wallet / 不读 keypair
- ❌ 不调 swap / open LP / close LP / collect fee / bridge
- ❌ 不构造 transaction
- ❌ 不假设 paid RPC 已就绪 (operator 必须显式提供)

## 4. 安全断言

```text
this_stage_only_decision       = true
this_stage_did_not_load_keypair = true
solana_wallet_or_keypair_touched = false
can_run_probe_now               = false
v2_line_count_unchanged         = true (992)
```

## 5. 操作员后续

- 默认下一阶段 = `LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT`（无需操作员声明）
- 关键 input 需求 (建议下个 prompt 提供):
  1. **paid RPC 决策** (Helius / Triton / QuickNode; 或 维持 public only + known-pool feed)
  2. **是否同意 connector stage 走"已知 pool feed + SDK decode"路径** (而非 paid RPC GPA for first-time discovery)
  3. (optional) **Raydium CPMM 真 mainnet pid** (从 operator 人类来源)
  4. (optional) **Lifinity pid** (从 operator 浏览器渲染 docs) **OR 同意从 P2 列表移除**
- 不建议改选 connector V1 (5/5 conditions touched 但 2 仍需 operator action)
- 不建议 STOP (5/6 source + 4/6 verified + sdk path identified + known-pool read smoke works = 显著进步)
- 即便选 connector V1, **仍需**新一轮 prompt 显式确认; 本阶段**未**自动做这件事。
