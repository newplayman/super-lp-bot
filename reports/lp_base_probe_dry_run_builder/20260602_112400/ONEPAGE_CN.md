# Base 10/20U Probe Dry-run Builder 总览

```text
stage                                       = LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1
run_id                                      = 20260602_112400
status                                      = PASS
previous_stage                              = LP_EVM_WALLET_ADDRESS_CROSSCHAIN_DRY_RUN_ROUTER_V1 (20260602_105654)

wallet_address_bound                        = true   (公开地址，仅作 recipient/from)
wallet_address_masked                       = 0xb05b...d835
wallet_loaded                               = false
signer_created                              = false
transaction_sent                            = false

chain                                       = base
chain_id                                    = 8453
rpc_ready                                   = true   (publicnode; host_hash=7d4aef4d)

frozen_candidate
  pool                                      = 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38
  pair                                      = WETH/USDC
  protocol                                  = Uniswap V3 (Base)
  fee_tier                                  = 100 (0.01%)
  tick_spacing                              = 1
  npm                                       = 0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1

tick_range_recommendation
  tier                                      = medium
  lower_tick                                = -200643
  upper_tick                                = -200243
  horizon_minutes                           = 15
  current_tick                              = -200443

notional_paths
  10U                                       = 0 WETH + 10 USDC; gas≈218,704; cost≈$0.0076
  20U                                       = 0 WETH + 20 USDC; gas≈218,704; cost≈$0.0076

wallet_state (at block 46807131)
  ETH_native                                = 0.0000905 ETH (~$0.18 gas; borderline)
  WETH                                      = 0.00247 (~$4.89)
  USDC                                      = 21.775 (~$21.77)
  USDC allowance to NPM                     = 5.0 (need new ApproveExact for 10/20)

invariants
  #3 dryrun broadcast == 0                 = passed
  #4 MinOut/Deadline non-zero              = passed (amount1Min>0; deadline=2099-01-01 placeholder)
  #9 ApproveExact only, never ApproveMax   = passed
  #10 post-exit revoke planned              = passed (step 4 = approve(NPM, 0))

fabrication_blocks
  QuoterV2 live read                        = skipped (inherited from upstream precise_quote CSV)
  Mint gas live estimate                    = skipped (inherited from upstream real_cost_model CSV)
  No fabricated block numbers / balances

can_run_probe_now                           = false
can_run_wallet_address_dry_run_next         = true
manual_approval_required_for_any_execution  = true
edge_proven                                 = no
tiny_canary_allowed                         = no
wallet_or_tx_touched                        = false

recommended_next_stage                      = LP_BASE_10_20U_PROBE_EXECUTION_SPEC_REVIEW_V1
```

## 一句话

Base WETH/USDC 0.01% (`0x72ab388e..`) 候选已 freeze；钱包双 token 命中 (WETH+USDC) + 21.77 USDC 余额；medium tick range [-200643, -200243] (15m)；notional 10U 需 0 WETH + 10 USDC；notional 20U 需 0 WETH + 20 USDC；approve 估计 38704 gas (live)，mint 180000 gas (inherited from upstream)；round-trip ≈ $0.0076 gas；钱包有 $0.18 gas 余量 → 24x margin；USDC allowance 5 < 10/20 → 需 1 个新 ApproveExact (USDC)。下一步是 `LP_BASE_10_20U_PROBE_EXECUTION_SPEC_REVIEW_V1`（仍只读，仍不签名不发交易）。

## 严格禁区（本轮已遵守）

```text
× 未读私钥 / 助记词 / keystore
× 未创建 signer / wallet client
× 未发送 eth_sendTransaction / eth_sendRawTransaction
× 未 approve / mint / decrease / collect / burn / swap
× 未启动 live / canary / paper
× 未自动 bridge / swap
× 未推荐特定 bridge / DEX 切换方案
× 未翻转 can_run_probe_now / tiny_canary_allowed / edge_proven
× 未在 Base RPC 不可用时编造余额 / 合约 / 池数据
× 未构造 QuoterV2 / mint gas 数字（fabrication_blocked = true，全部继承自 upstream）
```

## 偏离（deviation）声明

1. **QuoterV2 live re-read 跳过**：Uniswap V3 QuoterV2 (0x3d4e..) 与 Aerodrome Slipstream Quoter (0x254c..) 在 publicnode 上对标准 selector 都 revert。fabrication_blocked=true，未构造；改继承 upstream precise_quote CSV 中同一池同一 notional 的结果（high confidence, 20U）。
2. **mint gas live estimate 跳过**：publicnode eth_estimateGas 对 mint 调用在所有 amount0/amount1 组合下都 revert。fabrication_blocked=true，未构造；改继承 upstream real_cost_model CSV 中同一池的 `mint_gas_units=180000`。
3. **token amount 0 wei WETH**：V3 in-range math 在 WETH $1974 + 2% range 下，a0 ≈ 4.9e-4 × a1 raw，a0 价值 ≈ a1 价值的 0.05%。所以 10U 路径 WETH 端 = 0 wei（< 1 satoshi），USDC 端 = 10 USDC。wallet 的 0.00247 WETH 远超所需的"~0 WETH"。

## 操作员后续抉择

```text
路径 A（推荐）：进入 LP_BASE_10_20U_PROBE_EXECUTION_SPEC_REVIEW_V1
              先用您键入的审批短语 "APPROVE_BASE_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY wallet=0x<...> notional=10|20"
              把 wallet 地址交给下一阶段，由下阶段做精细化 gas / cost 预测 + 收紧 unsigned tx package
              然后再走人工审批 + 实际执行（隔好几道门禁）

路径 B：继续 BSC 路径
              须由您自行在 BSC 上准备 ~$25 等值（USDT+WBNB+BNB gas）
              资金到位后重新提交 BSC 审批短语
              本阶段**不**提供 BSC 路径 bundle

路径 C：暂停 LP 研究
              recommended_next_stage = STOP_LP_RESEARCH_NOW
              所有 dry-run / preflight artifacts 完整保留可日后复用

路径 D：修改进
              LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_FIX_REPEAT
              或 LP_BASE_CANDIDATE_REFRESH_FOR_PROBE_PREFLIGHT_V1
              适合想换 range / 换 notional / 换 tier 的人
```

## 安全门禁（本轮守住）

```text
wallet_or_tx_touched         = false
can_run_probe_now            = false
tiny_canary_allowed          = no
edge_proven                  = no
fabrication_blocked          = true
```
