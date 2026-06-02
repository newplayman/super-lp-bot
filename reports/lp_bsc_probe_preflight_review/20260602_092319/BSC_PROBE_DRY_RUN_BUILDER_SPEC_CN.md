# 10/20U Probe — Dry-run Builder 需求设计（仅 spec，不实现交易）

- stage: `LP_BSC_10_20U_PROBE_PREFLIGHT_REVIEW_V1`
- phase: F
- 目标：定义下一阶段 `LP_BSC_10_20U_PROBE_DRY_RUN_BUILDER_V1` 的输入 / 输出 / 安全门禁
- **关键**：即使 dry-run builder 拿到人工批准，**也不发交易**。执行是更远的、单独的、隔离的阶段（本审查不涉及）。

## 必需输入

```text
candidate_pool_address     = 0x172fcd41e0913e95784454622d1c3724f546f849
candidate_pair             = USDT/WBNB
candidate_fee_tier_raw     = 100
probe_notional_usd         = 10 or 20
probe_hold_window          = 15m (initial)
rpc_endpoint               = $BSC_RPC_PRIMARY (付费 endpoint；dry-run 阶段允许 publicnode)
wallet_address_for_simulation_only
                           = checksummed address，**仅**用于 eth_call 的 `from` 字段及 eth_call 查询 balance；**绝不**加载为 signer
approval_recipient_address = PancakeSwap V3 NonfungiblePositionManager (BSC) — 硬编码 allowlist
swap_router_address        = PancakeSwap V3 SwapRouter (BSC) — 硬编码 allowlist
tick_lower_strategy        = symmetric_k_sigma | manual
tick_lower_value_if_manual / tick_upper_value_if_manual / k_sigma
```

## 期望输出

| 文件 | 内容 |
|---|---|
| `BSC_10_20U_PROBE_DRY_RUN_REPORT_CN.md` | 人类可读总结 |
| `bsc_10_20u_probe_dry_run_report.json` | 机器读结构化报告 |
| `bsc_10_20u_probe_unsigned_tx_package.json` | **未签名**的 tx calldata 包 |

`unsigned_tx_package.json` 必须包含：

```text
approve_tx_calldata                  hex (constructed, NOT signed, NOT sent)
approve_tx_simulated_gas_used        from eth_call
approve_tx_simulated_logs            from eth_call
mint_tx_calldata                     hex (constructed, NOT signed, NOT sent)
mint_tx_simulated_gas_used           from eth_call
mint_tx_simulated_logs               from eth_call (查 NFT Transfer + IncreaseLiquidity)
expected_tokenId_if_predictable      uint256 or null
decrease_tx_calldata_placeholder     hex (template，依赖 expected tokenId)
collect_tx_calldata_placeholder      hex
revoke_tx_calldata                   hex (post-exit ApproveExact(0))
swap_back_tx_calldata_placeholder    hex (如预计需要)
```

## Dry-run builder 允许的操作

```text
eth_chainId, eth_blockNumber
eth_getCode (pool / token / PositionManager / SwapRouter)
eth_call (任何 read-only — slot0 / liquidity / fee / ticks / balanceOf / allowance / QuoterV2.quoteExactInputSingle / simulate calldata)
eth_getLogs (bounded，用于 fee velocity / NFT Transfer 历史)
eth_estimateGas (read-only gas estimate；**不发送**)
本地 ABI encode calldata（不签名）
写文件到 REPORT_DIR
```

## Dry-run builder 禁止的操作

```text
eth_sendTransaction
eth_sendRawTransaction
personal_sign / personal_signTransaction
eth_sign / eth_signTypedData_*
eth_signTransaction
从 disk / env / keystore / KMS 加载私钥
构造任何 signer 对象
任何具备发送 tx 能力的 wallet client
任何合约的 approve / mint / increaseLiquidity / decreaseLiquidity / collect / burn / swap 调用
修改任何链上状态
写 production lpbot 表
启动 lpbot-live / lpbot-paper / lpbot-canary 进程
翻转 can_run_probe_now / tiny_canary_allowed / edge_proven flag
```

## 写 unsigned tx package 前必须满足的 safety gates

```text
1. candidate_pool_state_validation_passed
2. tickLower < tickUpper 且都按 tick_spacing 对齐
3. expected token amounts 在 QuoterV2 output 的 5% 偏差内
4. approval_recipient 在静态 allowlist
5. swap_router 在静态 allowlist
6. 目标 token 不存在意外残留 allowance
7. wallet 模拟余额足够 notional + gas buffer
8. fee_velocity 最近 5m 有数据
```

## Abort conditions（dry-run 阶段）

```text
- tickLiquidity eth_call 失败
- QuoterV2 staticcall 失败或返回 0
- 当前 tick 已经在选定范围之外
- 预计 swap-back drift > 50 bps
- fee velocity 5m bucket 为 0
- 最近 10 个 RPC 调用中失败 ≥2 次
```

## 人工审批 checkpoint

- 人工看到的内容：完整 unsigned tx package JSON + dry_run_report MD + risk_limits MD + 本审查包
- 人工必须明确键入：`I approve probe 0x172fcd41 USDT/WBNB 20U 15m`（短语必须与候选完全匹配）
- 批准记录写到 `lp_probe_preflight_review_v1.human_approval_received` + `human_approval_at`
- **批准不触发执行** — 执行是后续单独阶段，本 spec 不涉及

## 安全

```text
dry_run_builder_writes_to_db                = false
dry_run_builder_modifies_any_chain_state    = false
wallet_or_tx_touched                        = false
can_run_probe_now                           = false
tiny_canary_allowed                         = no
edge_proven                                 = no
```
