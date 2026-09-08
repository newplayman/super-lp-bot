# 第二 RPC 提供方核验：LIVE 闸的单点阻塞已解除（2026-09-08 14:5x UTC，主脑亲跑）

## 结论

PRD §8.3 要求 `usable_provider_count >= 2` 才允许 LIVE。此前实测只有 1 个，LIVE 闸因此
一直 BLOCKED。本次核验得到 **3 个全方法可用的独立提供方**，该项阻塞解除。

**这不代表 LIVE 可以开。** 另一个阻塞 `CAPITAL_POLICY_CONFLICT`（三桶 50/30/20 与旧
100U 单账户口径冲突）仍在，且那是用户的资金授权决定，不是工程问题。Stage A / B / C
的观测门槛也全部未达。本条只是把一个与经济无关的工程阻塞挪开。

## 来源不是猜的

端点取自 ethereum-lists 官方链注册表 `chainid.network/chains.json` 中 chainId 4663
（`Robinhood Chain`，原生币 ETH）的 `rpc` 字段，不是我拼凑的域名。

## 逐方法核验（PRD §8.3 要求按方法而非按提供方判定）

固定在同一区块 **57774374**（当前高度回退 30 块，确保各方都已同步）以便结果可比。

| 提供方 | chainId | blockNumber | eth_call | getBlockByNumber | eth_getLogs | 判定 |
|---|---|---|---|---|---|---|
| `rpc.mainnet.chain.robinhood.com` | 284ms | 265ms | 291ms | 291ms | 515ms | 可用 |
| `robinhood-rpc.publicnode.com` | 100ms | 88ms | 113ms | 105ms | 91ms | 可用（最快） |
| `rpc.ordofi.network` | 232ms | 207ms | 259ms | 474ms | 239ms | 可用 |
| `rpc.arrowrpc.com` | FAIL | FAIL | FAIL | FAIL | FAIL | **不可用**（HTTP 530，全方法） |

`eth_call` 用的是 SGOV/USDG fee-3000 池的 `slot0()`，即本项目真实会打的调用，不是空探针。

## 一致性：固定区块上无 SOURCE_DISAGREEMENT

同一固定区块 57774374 上，三个可用提供方对 `eth_chainId` / `eth_call` /
`eth_getBlockByNumber` / `eth_getLogs` 的返回 **sha256 摘要逐字节一致**。按 PRD §9.3，
不一致本应触发 `SOURCE_DISAGREEMENT` 并禁止新仓；本次未触发。

### 更正：`eth_blockNumber` 三家不一致，但那不是分歧

初稿把 `eth_blockNumber` 也算进「五个方法逐字节一致」，**这是错的**。该方法返回各家
自己的链头，本来就该不同。实测三轮并列取样：

| 轮次 | primary | publicnode | ordofi | 极差 |
|---|---|---|---|---|
| 1 | 57775042 | 57775048 | 57775050 | 8 块 |
| 2 | 57775087 | 57775094 | 57775097 | 10 块 |
| 3 | 57775132 | 57775185 | 57775186 | 54 块 |

**由此得到一条本来不在预期内的发现：我们正在用的主端点
`rpc.mainnet.chain.robinhood.com` 每一轮都是三家里最落后的**，落后 6 到 54 块；
而 `publicnode` 既最快（88–113ms，主端点是 265–291ms）又最接近链头。

两条实现要求：

1. **一致性比对只能在固定区块上做。** 拿 `eth_blockNumber` 去比对会把正常的同步延迟
   误报成 `SOURCE_DISAGREEMENT`，从而无谓地禁掉新仓。RH-01d 的 `detect_disagreement`
   只对显式传入的 `consensus_methods` 生效，正是为此。
2. **链头落后会系统性影响时效性判定。** 采集器当前只用主端点，其读到的「最新」状态
   可能已落后 54 块。这对 `reference_age` 类判定的影响尚未量化，须在 Stage B 前评估。

## 这条证据的边界（不得夸大）

0. **链头落后的影响未量化。** 见上节更正。
1. **这是一次时点快照，不是可用性序列。** 三个提供方此刻全通，不等于观测窗口内持续可用。
   `arrowrpc` 恰好证明注册表里的端点会挂。持续可用性需要把它们接进轮循池后按周期记录，
   这正是 RH-01d（`lp_rh_provider_pool_v1_readonly`）在建的东西。
2. **一致性只在一个区块、五个方法上验证过。** 归档节点深度、日志区块跨度上限、
   速率限制各家不同，均未测。`eth_getLogs` 只查了单区块，宽区间行为未知。
3. **采集器目前仍只用主端点。** 本报告不改变任何运行中进程的配置。
4. 三家的独立性只到「不同域名与运营方」这一层；是否共用同一上游基础设施未核实。
