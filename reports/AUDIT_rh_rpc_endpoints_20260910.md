# AUDIT：Robinhood Chain (4663) RPC 端点穷尽调研与主端点切换（2026-09-10）

- 触发：生产采集器大面积超时，Stage A 覆盖率从 0.9984 掉到 0.9584。
- 性质：只读探测 + 一次生产参数切换（无代码改动）。
- 执行：主脑亲测。三路 gemini worker 调研全部无产出，原因见文末。

## 一句话结论

**当前在用的端点是三个可用端点里最差的一个，而且当天已经坏掉。**
切到 `robinhood-rpc.publicnode.com` 后，采样从 ~45 秒间隔恢复到 15.0 秒恒定，
203 次 RPC 零错误。

## 一、稳定性实测（40 轮 × 3 个真实调用，模拟采集器）

调用与采集器每轮实际发出的一致：`eth_blockNumber`、`eth_call slot0()`、
`eth_call liquidity()`。一轮三个调用全成功才算成功。

| 端点 | 成功轮 | 失败轮 | 成功率 | p50 | p95 | max |
|---|---:|---:|---:|---:|---:|---:|
| `rpc.mainnet.chain.robinhood.com`（原主端点） | 15 | 25 | **37.5%** | 6054ms | 14861ms | 28835ms |
| `rpc.ordofi.network` | 40 | 0 | **100%** | 681ms | 1362ms | 2018ms |
| `robinhood-rpc.publicnode.com` | 40 | 0 | **100%** | **308ms** | 404ms | 438ms |

单次探测（`eth_chainId` / `eth_blockNumber` / `eth_call slot0`）：

```
rpc.mainnet.chain.robinhood.com   FAIL / FAIL / OK          9962ms
rpc.ordofi.network                4663 / 59161825 / OK       240ms
robinhood-rpc.publicnode.com      4663 / 59161824 / OK       109ms
```

两个健康端点的区块号只差 1，都跟得上链头。

## 二、全部候选与排除理由

### 官方注册表（`chainid.network/chains.json`，chainId 4663 共 5 条）

| 端点 | 结论 |
|---|---|
| `robinhood-rpc.publicnode.com` | **可用**，最快 |
| `rpc.ordofi.network` | **可用**，次之 |
| `rpc.mainnet.chain.robinhood.com` | 当天大面积超时，37.5% 成功率 |
| `rpc.arrowrpc.com` | HTTP 530，已死（2026-09-08 探测时即已死） |
| `wss://robinhood-rpc.publicnode.com` | WebSocket，采集器用不上 |

### 注册表之外（区块浏览器与聚合服务，全部逐个实测）

| 候选 | 结果 |
|---|---|
| `robinhood.drpc.org` | `eth_chainId` **返回 0x1237 (4663)**，但 `eth_blockNumber` / `eth_getBlockByNumber` / `eth_call` 全部 `-32601 method does not exist/is not available` — 免费层只开放 chainId 与 net_version，对采集器无用 |
| `robinhoodchain.blockscout.com/api/eth-rpc` | 裸请求 403；补浏览器 header 后变 **429 Too many requests** — 端点真实存在但限流，不能每 15 秒打 |
| `rpc.robinscan.io` | HTTP 401，需认证 |
| `robinscan.io` / `hoodscan.co` / `stonkscan.io` 的 `/api/eth-rpc` | HTTP 404 |
| `lb.drpc.org/ogrpc?network=robinhood` | HTTP 403 |
| `robinhood-mainnet.public.blastapi.io` | URLError（无此主机） |
| `1rpc.io/robinhood` | HTTP 400 `unknown network` |
| `robinhood.gateway.tenderly.co` | HTTP 404 |
| `robinhood.rpc.nodies.app` | URLError |
| `rpc.ankr.com/robinhood` | HTTP 403 |
| `4663.rpc.thirdweb.com` | RPC_ERR |
| `robinhood.publicnode.com`（无 `-rpc`） | HTTP 403 `unsupported platform` |
| `sequencer.mainnet.chain.robinhood.com` | RPC_ERR — 是排序器不是通用 RPC |

**验收硬线**：任何候选的 `eth_chainId` 必须等于 4663，不等一律丢弃。
拿错链的端点比没有端点危险得多（PRD T01 防的正是 chainId 混入）。

## 三、切换记录

```
采集器 PID 1168725
RH_RPC_PRIMARY=https://robinhood-rpc.publicnode.com
```

纯环境变量，**未改任何代码或配置文件**。去掉该变量重启即回退。

切换前后：

| | 切换前 | 切换后 |
|---|---|---|
| 采样间隔 | 被拉长到 ~45s | **15.0s 恒定**（min=max=avg） |
| RPC 错误 | 50%（06:00 后 20 次里 10 次） | **0 / 203** |
| 延迟 | p50 6054ms | avg 123ms，max 160ms |
| 采集器健康标志 | DEGRADED 反复 | 全部 NORMAL |

**操作失误记录**：第一次切换失败，断采 37 秒。`kill` 旧进程后只等了 4 秒就启动新的，
而旧进程正在优雅退出（还在处理当轮），pid 文件未清空，新进程判定
`collector already running` 直接 Exit 2；随后旧进程才退出并清空 pid 文件，
**结果两个都没了**。第二次改用 `setsid` 并显式轮询等待 pid 文件清空后再启动。

**教训**：停一个带 pid 文件互斥的守护进程，必须等它真的退出、pid 文件真的清空，
再启新的。后续切换 shadow daemon 时按此执行，零中断。

## 四、对 PRD 的意义

`SINGLE_PROVIDER_NOT_ALLOWED_FOR_LIVE` 是 LIVE 闸门的硬前提（≥2 个独立提供方）。

现在有 **2 个实测可用且独立运营** 的端点（publicnode 与 ordofi），
理论上满足这条。但需注意：

- 采集器当前**仍是单端点**（`RH_RPC_PRIMARY` 一个变量），没有自动主备切换；
  `lp_rh_capabilities_v1_readonly.py:306` 已经读 `RH_RPC_SECONDARY`，
  但采集器本身没接。**接双端点是一个待做的工程项**。
- `scripts/lp_rpc_pool_v1_readonly.py` 有一套轮转端点池，
  但**只配了 base/ethereum/arbitrum/optimism/solana，没有 RH 链**。
- 本次事故证明单端点的脆弱性：一个上游故障就让 Stage A 的两个 blocker
  同时恶化（coverage 0.9984→0.9584，fee_growth 非空率跌破 0.99）。

## 五、三路 gemini 调研为何无产出（记下来，别再兜这个圈子）

同时派了三路做联网调研：本机 vps104、research13、research66。
**三路全部无有效产出**：

- vps104 那路：`--cwd /tmp` 让它用 ripgrep 在 `/tmp` 里翻本地文件
  （stderr 全是 `Permission denied`），最后试图访问仓库被工作区限制拒绝。
- research13 / research66：`exit_code=0` 完成，但 `stdout` 为空，
  报告没有落到任何可取回的位置。

**结论：gemini-worker 不适合做联网调研任务。** 它倾向于本地文件搜索，
且 readonly 模式下的文本产出取不回来。这类工作主脑自己用 `curl` / `urllib`
探测更快也更可靠——本报告的全部数据都是这么来的，耗时约 10 分钟。
