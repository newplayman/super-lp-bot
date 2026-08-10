# LP funnel autopsy — top-200 / all Stage-1 coarse-pass

结论：本批终闸完整合取后 `accepted=0`；分析的是 92 个 Stage-1 粗筛通过池中的 92 个终端记录。
未改动任何阈值；resolution/status 被单列为技术完整性闸，防止统计表遗漏终闸条件。

## 1. 逐闸衰减

| 闸 | 进入 | 本闸淘汰 | 存活 |
|---|---|---|---|
| resolution/status（技术完整性） | 92 | 25 | 67 |
| 资产质量 tier | 67 | 1 | 66 |
| yield_cover | 66 | 9 | 57 |
| 多窗口 stable | 57 | 20 | 37 |
| entry_eligible | 37 | 14 | 23 |
| NetCover | 23 | 23 | 0 |
| PositionCap | 0 | 0 | 0 |

entry_eligible 首次淘汰子原因：REWARD_PERSISTENCE_SURROGATE_WEAK=14。
NetCover 首次淘汰细分：输入缺失 0；可计算但 `<1.0` 23。

## 2. 每闸最接近通过的 5 个池

### resolution/status（技术完整性）

| 池 | Llama ID | 差距 |
|---|---|---|
| $OLIVIA2.0-USDC | 7a462d2c-b238-4fe2-9b56-034f48b7fd71 | observed_range_gte_100 |
| AERO-CBBTC | 3707d5ff-690b-423b-b3bb-4b7c7cca2990 | ambiguous_multi_factory_pool |
| AERO-CBBTC | 53b7036a-ec2a-494b-ad8e-ae53f35c20b8 | ambiguous_multi_factory_pool |
| BNKR-WETH | d7b0af87-0dba-4f48-8505-c801fccad673 | ambiguous_multi_factory_pool |
| CBETH-CBBTC | 79369b35-dd99-4d68-b989-31c258fc40ab | ambiguous_multi_factory_pool |

### 资产质量 tier

| 池 | Llama ID | 差距 |
|---|---|---|
| VVV-DIEM | c5bfb4c1-f788-4d05-8714-42c603c81534 | tier C：两腿中至少还需 1 个 major 资产 |

### yield_cover

| 池 | Llama ID | 差距 |
|---|---|---|
| CLANKER-WETH | 41273999-c799-420e-ae8b-2d8c6c6ab0fa | 0.931576，差 0.068424 |
| USDC-AERO | 31ed7657-e02c-427b-8e3e-c0bf24e6cb9b | 0.542084，差 0.457916 |
| USDC-AERO | 34185ab1-edf5-413a-b5bb-6d0fb2b4ef5f | 0.531440，差 0.468560 |
| WETH-USOL | a09feb82-76db-4291-aea9-dc6e88343e09 | 0.487860，差 0.512140 |
| USDC-AERO | afa3983e-5e2f-4c78-9175-e03df9062ce1 | 0.293112，差 0.706888 |

### 多窗口 stable

| 池 | Llama ID | 差距 |
|---|---|---|
| BIO-USDC | c82b6e92-d55c-484c-997f-fd54e1ea5705 | enter_frac=0.667，差 0.033 |
| BIO-WETH | 3709f4bb-2114-4742-907a-7bb5d58de274 | enter_frac=0.667，差 0.033 |
| BNKR-WETH | 2bb5e61e-0ed0-4c05-b791-6e3aa146875c | enter_frac=0.667，差 0.033 |
| CBBTC-ZEN | 913c44c2-5b5c-4dd8-9961-f1d1c112cee2 | enter_frac=0.667，差 0.033 |
| MSUSD-USDC | aae6cc3a-783b-4a76-bea7-c3edccd28d62 | enter_frac=0.667，差 0.033 |

### entry_eligible

| 池 | Llama ID | 差距 |
|---|---|---|
| CBETH-WETH | dc5b6771-96a6-4b38-b1c3-912544c23899 | SURROGATE_WEAK; score=0.00; measured=0.00h; REWARD_PERSISTENCE_SURROGATE_WEAK |
| HYPE-WETH | 2d73e593-f529-4373-aca7-58b4c552517b | SURROGATE_WEAK; score=0.00; measured=0.00h; REWARD_PERSISTENCE_SURROGATE_WEAK |
| ICP-WETH | 34987574-6e85-4046-ae9f-2b2b881008c6 | SURROGATE_WEAK; score=0.00; measured=0.00h; REWARD_PERSISTENCE_SURROGATE_WEAK |
| TBTC-CBBTC | e46e7064-000d-4a28-8771-aa52be687c7f | SURROGATE_WEAK; score=0.00; measured=0.00h; REWARD_PERSISTENCE_SURROGATE_WEAK |
| TOWNS-WETH | f3ab8cab-927e-4aed-9cbf-00d95c5350d7 | SURROGATE_WEAK; score=0.00; measured=0.00h; REWARD_PERSISTENCE_SURROGATE_WEAK |

### NetCover

| 池 | Llama ID | 差距 |
|---|---|---|
| WETH-USDC | 3ea03bb2-0fda-4280-9389-f76c5b75ff2b | 0.820998，差 0.179002 |
| WETH-USDT | 577caee3-254c-405d-a642-17e6b47a52b6 | 0.780163，差 0.219837 |
| O-USDC | e49edb6d-8e1d-4c76-8896-2357e7db849e | 0.621544，差 0.378456 |
| EURC-CBBTC | 29b739e4-5e90-40c3-9fe8-31f67a6be60c | 0.555121，差 0.444879 |
| WETH-USDC | b99bcdf5-1350-4269-981e-0e9b5cccb007 | 0.521926，差 0.478074 |

### PositionCap

| 池 | Llama ID | 差距 |
|---|---|---|
| — | — | 没有到达本闸后失败的池 |

## 3. 独立核查交叉验证

2026-08-09 一次性核查只保留了汇总数 `213`，没有保留 213 个池的身份列表或原始快照，因此无法诚实地声称逐个复原历史成员。下表是在本次随报告保存的 DefiLlama 快照上，用该文档披露的 H=30d、50U、65% fee、统一 50% reward haircut 和 fixed-cost-only 公式重跑的当前 cohort；它不是主漏斗入场闸。

当前重跑 cohort=200，其中 stablecoin=13；逐池结果全部保存在 `AUTOPSY.json.independent_cohort.rows`。

| 池 | 链/项目 | IL 容忍 APR | 死点 |
|---|---|---|---|
| MSUSD-USDC | Base/aerodrome-slipstream | 23.051% | multiwindow_stable:enter_frac=0.667，差 0.033 |
| XSGD-USDC | Base/aerodrome-slipstream | 29.563% | netcover:0.496001，差 0.503999 |
| VCHF-USDC | Solana/raydium-amm | — | BEFORE_MAIN_FUNNEL:M1_A_FORBIDDEN_SOLANA |
| VCHF-USDC | Base/aerodrome-slipstream | — | STAGE1_COARSE:vol1d 572 < 50000 |
| CADC-USDC | Base/aerodrome-slipstream | 30.509% | STAGE1_COARSE:TVL 129000 < 150000 |
| USDC-AVAIL | Base/aerodrome-slipstream | 39.343% | STAGE1_COARSE:TVL 125530 < 150000 |
| XSGD-USDC | Solana/orca-dex | — | BEFORE_MAIN_FUNNEL:M1_A_FORBIDDEN_SOLANA |

差异来源：历史核查覆盖 Base+Solana 且 TVL 门槛为 100K；主漏斗只支持 Base 两协议、M1 粗筛 TVL 为 150K、vol1d 为 50K，还要求资产质量、链上多窗口、reward persistence、完整 NetCover 和 PositionCap。Solana 因 M1-A 明令禁止而停在主漏斗之前。

## 4. 可审计性

- scanner as_of: `2026-08-10T04:34:39.491608+00:00`
- scanner cycle RPC health: `DEGRADED`（健康状态不参与放宽任何闸）
- terminal conjunction 与存储 accepted 计数一致：`True`
- JSON 保留每个终端池的逐位 gate bits、first failure、差距输入，以及独立 cohort 的逐池 death。
- 本工具仅以 SQLite `mode=ro` 读取；无钱包、签名、广播或阈值写入路径。
