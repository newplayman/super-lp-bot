# Base Sepolia 武装演练 runbook（准备稿，禁止直接执行）

状态：今晚只完成链 ID 硬断言与只读 dry-run；签名、广播、钱包操作均未执行。任何真实测试网执行仍需指挥官逐次明确批准。

## 网络硬线

- 网络必须是 Base Sepolia，`eth_chainId` 必须精确等于 `84532`；C4 的 `assert_executor_chain_id` 对 `8453` 或任意其他值均拒绝测试网启动。
- 免费官方 RPC 示例为 `https://sepolia.base.org`，区块浏览器为 `https://sepolia-explorer.base.org`。来源：[Base 官方网络配置](https://docs.base.org/base-chain/quickstart/connecting-to-base)。
- 配置从 `configs/base_sepolia_smoke.example.json` 复制到仓库外；`dry_run_only=true`、`signing_enabled=false`、`broadcast_enabled=false`、`live_trading=false` 不得修改。

## 批准前可做的只读检查

```bash
python3 scripts/lp_base_sepolia_smoke_v1_readonly.py \
  --config configs/base_sepolia_smoke.example.json \
  --out reports/lp_base_sepolia_smoke/<UTC_STAMP>
```

预期产物为 `dry_run.json` 与 `dry_run.md`；RPC 方法白名单只含 `eth_chainId`、`eth_blockNumber`、`eth_getCode`、`eth_call`，`broadcast_count=0`。示例配置没有 NPM/token/pool，所以完整 mint→decrease→collect→revoke 模拟必须显示 `BLOCKED_CONTRACTS_NOT_CONFIGURED`，不能冒充已跑通。

## 指挥官批准后才可准备的测试网身份

1. 创建只用于 Base Sepolia 的独立、不可登录 executor 用户；不得复用主网身份。
2. 通过 Foundry 的交互式 `cast wallet import <account> --interactive` 生成加密 keystore；不要在命令行、环境变量、文档或 shell history 中放私钥。Foundry 官方建议测试网使用 encrypted keystore，并将生产环境与测试环境密钥分离：[Foundry key management](https://www.getfoundry.sh/guides/best-practices/writing-scripts/#key-management)。
3. keystore 与 password file 归 executor 用户、权限 `0600`，目录 `0700`；strategy 用户必须不可读。
4. 从 Base 官方文档链接的免费 faucet 获取少量 Base Sepolia ETH；先在浏览器确认网络为 chain ID 84532。Base 官方 quickstart 给出了测试网 RPC、浏览器与 faucet 入口：[Base quickstart](https://docs.base.org/base-chain/quickstart/connecting-to-base)。
5. 把已核验的 Base Sepolia NPM、测试 token、pool 地址填入仓库外配置。必须先用 `eth_getCode`、token0/token1/fee/tickSpacing 只读核验身份。

## 获批后的完整演练顺序（今晚不执行）

1. 启动前读取 `eth_chainId` 并调用硬断言；不是 84532 立即退出，签名器 chain id 也必须为 84532。
2. 只读 preflight：余额/gas、合约身份、quote、basis、RPC health、PositionCap；任一失败停止。
3. ApproveExact → mint；等待成功回执与 3 confirmations；写入 fsync ledger 并对账 tokenId/本金。
4. decreaseLiquidity → collect → burn → 双 token `approve(0)`；每一步单独回执、3 confirmations、ledger 对账。
5. 最终验证 NFT 已 burn、allowance 为 0、测试 token/ETH 余额与 ledger 一致；保留交易哈希、回执、gas、revert 与重试证据。

停止条件：chain ID 漂移、RPC EXIT_ONLY/KILLED、合约身份变化、quote/simulation/balance 任一失败、回执重组、对账不一致、allowance 未清零。禁止自动切换到 Base mainnet。
