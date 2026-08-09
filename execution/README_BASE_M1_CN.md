# Base M1 单仓执行器（C4）

状态：实现与测试完成；`LIVE_TRADING` 默认关闭；本轮未创建真实钱包、未签名、未广播。

## 边界

- 只允许 Base（chain id 8453）。
- 只允许 Uniswap v3 NPM 与 Aerodrome 官方 Slipstream NPM 部署。
- 单仓、池/Token/NPM 三层白名单、动作白名单、单笔与单日限额。
- 开仓使用 ApproveExact；退出顺序为 decrease → collect → burn → approve(0)。
- kill switch 将执行器置为 `EXIT_ONLY`，此后开仓、approve、mint 一律拒绝。
- 五项预检 simulate / quote / basis / RPC health / wallet balance 必须全真。

Aerodrome 地址与 ABI 以官方仓库为依据：

- <https://github.com/aerodrome-finance/slipstream#deployments>
- <https://github.com/aerodrome-finance/slipstream/blob/main/contracts/periphery/interfaces/INonfungiblePositionManager.sol>

## 密钥与进程隔离

正式部署时创建两个不可登录 Unix 用户：`lpbot-strategy` 和
`lpbot-executor`。encrypted keystore 与密码文件应由 executor 用户拥有，均为
`0600`；目录为 `0700`。策略进程只能向经过鉴权的本机 intent 通道写入，不能
读取 `/etc/lpbot-executor` 或 `/var/lib/lpbot-executor`。示例 systemd unit 已设置
独立用户、`UMask=0077`、`ProtectSystem=strict`、`ProtectHome=true`。

验收命令（不得替换为真实密钥）：

```text
stat -c '%U %G %a %n' /etc/lpbot-executor/keystore.json /etc/lpbot-executor/password
sudo -u lpbot-executor test -r /etc/lpbot-executor/keystore.json
sudo -u lpbot-strategy test ! -r /etc/lpbot-executor/keystore.json
systemctl show lpbot-base-m1-executor -p User -p Group -p UMask -p ProtectSystem -p ProtectHome
```

签名器仅调用 `cast mktx --keystore ... --password-file ...`，子进程环境只保留
`PATH`；没有私钥、助记词或 seed 的环境变量入口。

## 双重解锁

广播边界必须同时满足：

1. 进程启动环境明确设置 `LIVE_TRADING=true`；
2. 启动参数明确传入精确确认串 `CONFIRM_BASE_M1_LIVE_BROADCAST`。

缺任一条件，`Broadcaster.broadcast()` 都抛出 `LiveTradingLocked`，计数保持 0；
`BaseM1Executor.execute()` 在签名前再次检查同一边界。C4/C5 不设置这两个条件。

## 回执与故障处理

RPC 带指数退避重试；nonce 从 pending 状态串行预留，失败后强制刷新；gas 使用
链上 estimate 并在真实路径加 20% buffer；EIP-1559 使用 fee history，max fee
按 `2 × base fee + priority fee`。回执必须 status=1 且达到 3 confirmations，期间
block hash 变化、回执消失或移动均按 reorg 失败。Solidity `Error(string)` 与
`Panic(uint256)` revert data 可解码，所有成功结果必须 fsync 回填 JSONL ledger。
