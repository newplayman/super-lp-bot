# Solana M1 执行 sidecar（FIX-E3）

状态：安全边界、纯构建器、`simulateTransaction` dry-run 与测试已经实现；没有生成钱包、加载密钥、签名或广播交易。`LIVE_TRADING` 默认 `false`，示例 systemd unit 不启用、不启动。

## 信任边界

- 策略进程只提交带 `strategy_decision_id`、`risk_verdict_id` 和 idempotency key 的 intent，不读取任何密钥文件。
- sidecar 必须使用独立的 `lpbot-solana-executor` Unix user；`/etc/lpbot-solana-executor` 建议目录权限 `0700`，加密 keystore 和口令文件都必须为该用户所有且为 `0600`。不得把策略用户加入 executor group。
- 禁止 `PRIVATE_KEY`、`SOLANA_PRIVATE_KEY`、`SOLANA_SECRET_KEY`、`SECRET_KEY`、`MNEMONIC`、`SEED_PHRASE` 环境变量。加密 keystore 只允许通过外部 signer 边界读取；sidecar 不解析明文 secret。
- 真实路径只有同时设置 `LIVE_TRADING=true` 和进程启动确认串 `CONFIRM_SOLANA_M1_LIVE_BROADCAST` 才能越过签名前闸。默认任一路径缺失都会在 signer 调用之前抛错。

## 执行契约

- action 仅为 `open / increase / decrease / collect / close / swap`；Raydium AMM v4、Raydium CLMM、Orca Whirlpool 的 program ID 固定映射到 protocol。
- 硬编码 ID 不是信任根。每份交易计划中实际调用的全部 program 都必须在白名单内，并在当次 RPC 上以 `getAccountInfo` 验证 `executable=true`、owner 为认可 loader、context slot 有效。
- 单笔/daily cap、滑点上限、deadline、blockhash 剩余高度、pool/mint 白名单全部 fail-closed。daily cap 将 `prepared/submitted/confirmed/failed_ambiguous` 一并占用，避免并发或超时后的重复花费。
- 五检 `simulate / quote / basis / RPC health / wallet balance` 任一失败均拒绝；sidecar 随后还会亲自再次调用 `simulateTransaction`。
- kill switch 持久化到 ledger 并切换为 `EXIT_ONLY`。只允许 `decrease / collect / close`，以及明确标注 `reduces_risk=true` 的 `swap`。
- dry-run 只生成带零签名占位的 unsigned legacy transaction，设置 `sigVerify=false` 调用 `simulateTransaction`；报告显式记录 `signed=false`、`broadcast_count=0`、`keystore_loaded=false`。

## Token-2022 / Scaled UI

mint 必须运行时读取并验证 owner 与 `jsonParsed` mint 数据。数量保持三个不混用的概念：

1. `raw_amount`：链上整数；
2. `accounting_amount = raw / 10^decimals`；
3. `ui_amount = accounting_amount × active_scaled_ui_multiplier`。

估值必须显式声明价格是 `per_ui_unit` 还是 `per_accounting_unit`；语义缺失直接拒绝。未来 multiplier 只在链上配置的生效时间到达后切换，UI → raw 转换不能精确表示时拒绝，防止静默舍入。

## 本轮禁止项

本轮不得创建真实 keystore、启动 unit、调用 signer、签名或调用 `sendTransaction`。真实广播即便代码边界已具备，仍需指挥官逐次放行。
