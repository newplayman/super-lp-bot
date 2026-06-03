# Input Evidence Audit — LP_SOLANA_LP_CONNECTOR_DESIGN_V1

- stage: `LP_SOLANA_LP_CONNECTOR_DESIGN_V1`
- run_id: `20260603_080347`
- branch: `feat/supabase-postgres-deployment`
- head before: `e4deffb` (research: discover multichain lp survival ev 20260603_051605)

## 1. 上游 inputs 一览

| 路径 | 关键字段 | 状态 |
|---|---|---|
| `reports/lp_multichain_survival_ev/20260603_051605/FINAL_VERDICT.json` | `status=WARN`, `positive_realistic_count=0`, `positive_conservative_count=0`, `near_break_even_count=0`, `candidate_now=0`, `can_run_probe_now=false`, `recommended_next_stage=LP_SOLANA_LP_CONNECTOR_DESIGN_V1`, `evm_v3_path_paused` (推断) | OK |
| `reports/lp_multichain_survival_ev/20260603_051605/ONEPAGE_CN.md` | structural_finding = "0/19,980 V3 LP positive EV" | OK |
| `reports/lp_multichain_survival_ev/20260603_051605/ARTIFACT_INDEX.md` | 26 产物 | OK |
| `reports/lp_multichain_survival_ev/20260603_051605/survival_horizon_ev_model.{csv,json}` | 19980 rows; best by notional; even zero_il_lvr ceiling negative | OK |
| `reports/lp_multichain_survival_ev/20260603_051605/lp_candidate_scoring.{csv,json}` | 134 pools × 6 notionals; 0 candidate_now | OK |
| `reports/lp_base_10u_probe_execution_script_build/20260602_135824/FINAL_VERDICT.json` | executor v2 built; `can_run_probe_now=false`; `execution_stubs_disabled=true` | OK |
| `reports/lp_base_probe_execution_spec_review/20260602_133221/FINAL_VERDICT.json` | execution_runbook_ready; `can_run_probe_now=false` | OK |
| `docs/LPBOT_RESEARCH_STATUS_CN.md` | LP strategy research FROZEN; `tiny_canary_allowed=no`; `edge_proven=no` | OK |
| `docs/LPBOT_RESEARCH_ARTIFACT_INDEX_CN.md` | 索引 | OK |

> 注：spec 中的 `reports/lp_base_probe_execution_script_build/...` 实际位于 `reports/lp_base_10u_probe_execution_script_build/...`（多了 `10u_`）。等价。

## 2. 关键事实

```text
EVM V3 survival EV                  = 0/19,980 positive (per FINAL_VERDICT)
positive_realistic_count           = 0
positive_conservative_count        = 0
near_break_even_count              = 0
candidate_now                      = 0
can_run_probe_now                  = false
recommended_next_stage             = LP_SOLANA_LP_CONNECTOR_DESIGN_V1
```

## 3. 关键判断

1. **EVM V3 简单 LP 范式失败** — cost structure 主导，fee yield 不足不是根因。`LP_BASE_10U_PROBE_*` 路径**暂停**，不再推进执行阶段。
2. **Base 10U probe 上游路径已 completed**（execution_script_build, execution_implementation, overnight monitor, go/nogo）— v2 line 992 保留；`send_hard_disable_still_active=true`；executor 的 `execute-armed` 模式硬退出。
3. **本阶段 (LP_SOLANA_LP_CONNECTOR_DESIGN_V1) 只做 design** — 不实现 connector 代码；只设计：
   - 协议矩阵 (Stage C)
   - 数据源 (Stage D)
   - 3 个协议 connector design (Stage E/F/G)
   - 7 个 normalized schema (Stage H)
   - EV model adaptation (Stage I)
   - 10/20U probe preflight (Stage J)
   - 6 phase roadmap (Stage K)
4. **本阶段不**：
   - 读 Solana 私钥/seed phrase/keypair
   - 创建 signer
   - 发 Solana transaction
   - 调 swap / 开仓 LP / 关仓 LP / collect fee
   - 启动 live/canary/paper
   - 桥接
   - 自动换币
   - 写 production positions
   - 覆盖 shadow 表
   - 修改 EVM executor 执行路径
   - 把 `can_run_probe_now` 设 true 或 `tiny_canary_allowed` 设 yes

## 4. Solana vs EVM 主要差异（影响 design）

| 维度 | EVM | Solana |
|---|---|---|
| account model | contract address | program derived address (PDA) |
| position model | NFT (token id) | position account (PDA) or mint |
| token | ERC20 (4 bytes 32 word) | SPL token mint + ATA |
| LP fee accrual | ERC20 transfer to address | token balance in position account |
| tx cost | gas × gas_price | base_fee + priority_fee + rent (one-time) |
| account creation | contract deploy (~100k-3M gas) | ATA create (~0.00204 SOL rent-exempt) |
| block time | 12s (Ethereum) | ~0.4s |
| quote | QuoterV2 staticcall | simulateSwap / SDK simulate |
| pool discovery | factory.getPool(tokenA, tokenB, fee) | getProgramAccounts(amm_program, filters) |
| pool layout | slot0/liquidity/tickSpacing | LbPair state struct / Whirlpool state / etc |
| position close | ERC721.transferFrom + decreaseLiquidity | close_position + claim_fee |
| IL exposure | range width | bin range / tick range / weight |

## 5. 安全不变式（来自上游 + 继承）

```text
can_run_probe_now                  = false
execution_allowed_now              = false
tiny_canary_allowed                = "no"
edge_proven                        = "no"
actual_fee_ready                   = false
token_id_available                 = false
wallet_or_tx_touched               = false
solana_wallet_or_keypair_touched   = false
manual_approval_required           = true
send_hard_disable_still_active     = true
v2_modified_by_this_task           = false
v2_line_count_unchanged            = true (992)
```

本阶段**不**改任何上述值。

## 6. 决定

继续 Stage C — Solana LP 协议目标矩阵。
