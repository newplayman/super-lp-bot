# Reusable Artifacts and Modules — Stage G

- stage: `LP_RESEARCH_FINAL_FREEZE_AND_HANDOFF_V1`
- run_id: `20260604_051254`

## 0. 保留原则

LP research 收口, 但**所有已验证的代码、文档、测试、artifact 都保留**, 不删除. 这些是真实的工程成果, 可用于:
- 未来其他 LP research (e.g. V4 协议上线)
- Scanner / dashboard / monitoring tool
- Hedging tool / arbitrage tool
- 其他 chain (EVM, Base, Arbitrum) LP research
- Polymarket / prediction market research
- Educational reference

## 1. 12 个核心可复用模块

### 1.1 EVM V3 quote / depth / cost pipeline

**状态**: ✅ 保留
**位置**: `scripts/lp_*.py` 历史 (early commits)
**功能**:
- Uniswap V3 QuoterV2 call
- V3 depth / liquidity profile
- V3 cost decomposition (rent + priority fee + slippage)
**复用场景**:
- EVM V3 LP research (Base, Arbitrum, Mainnet)
- V3 scanner
- V3 fee model reference

### 1.2 BSC PancakeSwap V3 QuoterV2 fix

**状态**: ✅ 保留
**位置**: `scripts/lp_*.py` 历史
**功能**:
- PancakeSwap V3 QuoterV2 ABI 修复
- V3 pool on-chain decode
- V3 fee calculation
**复用场景**:
- BSC LP research
- PancakeSwap V3 scanner
- EVM V3 reference

### 1.3 Base wallet dry-run builder

**状态**: ✅ 保留
**位置**: `scripts/lp_*.py` 历史
**功能**:
- EVM wallet dry-run 构造 (无 keypair 暴露)
- V3 addLiquidity / removeLiquidity / collect simulation
- cost estimation
**复用场景**:
- EVM LP dry-run 工具
- V3 pre-flight 工具
- V3 cost calculator

### 1.4 Solana RPC registry

**状态**: ✅ 保留
**位置**: `reports/lp_solana_rpc_registry_fix/*/`
**功能**:
- 5 mainnet Solana program ids (Meteora DLMM, Orca, Raydium CLMM, Raydium AMM v4, Raydium DAMM v2) on-chain verified
- 2 devnet fallbacks documented
- on-chain ownership verification procedure
**复用场景**:
- 任何 Solana LP research / scanner
- Solana protocol identification
- Program id discovery

### 1.5 Meteora DLMM connector

**状态**: ✅ 保留
**位置**: `scripts/lp_meteora_dlmm_targeted_top_pool_feed_expansion_v1_readonly.js`
**功能**:
- 56/56 pool SDK decode via `@meteora-ag/dlmm@1.9.10`
- 27 quote-ready via `swapQuote` (10/20/100/500/1000/2000 USD)
- 4536 EV cells (6 × 7 × 4)
**复用场景**:
- 任何 Meteora DLMM 工作
- DLMM fee velocity scanner
- DLMM IL model

### 1.6 Orca connector

**状态**: ✅ 保留
**位置**: `scripts/lp_orca_whirlpool_readonly_connector_v1_readonly.js`
**功能**:
- 75/75 pool SDK decode via `@orca-so/whirlpools@8.0.0`
- tick array PDA derive + read (LAZY init finding)
- 10 quote-ready via `swapInstructions` quote-only
- 1680 EV cells
**复用场景**:
- 任何 Orca Whirlpool 工作
- V3 CL on Solana reference
- tick array lazy init study

### 1.7 Raydium CLMM connector

**状态**: ✅ 保留
**位置**: `scripts/lp_raydium_clmm_readonly_connector_v1_readonly.js`
**功能**:
- 65/65 pool SDK decode via `@raydium-io/raydium-sdk@1.3.1-beta.58` (PoolInfoLayout)
- 50 quote-ready via liquidity ratio heuristic
- 8400 EV cells
**复用场景**:
- 任何 Raydium CLMM 工作
- V3 CL 第三方 SDK reference
- liquidity-based quote fallback (when tick arrays unavailable)

### 1.8 Raydium CPMM connector (AMM v4)

**状态**: ✅ 保留
**位置**: `scripts/lp_raydium_cpmm_readonly_connector_v1_readonly.js`
**功能**:
- 81/81 pool SDK decode via `@raydium-io/raydium-sdk-v2@0.2.50-alpha` (liquidityStateV4Layout)
- 73 quote-ready via constant product formula
- 12264 EV cells
- 24 stable pairs (USDC-anchor) identified
**复用场景**:
- 任何 Raydium AMM v4 工作
- constant product LP research
- 替代 Saber 的 stable pool reference

### 1.9 Survival EV framework

**状态**: ✅ 保留
**位置**: 各 stage `*_survival_ev_preview.{json,csv}`
**功能**:
- 6 notionals × 7 hold windows × 4 scenarios = 168 cells per pool
- 4 IL/LVR scenarios: zero / optimistic / realistic / conservative
- heuristic 0.5%/day turnover, scenario-adjusted IL rates
- Heuristic-flagged rows (not actual fee data)
**复用场景**:
- 任何 LP research 的 EV model
- IL/LVR scenario analysis
- Liquidity yield backtest

### 1.10 Artifact index / verdict discipline

**状态**: ✅ 保留
**位置**: `reports/lp_*/ARTIFACT_INDEX.md` + `docs/LPBOT_RESEARCH_ARTIFACT_INDEX_CN.md`
**功能**:
- 每 stage 独立 artifact index
- 跨 stage 累计 evidence chain
- Verdict discipline (status, can_run_probe_now, tiny_canary_allowed, recommended_next_stage)
**复用场景**:
- 任何 research project 的 artifact organization
- Verdict schema 模板
- 跨 stage evidence audit

### 1.11 Safety gates

**状态**: ✅ 保留 + 持续 active
**位置**: `tests/test_lp_*.py` (5 个 test 文件)
**功能**:
- pytest 强制 chain verify (owner = mainnet program)
- 强制 FINAL_VERDICT has all required fields
- 强制 no Keypair / no signer / no tx in any artifact
- 强制 can_run_probe_now = false / tiny_canary_allowed = no
- 强制 data_len check (协议 specific)
- 强制 heuristic marked on all EV rows
- 强制 survival EV ran on quote-ready only
**复用场景**:
- 任何 Solana LP / DEX research 测试
- 任何 read-only connector 测试
- safety-first 模板

### 1.12 Hard-disable executor

**状态**: ✅ 保留 + active
**位置**: `internal/core/execution/` (Go code)
**功能**:
- 即使 build tags 错配, hard-disable 阻止 sendTransaction
- `mode_default.go` 故意 `os.Exit(1)` 在无 build tag 时
- `_live.go` / `_stub.go` 配对, dry-run 路径 panics if 错误 invoked
**复用场景**:
- 任何需要 write-disable 安全的项目
- Build tag 安全模式
- 任何 live / paper 路径的强约束

## 2. 不要删除的 artifacts

```text
scripts/                   # all 5 LP connector runner scripts
tests/                     # all 5 LP test files
docs/                      # all research docs (LPBOT_RESEARCH_STATUS_CN.md 等)
reports/                   # all 5 stage artifact dirs (28160 cells total EV)
README.md                  # top-level readme
internal/core/execution/   # hard-disable executor
```

## 3. 复用路径

| 复用模块 | 可用于 |
|---|---|
| 1.1 EVM V3 pipeline | Base/Arbitrum/Mainnet V3 research |
| 1.2 BSC QuoterV2 fix | BSC V3 research |
| 1.3 Base wallet dry-run | EVM LP dry-run 工具 |
| 1.4 Solana RPC registry | 任何 Solana LP research |
| 1.5-1.8 4 个 connector | 4 个 Solana AMM (DLMM, Orca, CLMM, CPMM) |
| 1.9 Survival EV | 任何 LP research |
| 1.10 Artifact index | 任何 research project |
| 1.11 Safety gates | 任何 read-only connector |
| 1.12 Hard-disable | 任何 write-disabled project |

## 4. 重要 caveat

- 复用 ≠ 直接 production deploy. 必须重做 read-only → preflight → dry-run → manual approval.
- 复用模块可能在不同 chain / protocol 上需要适配.
- safety gates 和 hard-disable 持续 active, 不应改动.
