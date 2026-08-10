# FIX-D5：C6 前置四项验收（2026-08-10）

结论：D5 四项完成；本轮没有生成/导入私钥，没有读取钱包，没有签名，没有广播。
systemd executor unit 保持 `disabled/inactive`，`LIVE_TRADING=false`。

## 1. 系统用户与空 keystore 结构

- `lpbot-executor`：系统用户、shell `/usr/sbin/nologin`；
- `lpbot-strategy`：独立系统用户、shell `/usr/sbin/nologin`；
- `/etc/lpbot-executor` 与 `/var/lib/lpbot-executor`：
  `lpbot-executor:lpbot-executor`、mode `0700`；
- `keystore.json` 与 `password`：owner `lpbot-executor`、mode `0600`、大小均为
  **0 字节**。两者只是占位结构，不含 encrypted keystore、口令或任何私钥。

权限验收：

```text
lpbot-executor lpbot-executor 600 0 /etc/lpbot-executor/keystore.json
lpbot-executor lpbot-executor 600 0 /etc/lpbot-executor/password
executor_read=PASS
strategy_denied=PASS
UMask=0077
User=lpbot-executor
Group=lpbot-executor
ProtectHome=yes
ProtectSystem=strict
ActiveState=inactive
```

## 2. ledger ↔ 链上只读对账 CLI

`cmd/lpbot-recon` 已不再是 Phase 3 stub，可读取 executor JSONL ledger 或 C5
JSON artifact。它只允许 `eth_chainId` 与 `eth_getTransactionReceipt`，代码级拒绝
`eth_sendRawTransaction` 等其他方法。

对 C5 open/exit 两份产物分别连接 `https://mainnet.base.org` 实跑：RPC chain id
均为 8453；产物均为 `signed=false / broadcast_count=0 /
transaction_hashes=[]`，因此 ledger hash 数与链上应查回执数同为 0，结果均为
`PASS`。证据见 `C5_OPEN_RECONCILIATION.json` 和
`C5_EXIT_RECONCILIATION.json`。这只证明零广播事实一致，不把 C5 校准池升级为
C6 候选。

## 3. Aerodrome NPM 链上核验与启动硬检查

三个 NPM 均与官方 Slipstream README 的 Initial / Gauge Caps / Gauges V3 地址
一致。通过 Base 公共 RPC 读取到的 runtime 均为 24,542 bytes；SHA-256 与
`factory()` / `WETH9()` 逐项匹配。完整逐地址证据见 `NPM_VERIFICATION.md` 与
`npm_verification.json`。

`execution/base_m1_executor_v1.py` 已固化同一套预期 fingerprint。Base mainnet
执行器构造时会逐地址做 3 个只读探针；无代码、hash、factory 或 WETH9 任一不符
均立即 `PolicyRejected`，签名和广播不可达。

## 4. 外部依赖台账

`docs/ops/external-readonly-dependencies.md` 登记了：

- `api.dexscreener.com`：只读、免费、缺失时可降级并 fail-closed；
- `mainnet.base.org`：只读、免费、经免费 RPC pool 可降级；发送交易不在授权范围。

## 定向验证

- `go test ./cmd/lpbot-recon`：PASS；
- `pytest tests/test_lp_d5_c6_preflight_v1.py tests/test_base_m1_executor_c4.py`：
  `24 passed`；
- 真实只读 NPM probe：3 deployments PASS；
- 真实只读 C5 reconcile：open PASS、exit PASS；
- C6 机器预检：`PASS 6 / FAIL 2`；仅候选 `accepted=0` 与未配置钱包/gas
  余额探针保持 FAIL，详见 `preflight.json` / `preflight.md`；
- 受保护 PID `1349731 / 2077656 / 2082408` 验收后全部仍存活。

仍未完成且本轮禁止：真实 keystore/口令、钱包资金与 gas 验收、至少一个全闸候选、
C6 独立放行、签名、广播、启动 live executor。
