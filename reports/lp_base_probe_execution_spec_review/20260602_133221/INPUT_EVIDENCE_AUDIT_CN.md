# 输入证据审计

- stage: `LP_BASE_10_20U_PROBE_EXECUTION_SPEC_REVIEW_V1`
- phase: B
- run_id: `20260602_133221`
- 上一阶段: `LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1` (20260602_112400)

## 1. 上游门禁校验

| 门禁 | 期望 | 实际 | 通过 |
|---|---|---|---|
| 上一阶段 status | PASS | PASS | ✓ |
| can_run_probe_now | false | false | ✓ |
| wallet_loaded | false | false | ✓ |
| signer_created | false | false | ✓ |
| transaction_sent | false | false | ✓ |
| edge_proven | no | no | ✓ |
| tiny_canary_allowed | no | no | ✓ |
| 上一阶段 recommended_next_stage | LP_BASE_10_20U_PROBE_EXECUTION_SPEC_REVIEW_V1 | LP_BASE_10_20U_PROBE_EXECUTION_SPEC_REVIEW_V1 | ✓ |

## 2. 继承的关键事实

| 字段 | 值 | 来源 |
|---|---|---|
| chain | base (chain_id 8453) | upstream FINAL_VERDICT |
| pool | `0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38` | upstream FINAL_VERDICT |
| pair | WETH/USDC | upstream FINAL_VERDICT |
| fee_tier | 100 (0.01%) | upstream FINAL_VERDICT |
| protocol | Uniswap V3 (Base) | upstream base_candidate_freeze |
| npm | `0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1` | upstream base_candidate_freeze |
| wallet | `0xb05b2872ace4564ff247555b6f7b097d31f3d835` | upstream FINAL_VERDICT |
| preferred_notional | 10 USD | upstream FINAL_VERDICT |
| max_notional | 20 USD | upstream FINAL_VERDICT |
| **recommended_first_notional** | **10 USD** | 本阶段推荐 |
| recommended_first_hold_window | 15 minutes | upstream tick_range |
| max_manual_extension | 30 minutes | 本阶段规定 |
| tick range | lower=-200643, upper=-200243 (medium) | upstream tick_range |
| token amount (10U) | 0 WETH + 10 USDC | upstream token_amount_calc |
| token amount (20U) | 0 WETH + 20 USDC | upstream token_amount_calc |
| known required action | USDC ApproveExact (allowance 5 < 10/20) | upstream base_wallet_balance |

## 3. 上游已读 artifacts (16 项)

| 类别 | 路径 | 关键事实 |
|---|---|---|
| dry-run FINAL_VERDICT | `reports/lp_base_probe_dry_run_builder/20260602_112400/FINAL_VERDICT.json` | status=PASS; can_run_probe_now=false; recommended_next_stage=本阶段 |
| dry-run ONEPAGE | `.../ONEPAGE_CN.md` | human-readable 摘要 |
| dry-run candidate freeze | `.../base_candidate_freeze.json` | frozen_count=1; 4 alternates rejected; BSC 路径拒绝 |
| dry-run balance/allowance | `.../base_wallet_balance_allowance_refresh.json` | block 46807131; USDC 21.775; allowance 5.0 |
| dry-run pool state | `.../base_pool_state_refresh.json` | block 46807634; current_tick=-200443; anchor=$1973.88 |
| dry-run tick range | `.../tick_range_proposal.json` | 3 档; medium 推荐; tick spacing aligned |
| dry-run token amount | `.../token_amount_calc.json` | 10U/20U = 0 WETH + 10/20 USDC |
| dry-run unsigned pkg | `.../wallet_bound_unsigned_package.json` | 10U/20U; deadline placeholder 2099-01-01 |
| dry-run gas feasibility | `.../gas_estimate_feasibility.json` | approve=38704 (live); mint=180k (inherited); total 218,704 gas; $0.0076 |
| dry-run approval checkpoint | `.../BASE_PROBE_MANUAL_APPROVAL_CHECKPOINT_CN.md` | 上游 regex (dry-run 用) |
| + CN 文档 6 项 | `.../BASE_*.md` | human-readable 配套 |
| + input_evidence_audit | `.../input_evidence_audit.json` | 上游 input audit |

## 4. 钱包余额快照（继承自 dry-run Phase E, block 46807131）

| 字段 | 值 |
|---|---|
| ETH native | 0.0000905 ETH ≈ $0.18 (borderline) |
| WETH | 0.0024701310037938 ≈ $4.89 |
| USDC | 21.774783 ≈ $21.77 |
| WETH → NPM allowance | 0.0024701310037938 (ApproveExact 旧痕迹; 0 wei mint 不需新) |
| USDC → NPM allowance | 5.0 (5 USDC) |

## 5. 本轮范围

```text
base_10u_lp_probe_execution_spec_review_only
```

### 允许
- 设计 execution runbook (no execution)
- 定义 stop conditions
- 定义 telemetry schema (no writes)
- 设计 execution script boundary (allow/deny)
- 公布 human approval template (template only; 本轮 non-effective)
- 公布 risk acceptance statement
- 推荐 next stage

### 禁止
- 加载私钥 / 助记词 / keystore
- 创建 signer / wallet client
- 发送 `eth_sendTransaction` / `eth_sendRawTransaction`
- 执行 approve / mint / increaseLiquidity / decreaseLiquidity / collect / burn / swap
- 启动 lpbot-live / lpbot-canary / lpbot-paper
- 自动 bridge / swap
- 翻转 `can_run_probe_now` / `tiny_canary_allowed` / `edge_proven`
- 本轮执行任何审批短语
- 写 production lpbot 表
- 改任何策略执行路径

## 6. 通过

```text
all 16 inputs read                          = yes
all upstream gates aligned                  = yes
previous status = PASS                      = yes
proceed_to_phase_C                          = true
```
