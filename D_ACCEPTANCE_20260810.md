# TP-D 验收：RPC 效率 + 闸位校准 + C6 前置

RPC resolver 的真实同批 92 池对照为底层 HTTP `1297 → 130`（`-89.98%`）、`182.326s → 21.613s`（`-88.15%`）；完整 cycle 的同口径保守预算为 `18675 → 18497`（`-0.95%`），资格端点 run 实测 12,843 次、`4721.582s`，较昨夜产物跨度约 92.1 分钟缩短约 `14.6%`，但两次复跑最终 RPC health 都是 `DEGRADED`。
多窗口在 NORMAL 资格 run 的 47 个同批可控池中由 6 窗 stable `29` 变为 10 窗 stable `38`，发生 `2` 个过→不过和 `11` 个不过→过；LVR 因证据不足维持 `0.5`，92 池五档敏感性均为 0 个过 NetCover/终闸，最新 68 池仍 `accepted=0`。
C6 四项前置已完成；C6 仍缺至少 1 个全闸候选与指挥官配置真实钱包/keystore 后的余额和 gas 验收，此外本包 D4 的 `RPC NORMAL` 终态未满足。

## 验收结论

| FIX | 结论 | 核心证据 |
|---|---|---|
| D1 Multicall3 | **PASS** | runtime 校验、显式串行回退、batch=60、per-call failure、resolver/scanner 接入、92 池逐字段差异 0 |
| D2 10 窗离散化 | **PASS** | `STABLE_MIN_FRAC=0.7` 未改；同 tip 前 6 窗反事实；双向翻转完整；保守预算不超旧版 |
| D3 LVR 系数 | **PASS（常量不改）** | 无可核验来源；真实 swap 近似提示可能低估风险但证据不足；`0.5` 保持 |
| D4 RPC NORMAL N1 | **FAIL** | 两次完整 run 均 68 scored / accepted=0，但终态分别 6/11、2/4 impaired，不能宣称 NORMAL |
| D5 C6 前置 | **PASS** | 系统用户/空 keystore、只读对账、3 NPM 启动核验、外部依赖台账完成 |

整体判定：**TP-D 部分通过；D1/D2/D3/D5 通过，D4 未满足硬验收。** 数值复跑完整、没有因健康状态放宽任何闸；D4 失败仅表示不能把这批称为“RPC NORMAL 下的复核”。

## D1：Multicall3

- 地址：`0xca11bde05977b3631167028862be2a173976ca11`。
- 启动 runtime：3,808 bytes；Keccak-256：`0xd5c15df687b16f2ff992fc8d767b4216323184a2bbc6ee2f9c398c318e770891`。
- 首批前必须经同一 `RpcPool` 执行 `eth_getCode`；空代码、读取/解码失败记录 `FALLBACK_SERIAL` 并逐项 `eth_call`，不静默跳过。
- `aggregate3(Call3[])` 强制每项 `allowFailure=true`；默认 batch `60`；失败子调用不吞相邻结果。
- 92 池真实 resolver 同批对照：

| 指标 | 串行 | Multicall3 | 变化 |
|---|---:|---:|---:|
| HTTP 尝试 | 1,297 | 130 | -89.98% |
| `eth_call` HTTP | 1,196 | 23 | -98.08% |
| wall-clock | 182.326s | 21.613s | -88.15% |
| 成功分类 | 68 | 68 | 0 |
| 逐字段差异 | — | 0 | 完全等价 |

完整资格 run 中 Multicall3 预取 665 个逻辑子调用，形成 12 个 aggregate3 请求；serial fallback=0、per-call failure=0、cache hits=865。完整 cycle 的 12,843 次物理请求中 `eth_getLogs=12,645`，说明约 98.46% 的剩余请求不在 Multicall3 能力范围内；局部 8.44× 提速没有被夸大为全流程同倍提速。

证据：`reports/lp_multicall3/20260810_d1_acceptance/SUMMARY.md`、`reports/lp_tp_d/20260810_d4_top68_w10_normal/once_evidence.json`。

## D2：10 窗与 RPC 预算

`DEFAULT_N_WINDOWS=10`，`STABLE_MIN_FRAC=0.7` 原值未动；因此判定边界从 6 窗实际的 5/6=83.3% 恢复成字面 7/10=70%。每个完成 10 窗的 score record 保存同一 tip、同一观测中前 6 窗的反事实，不用两个市场时点归因离散化翻转。

### 预算账

两边均按 2,001-block inclusive 分片计算、均为 provider retry 前保守逻辑上界：

| 配置 | top | 窗口 | 上界请求 |
|---|---:|---:|---:|
| 改造前串行 | 92 | 6 | 18,675 |
| 改造后 Multicall3 | 68 | 10 | 18,497 |

改造后少 178 次（-0.95%）。top=69 的最坏工厂分叉模型会越过旧上界，因此按任务包要求降到 top=68，没有降低窗口、阈值或其他业务闸。资格 run 真实物理尝试为 12,843，低于该逻辑上界；第一次全端点 run 为 13,110。

### 同批分布

47 个有完整 10 窗的池：

- 6 窗 enter_frac：`0.167:2, 0.333:1, 0.500:6, 0.667:9, 0.833:18, 1.000:11`。
- 10 窗 enter_frac：`0.300:1, 0.400:2, 0.500:4, 0.600:2, 0.700:8, 0.800:14, 0.900:11, 1.000:5`。
- stable：`29 → 38`。

### 全部双向翻转

| 方向 | 池 | llama_pool_id | 6窗 n/frac | 10窗 frac | 归因 |
|---|---|---|---:|---:|---|
| 过→不过 | WETH-AAVE | `2641aaa3-d441-4718-b638-029d09ca1d14` | 5/6=0.833 | 0.600 | 新增四窗有 1 个进入，完整 6/10；更长同批测量揭示不稳定 |
| 过→不过 | USDC-AERO | `06a7ca71-dc68-495c-b1d8-5c708339f0ab` | 5/6=0.833 | 0.600 | 新增四窗有 1 个进入，完整 6/10；更长同批测量揭示不稳定 |
| 不过→过 | USDC-DIEM | `7944b313-e6ee-42b2-a5c8-a26446e37621` | 4/6=0.667 | 0.800 | 新增四窗全部进入，完整 8/10 |
| 不过→过 | WETH-USDC | `b99bcdf5-1350-4269-981e-0e9b5cccb007` | 4/6=0.667 | 0.800 | 新增四窗全部进入，完整 8/10 |
| 不过→过 | WETH-USDT | `577caee3-254c-405d-a642-17e6b47a52b6` | 4/6=0.667 | 0.800 | 新增四窗全部进入，完整 8/10 |
| 不过→过 | USDC-VVV | `c7d461f8-4ad8-42d8-a6b8-378fd8045660` | 4/6=0.667 | 0.800 | 新增四窗全部进入，完整 8/10 |
| 不过→过 | AVNT-USDC | `eb27d0be-9de4-4ed9-8d36-a754e18d3358` | 4/6=0.667 | 0.800 | 新增四窗全部进入，完整 8/10 |
| 不过→过 | EURC-USDC | `847c874f-d4e7-47ed-8870-97d2f24a8767` | 4/6=0.667 | 0.700 | 新增四窗 3 个进入，完整 7/10 |
| 不过→过 | WETH-USOL | `a09feb82-76db-4291-aea9-dc6e88343e09` | 3/6=0.500 | 0.700 | 新增四窗全部进入，完整 7/10 |
| 不过→过 | SOSO-USDC | `d1a265ef-1c32-4d98-b2d6-a473447286a2` | 4/6=0.667 | 0.700 | 新增四窗 3 个进入，完整 7/10 |
| 不过→过 | TOWNS-WETH | `f3ab8cab-927e-4aed-9cbf-00d95c5350d7` | 4/6=0.667 | 0.700 | 新增四窗 3 个进入，完整 7/10 |
| 不过→过 | WETH-REI | `7cb47e02-170a-4f9e-bdd4-9d1a9a65e65a` | 3/6=0.500 | 0.700 | 新增四窗全部进入，完整 7/10 |
| 不过→过 | BIO-WETH | `3709f4bb-2114-4742-907a-7bb5d58de274` | 3/6=0.500 | 0.700 | 新增四窗全部进入，完整 7/10 |

这些翻转来自更长的同批观察；业务阈值没有变。即使 stable 净增 9，终闸仍为 accepted=0。

完整机器清单：`reports/lp_tp_d/20260810_d4_top68_w10_normal/D2_D4_COMPARISON.json`。

## D3：LVR=0.5×IL

- git blame：`0.5` 首见于 `0541c1f` 的 W6 新文件；仓库没有论文、推导、回放或校准引用，因此是未获证明的初始假设。
- 真实 swap 近似：已提交 R4 的 115,680 条 Base Swap、3 个 WETH/USDC 池、每池 4 窗；12 窗全样本 `LVR/端点IL` 中位数 2.921119，25 bps 稳健子样本 9 窗中位数 2.652941。
- 该方向提示 0.5 可能低估风险，而非支持下调；但样本仅单一 24h/同资产，缺 CL tokenId、区间、库存、外部公允价且源边界有矛盾，不能用于定参。
- N1 同一 92 池：65 可算、27 fail-closed；系数 `{0, .25, .5, .75, 1}` 下 NetCover 过闸与终闸合取均为 0。0.5 重算与库内最大误差 `8.327e-17`。
- 决策：**未获充分证据，维持 `LVR_COEFFICIENT_MODEL=0.5`。**

证据：`reports/lp_lvr_coefficient_calibration/20260810_d3/SUMMARY.md` 及配对 CSV/JSON。

## D4：完整复跑

### 数值结果

资格端点 run：730 Stage-1 记录、93 个粗闸通过、按预算取 top=68、68 resolved/scored、47 个有完整 10 窗、accepted=0。逐闸：

| 闸 | 昨夜 92 池淘汰 | 本次 68 池淘汰 |
|---|---:|---:|
| resolution/status | 25 | 21 |
| asset_quality | 1 | 0 |
| yield_cover | 9 | 8 |
| multiwindow_stable | 20 | 6 |
| entry_eligible | 14 | 8 |
| NetCover | 23 | 25 |
| PositionCap | 0 | 0 |

本次到达 NetCover 闸的最好池为 USDC-CBBTC，`0.854595`；昨夜为 WETH-USDC，`0.820998`。绝对变化 +0.033597，仍明确低于 1.0；cohort 与市场时点已变化，不能把该变化归因给 RPC 或 LVR 调参。终闸合取复算 accepted=0，与存储计数完全一致。

### 健康失败

| run | 端点 | cycle | HTTP | health | impaired | max consecutive failures |
|---|---:|---:|---:|---|---:|---:|
| 全登记端点 | 11 | 4754.590s | 13,110 | DEGRADED | 6 | 10 |
| 四个预资格 getLogs 端点 | 4 | 4721.582s | 12,843 | DEGRADED | 2 | 2 |

四个端点在 run 前均通过同一池、同一 2,000-block 的 `eth_blockNumber + eth_getLogs` 探测；长周期仍发生 237 次 getLogs 失败并由 `RpcPool` 重试完成。两次均全量落库且未缺终端行，但任务要求的是最终 `NORMAL`，故 D4 **FAIL**。不再发起第三次长跑去追逐偶然的终点快照。

证据：`reports/lp_tp_d/20260810_d4_top68_w10_normal/`；第一次失败证据：`reports/lp_tp_d/20260810_d4_top68_w10/once_evidence.json`。

## D5：C6 前置

- 实际系统隔离：`lpbot-executor`、`lpbot-strategy` 均为 `/usr/sbin/nologin`；`/etc/lpbot-executor`、`/var/lib/lpbot-executor` 为 0700/executor owner；`keystore.json`、`password` 为 0600、0 字节空占位。
- 权限：executor 可读、strategy 不可读；systemd `disabled/inactive`、`LIVE_TRADING=false`、`UMask=0077`、`ProtectSystem=strict`、`ProtectHome=yes`。
- 对账 CLI：`cmd/lpbot-recon` 已去 stub，支持 C5 JSON 或 executor JSONL；RPC 仅白名单 `eth_chainId`、`eth_getTransactionReceipt`。C5 open/exit 对 mainnet.base.org 实跑均 PASS，链 ID 8453、signed=false、broadcast=0、hashes=0。
- Aerodrome NPM：3 个地址均为 24,542 bytes，SHA-256、`factory()`、`WETH9()` 与官方部署记录匹配；Base mainnet executor 启动时 fail-closed 核验。
- 依赖台账：`api.dexscreener.com`、`mainnet.base.org` 已登记为免费、只读、可降级，发送交易不在授权范围。
- C6 机器预检：6 PASS / 2 FAIL。剩余是 `accepted=0` 与未配置真实钱包/gas 余额探针；真实 keystore/口令、资金、签名、广播仍未执行。

证据：`reports/lp_d5_c6_preflight/20260810_acceptance/SUMMARY.md`。

## 回归与安全

- Python：`2958 passed, 14 skipped`。
- Go：`go test ./...` PASS。
- D1/D2/D3/D5 配对定向测试均 PASS。
- host 安全 umask 为 0077；Go 的 0644/0640 权限测试显式 chmod 后验证 fail-closed，未削弱生产权限校验。
- 三个受保护 PID `1349731 / 2077656 / 2082408` 在收口检查时均存活。
- 钱包/私钥生成或导入=0；签名=0；广播=0；M1-A=0；git push=0；计费服务=0。
