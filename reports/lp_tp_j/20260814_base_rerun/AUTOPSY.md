# LP funnel autopsy — top-200 / all Stage-1 coarse-pass

结论：本批终闸完整合取后 `accepted=0`；分析的是 92 个 Stage-1 粗筛通过池中的 30 个终端记录。
未改动任何阈值；resolution/status 被单列为技术完整性闸，防止统计表遗漏终闸条件。

## 1. 逐闸衰减

| 闸 | 进入 | 本闸淘汰 | 存活 |
|---|---|---|---|
| resolution/status（技术完整性） | 30 | 12 | 18 |
| 资产质量 tier | 18 | 0 | 18 |
| yield_cover | 18 | 2 | 16 |
| 多窗口 stable | 16 | 10 | 6 |
| entry_eligible | 6 | 1 | 5 |
| NetCover | 5 | 5 | 0 |
| PositionCap | 0 | 0 | 0 |

entry_eligible 首次淘汰子原因：REWARD_PERSISTENCE_SURROGATE_WEAK=1。
NetCover 首次淘汰细分：输入缺失 4；可计算但 `<1.0` 1。

## 2. 每闸最接近通过的 5 个池

### resolution/status（技术完整性）

| 池 | Llama ID | 差距 |
|---|---|---|
| CBETH-CBBTC | 79369b35-dd99-4d68-b989-31c258fc40ab | ambiguous_multi_factory_pool |
| EURC-USDC | fbce5857-69c4-4142-938b-62bdc9444967 | ambiguous_multi_factory_pool |
| RECALL-USDC | 4e01eb90-f885-40e9-a484-3624be86fd66 | ambiguous_multi_factory_pool |
| USDC-ACU | adcae740-c286-43a4-b71d-8c301a4ac526 | observed_range_gte_100 |
| USDC-CBBTC | 6f1786fc-a22f-4c46-91cd-d3792479bdc2 | ambiguous_multi_factory_pool |

### 资产质量 tier

| 池 | Llama ID | 差距 |
|---|---|---|
| — | — | 没有到达本闸后失败的池 |

### yield_cover

| 池 | Llama ID | 差距 |
|---|---|---|
| BNKR-WETH | 2bb5e61e-0ed0-4c05-b791-6e3aa146875c | 0.362047，差 0.637953 |
| TRUST-USDC | e351f2a6-2bcd-4a74-9d44-fc9795fce9c8 | 0.156597，差 0.843403 |

### 多窗口 stable

| 池 | Llama ID | 差距 |
|---|---|---|
| AVNT-USDC | eb27d0be-9de4-4ed9-8d36-a754e18d3358 | enter_frac=0.667，差 0.033 |
| EURC-CBBTC | 29b739e4-5e90-40c3-9fe8-31f67a6be60c | enter_frac=0.667，差 0.033 |
| EURC-USDC | 847c874f-d4e7-47ed-8870-97d2f24a8767 | enter_frac=0.667，差 0.033 |
| HYPE-WETH | 2d73e593-f529-4373-aca7-58b4c552517b | enter_frac=0.667，差 0.033 |
| SOSO-USDC | d1a265ef-1c32-4d98-b2d6-a473447286a2 | enter_frac=0.667，差 0.033 |

### entry_eligible

| 池 | Llama ID | 差距 |
|---|---|---|
| VIRTUAL-WETH | 8d182f18-a49e-4afd-9fcc-4d70ea2f6e0f | SURROGATE_WEAK; score=0.00; measured=0.00h; REWARD_PERSISTENCE_SURROGATE_WEAK |

### NetCover

| 池 | Llama ID | 差距 |
|---|---|---|
| WETH-USDC | 3ea03bb2-0fda-4280-9389-f76c5b75ff2b | 0.808238，差 0.191762 |
| MSUSD-USDC | aae6cc3a-783b-4a76-bea7-c3edccd28d62 | 输入缺失：PERMANENT_FAIL_CLOSED |
| WETH-CBBTC | d632293f-ebd7-4316-850e-9b5dd4d992f3 | 输入缺失：PERMANENT_FAIL_CLOSED |
| WETH-DIEM | 6d3763f2-b4c3-4c95-ae28-4248cb9c0358 | 输入缺失：PERMANENT_FAIL_CLOSED |
| WETH-USDT | 577caee3-254c-405d-a642-17e6b47a52b6 | 输入缺失：PERMANENT_FAIL_CLOSED |

### PositionCap

| 池 | Llama ID | 差距 |
|---|---|---|
| — | — | 没有到达本闸后失败的池 |

## 3. 独立核查交叉验证

2026-08-09 一次性核查只保留了汇总数 `213`，没有保留 213 个池的身份列表或原始快照，因此无法诚实地声称逐个复原历史成员。下表是在本次随报告保存的 DefiLlama 快照上，用该文档披露的 H=30d、50U、65% fee、统一 50% reward haircut 和 fixed-cost-only 公式重跑的当前 cohort；它不是主漏斗入场闸。

当前重跑 cohort=200，其中 stablecoin=13；逐池结果全部保存在 `AUTOPSY.json.independent_cohort.rows`。

| 池 | 链/项目 | IL 容忍 APR | 死点 |
|---|---|---|---|
| MSUSD-USDC | Base/aerodrome-slipstream | 23.051% | netcover:输入缺失：PERMANENT_FAIL_CLOSED |
| XSGD-USDC | Base/aerodrome-slipstream | 29.563% | AFTER_STAGE1:NOT_PRESENT_IN_TERMINAL_COHORT |
| VCHF-USDC | Solana/raydium-amm | — | BEFORE_MAIN_FUNNEL:M1_A_FORBIDDEN_SOLANA |
| VCHF-USDC | Base/aerodrome-slipstream | — | STAGE1_COARSE:vol1d 572 < 50000 |
| CADC-USDC | Base/aerodrome-slipstream | 30.509% | STAGE1_COARSE:TVL 129000 < 150000 |
| USDC-AVAIL | Base/aerodrome-slipstream | 39.343% | STAGE1_COARSE:TVL 125530 < 150000 |
| XSGD-USDC | Solana/orca-dex | — | BEFORE_MAIN_FUNNEL:M1_A_FORBIDDEN_SOLANA |

差异来源：历史核查覆盖 Base+Solana 且 TVL 门槛为 100K；主漏斗只支持 Base 两协议、M1 粗筛 TVL 为 150K、vol1d 为 50K，还要求资产质量、链上多窗口、reward persistence、完整 NetCover 和 PositionCap。Solana 因 M1-A 明令禁止而停在主漏斗之前。

## 4. 可审计性

- scanner as_of: `2026-08-14T08:16:58.647010+00:00`
- scanner cycle RPC health: `UNKNOWN`（健康状态不参与放宽任何闸）
- terminal conjunction 与存储 accepted 计数一致：`True`
- JSON 保留每个终端池的逐位 gate bits、first failure、差距输入，以及独立 cohort 的逐池 death。
- 本工具仅以 SQLite `mode=ro` 读取；无钱包、签名、广播或阈值写入路径。
