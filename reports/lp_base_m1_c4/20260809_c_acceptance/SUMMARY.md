# FIX-C4 Base M1 最小执行器验收

日期：2026-08-09

结论：实现与定向测试通过；本阶段没有创建或读取真实钱包，没有签名，没有广播，没有链上交易。

## 已实现

- Base chain id 8453；Uniswap v3 / Aerodrome Slipstream NPM 白名单；单仓池与 Token 白名单。
- `mint`、`decreaseLiquidity`、`collect`、`burn`、ApproveExact、退出 `approve(0)`。
- Uniswap 与 Slipstream 各自正确的 mint ABI；decrease selector 为官方接口的 `0x0c49ccbe`。
- simulate / quote / basis / RPC health / wallet balance 五检，任一 false 即拒绝。
- single/daily notional cap、75 bps 滑点硬限、1 小时内 deadline、三类 ID、idempotency、fsync ledger。
- gas estimate + 20% buffer、EIP-1559、RPC 重试、pending nonce、回执/revert 解码、3 confirmations 与 reorg 检测。
- kill switch → `EXIT_ONLY`，只允许 decrease / collect / burn / revoke。
- encrypted keystore 经 `cast mktx --keystore --password-file` 签名；子进程不接收策略环境或密钥环境变量。
- `LIVE_TRADING=true` 与启动确认串必须同时存在；否则在签名前及广播边界均抛异常。

## TDD 证据

- `tests/test_base_m1_executor_c4.py`：19 passed。
- C4 + C5 联合定向：21 passed。
- 未解锁广播的三种组合全部抛 `LiveTradingLocked`，fake transport 的 send 调用数为 0。
- ApproveExact、ApproveMax 拒绝、双 Token approve(0)、五检逐项 false、白名单、cap、ID、deadline、EXIT_ONLY、keystore 0600、cast 命令隔离、回执与 revert 解码均有测试。

## 隔离验收

完整部署与权限核对步骤见 `execution/README_BASE_M1_CN.md`，systemd 示例见
`deploy/systemd/lpbot-base-m1-executor.service.example`。本轮只交付代码和示例，未创建
`lpbot-executor` 用户，未接触任何现有 keystore。

## 安全计数

- real wallet access: 0
- raw private key / mnemonic: 0
- signed transactions: 0
- `eth_sendRawTransaction`: 0
- broadcast_count: 0
- live daemon started: 0
