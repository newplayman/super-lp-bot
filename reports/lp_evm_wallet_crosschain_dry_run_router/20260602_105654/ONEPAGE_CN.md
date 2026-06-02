# 跨链路由总览

```text
stage                                       = LP_EVM_WALLET_ADDRESS_CROSSCHAIN_DRY_RUN_ROUTER_V1
run_id                                      = 20260602_105654
status                                      = PASS

wallet_address_bound                        = true   (公开地址，仅作 from 字段)
wallet_address_masked                       = 0xb05b...d835
wallet_loaded                               = false
signer_created                              = false
transaction_sent                            = false

base_rpc_ready                              = true   (publicnode 8453)
bsc_rpc_ready                               = true   (publicnode 56)

base_total_usd_proxy                        = $26.84
  ├ Base ETH (native)                       = $0.18
  ├ Base WETH                               = $4.89
  └ Base USDC                               = $21.77
bsc_total_usd_proxy                         = $0.00
likely_funded_chain                         = base

bsc_candidate_ready                         = true   (USDT/WBNB 0.01% from prior stage)
bsc_candidate_blocked_by_funds              = true   (no BSC funds)
base_candidate_count                        = 5
base_dry_run_ready_candidate_count          = 5
recommended_probe_chain                     = base
primary_base_candidate                      = WETH/USDC 0x72ab388e... (0.01%) — wallet holds both tokens

can_run_probe_now                           = false
can_run_wallet_address_dry_run_next         = true
manual_approval_required_for_any_execution  = true
edge_proven                                 = no
tiny_canary_allowed                         = no
wallet_or_tx_touched                        = false

recommended_next_stage                      = LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1
```

## 一句话

钱包资金在 Base ≈ $26.84，BSC = $0。BSC 候选已 ready 但被资金阻断；Base 有 5 个 dry-run-ready 候选（首推 WETH/USDC 0.01%，钱包双 token 命中 + 已有 Uniswap V3 NPM 部分 allowance）。下一步是 `LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1`（仍只读，仍不签名不发交易）。

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
× 未在 Base RPC 不可用时编造余额
```

## 操作员后续抉择

```text
路径 A（推荐）：进入 LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1
              候选：WETH/USDC 0x72ab388e... (0.01%)
              钱包：双 token 已就位，仍需要补 ~$1 ETH 作 gas 余量（advisory）
              然后再走 wallet-address dry run、人工审批、最后才是执行（隔好几道门禁）

路径 B：继续 BSC 路径
              须由您自行在 BSC 上准备 ~$25 等值（USDT+WBNB+BNB gas）
              如何获取（CEX 提币 / 您自选 bridge）在本工具范围之外
              资金到位后可直接重发 BSC 的审批短语进入 BSC wallet-address dry run

路径 C：暂停 LP 研究
              recommended_next_stage = STOP_LP_RESEARCH_NOW
              所有 dry-run / preflight artifacts 完整保留可日后复用
```
