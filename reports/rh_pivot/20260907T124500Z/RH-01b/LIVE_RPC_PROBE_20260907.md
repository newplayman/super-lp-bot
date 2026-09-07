# Robinhood Chain 公开 RPC 实测证据（2026-09-07 19:0x UTC，主脑亲跑）

授权：用户 2026-09-07 本轮明确授权"连接 Robinhood 免费公开 RPC 做只读探测，可用多个免费节点组轮循池"。全程只读方法，无签名、无广播、无钱包、无付费服务。

## 1. 链身份与活性 — VERIFIED

| 项 | 实测值 |
|---|---|
| endpoint | `https://rpc.mainnet.chain.robinhood.com` |
| `eth_chainId` | `0x1237` = **4663** ✓ 与 PRD §3.3 一致 |
| `web3_clientVersion` | `nitro/v3.11.4-rc.3-7d5ac27/linux-amd64/go1.25.14`（Arbitrum Nitro，印证 PRD 的 L2 定位） |
| 链头高度 | 57,071,656 |
| 延迟 | p50 270ms，8 次串行 0 错误 |

## 2. 种子地址链上核验 — 五个全部 ATTESTED

| 名称 | 地址 | 运行时代码 | 核验结论 |
|---|---|---|---|
| WETH | `0x0Bd7…AD73` | 2202 B | `symbol="WETH"`, `decimals=18`, `name="WETH"` |
| USDG | `0x5fc5…1d168` | 170 B | **EIP-1967 代理**，实现 `0x68184c449e1a8f34fa18d289737129fd27b66f8f`；`symbol="USDG"`, **`decimals=6`**, `name="Global Dollar"` |
| V3 factory | `0x1f7d…2efa` | 24535 B | 存在 |
| V3 position manager | `0x7399…de0d3` | 24384 B | 存在 |
| 候选池 USDG/WETH | `0x52e6…71ca` | 22142 B | **身份闸通过**（见下） |

## 3. 候选池身份闸 — PASS（T07 正向）

```
token0      = 0x0bd7d308f8e1639fab988df18a8011f41eacad73  (WETH)
token1      = 0x5fc5360d0400a0fd4f2af552add042d716f1d168  (USDG)
fee         = 100 (0.01%)      tickSpacing = 1
liquidity   = 10,661,985,504,065,420,007
factory.getPool(token0, token1, 100) -> 0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca   匹配 ✓
```

池状态：`sqrtPriceX96=3953938817749275760872870`，`tick=-198118`；按正确精度归一 **1 WETH = 2,490.58 USDG**。池内余额 **5,910.53 WETH + 17,166,110.29 USDG**，约 **3,190 万美元**规模。是真实活跃池，可作为 RH-04 首个 CORE Shadow 标的。

## 4. 三个必须写进设计的实测约束

### 4.1 USDG 是 6 位小数，不是 18 —— 错了会差 10¹² 倍

`decimals()` 实测返回 **6**。按两边都 18 位计算，池价会算成 `0.000000` 而非 `2,490.58`。PRD §9.2 只警告了股币 multiplier 的单位混淆，**未覆盖稳定币 decimals 不对称**。RH-03a 装配器与任何价格/TVL 计算必须从链上读 `decimals()`，禁止假设 18。

### 4.2 `robinhood.drpc.org` 是假绿端点 —— 正是 PRD §7.4 所防的形态

| 方法 | HTTP | 结果 |
|---|---|---|
| `eth_chainId` | 200 | `0x1237`（**正确**，20ms，比官方快 13 倍） |
| `eth_blockNumber` | 400 | `-32601 the method does not exist/is not available` |
| `eth_getBlockByNumber` | 400 | 同上 |
| `eth_call` | 400 | 同上 |

只用 `eth_chainId` 做健康检查会把它判为"健康的第二个独立 provider"，从而**满足 LIVE 的多源冗余门槛**，实际却零可用能力。这实证了 PRD §7.4"能力不是一个布尔值"与 §8.3"主备指向同一后端不算两套独立证据"的必要性：**健康检查必须逐方法验证，不能只探 chainId**。

结论：该端点 `discovery/state_read/history_read` 全部 `UNSUPPORTED`，**不得计入 provider 独立性计数**。

### 4.3 官方端点无 archive —— 只能正向采集

```
eth_call @ 链头      OK
eth_call @ -128      OK
eth_call @ -1,000    OK
eth_call @ -10,000   metadata is not found
eth_call @ -100,000  metadata is not found
```

历史状态窗口约 **1,000 ~ 10,000 区块**。按 PRD §8.2：`HISTORY_UNAVAILABLE`，**使用正向采集，不伪造历史**。

`eth_getLogs` 可用且无区块跨度硬限，但**单次返回上限 10,000 条日志**：span=1 → 7 条，100 → 139 条，1000 → 1322 条，10000 → 超限报错。按此速率，安全窗口约 **7,000 区块/次**，采集器需自适应二分降 span。

## 5. 当前 provider 独立性结论

**只有 1 个可用 provider。** PRD §8.3：READONLY 阶段可暂用公开单点；**LIVE 不允许该单点成为唯一可用数据源**。若要上 LIVE，必须再找到至少一个逐方法验证通过的独立后端。已探测但不可用的候选：`rpc.robinhood.com`、`rpc.ankr.com/robinhood`、`robinhood-mainnet.public.blastapi.io`、`4663.rpc.thirdweb.com`、`robinhood.gateway.tenderly.co`、`robinhood.publicnode.com`、`rpc.robinhoodchain.com`（DNS 不存在或 HTTP 错误）。
