# LP funnel autopsy — top-200 / all Stage-1 coarse-pass

结论：本批终闸完整合取后 `accepted=0`；分析的是 93 个 Stage-1 粗筛通过池中的 68 个终端记录。
未改动任何阈值；resolution/status 被单列为技术完整性闸，防止统计表遗漏终闸条件。

## 1. 逐闸衰减

| 闸 | 进入 | 本闸淘汰 | 存活 |
|---|---|---|---|
| resolution/status（技术完整性） | 68 | 21 | 47 |
| 资产质量 tier | 47 | 0 | 47 |
| yield_cover | 47 | 8 | 39 |
| 多窗口 stable | 39 | 6 | 33 |
| entry_eligible | 33 | 8 | 25 |
| NetCover | 25 | 25 | 0 |
| PositionCap | 0 | 0 | 0 |

entry_eligible 首次淘汰子原因：REWARD_PERSISTENCE_SURROGATE_WEAK=8。
NetCover 首次淘汰细分：输入缺失 0；可计算但 `<1.0` 25。

## 2. 每闸最接近通过的 5 个池

### resolution/status（技术完整性）

| 池 | Llama ID | 差距 |
|---|---|---|
| AERO-CBBTC | 3707d5ff-690b-423b-b3bb-4b7c7cca2990 | ambiguous_multi_factory_pool |
| AERO-CBBTC | 53b7036a-ec2a-494b-ad8e-ae53f35c20b8 | ambiguous_multi_factory_pool |
| BNKR-WETH | d7b0af87-0dba-4f48-8505-c801fccad673 | ambiguous_multi_factory_pool |
| CBETH-CBBTC | 79369b35-dd99-4d68-b989-31c258fc40ab | ambiguous_multi_factory_pool |
| EURC-USDC | fbce5857-69c4-4142-938b-62bdc9444967 | ambiguous_multi_factory_pool |

### 资产质量 tier

| 池 | Llama ID | 差距 |
|---|---|---|
| — | — | 没有到达本闸后失败的池 |

### yield_cover

| 池 | Llama ID | 差距 |
|---|---|---|
| ICP-WETH | 34987574-6e85-4046-ae9f-2b2b881008c6 | 0.940253，差 0.059747 |
| WETH-USOL | a09feb82-76db-4291-aea9-dc6e88343e09 | 0.842600，差 0.157400 |
| FLOWER-USDC | c3bf7641-16f2-458e-8aad-c02d230c3817 | 0.635631，差 0.364369 |
| TOWNS-WETH | f3ab8cab-927e-4aed-9cbf-00d95c5350d7 | 0.623978，差 0.376022 |
| SOSO-USDC | d1a265ef-1c32-4d98-b2d6-a473447286a2 | 0.536335，差 0.463665 |

### 多窗口 stable

| 池 | Llama ID | 差距 |
|---|---|---|
| WETH-AAVE | 2641aaa3-d441-4718-b638-029d09ca1d14 | enter_frac=0.600，差 0.100 |
| CTR-USDC | 47bb2cb3-6a91-43ee-9dde-abceb2ded03f | enter_frac=0.500，差 0.200 |
| USDC-VELVET | c07a115f-7299-4dd1-ac25-2de459010b6b | enter_frac=0.500，差 0.200 |
| HYPE-WETH | 2d73e593-f529-4373-aca7-58b4c552517b | enter_frac=0.400，差 0.300 |
| WETH-MSETH | 08e1a166-5366-4f57-bef8-76acb53699f0 | enter_frac=0.400，差 0.300 |

### entry_eligible

| 池 | Llama ID | 差距 |
|---|---|---|
| FUN-USDC | 18674a4f-57ea-4c91-99ce-ea1a2b37aa3d | SURROGATE_WEAK; score=0.00; measured=0.00h; REWARD_PERSISTENCE_SURROGATE_WEAK |
| USDC-CBBTC | ff82c362-dea1-4946-b3b1-92ebd5100b1e | SURROGATE_WEAK; score=0.00; measured=0.00h; REWARD_PERSISTENCE_SURROGATE_WEAK |
| USDC-CBMEGA | f9fbb53c-9584-498d-9a17-a67376550b5d | SURROGATE_WEAK; score=0.00; measured=0.00h; REWARD_PERSISTENCE_SURROGATE_WEAK |
| USDC-DIEM | 7944b313-e6ee-42b2-a5c8-a26446e37621 | SURROGATE_WEAK; score=0.00; measured=0.00h; REWARD_PERSISTENCE_SURROGATE_WEAK |
| USDC-USDT | ba557f7e-f287-45a9-bc37-8f3a24ca05c7 | SURROGATE_WEAK; score=0.00; measured=0.00h; REWARD_PERSISTENCE_SURROGATE_WEAK |

### NetCover

| 池 | Llama ID | 差距 |
|---|---|---|
| USDC-CBBTC | bf599ba2-97ae-48bb-9fd0-4f647ad7a832 | 0.854595，差 0.145405 |
| EURC-CBBTC | 29b739e4-5e90-40c3-9fe8-31f67a6be60c | 0.802850，差 0.197150 |
| WETH-USDC | 3ea03bb2-0fda-4280-9389-f76c5b75ff2b | 0.750400，差 0.249600 |
| WETH-USDT | 577caee3-254c-405d-a642-17e6b47a52b6 | 0.735492，差 0.264508 |
| VIRTUAL-USDC | 2df3e378-a3c7-4187-995f-51fe7ff18ccb | 0.708685，差 0.291315 |

### PositionCap

| 池 | Llama ID | 差距 |
|---|---|---|
| — | — | 没有到达本闸后失败的池 |

## 3. 独立核查交叉验证

2026-08-09 一次性核查只保留了汇总数 `213`，没有保留 213 个池的身份列表或原始快照，因此无法诚实地声称逐个复原历史成员。下表是在本次随报告保存的 DefiLlama 快照上，用该文档披露的 H=30d、50U、65% fee、统一 50% reward haircut 和 fixed-cost-only 公式重跑的当前 cohort；它不是主漏斗入场闸。

当前重跑 cohort=0，其中 stablecoin=0；逐池结果全部保存在 `AUTOPSY.json.independent_cohort.rows`。

| 池 | 链/项目 | IL 容忍 APR | 死点 |
|---|---|---|---|
| USDC-AVAIL | None/None | — | MISSING_FROM_CURRENT_DEFILLAMA_SNAPSHOT |
| CADC-USDC | None/None | — | MISSING_FROM_CURRENT_DEFILLAMA_SNAPSHOT |
| MSUSD-USDC | None/None | — | MISSING_FROM_CURRENT_DEFILLAMA_SNAPSHOT |
| XSGD-USDC | None/None | — | MISSING_FROM_CURRENT_DEFILLAMA_SNAPSHOT |
| VCHF-USDC | None/None | — | MISSING_FROM_CURRENT_DEFILLAMA_SNAPSHOT |

差异来源：历史核查覆盖 Base+Solana 且 TVL 门槛为 100K；主漏斗只支持 Base 两协议、M1 粗筛 TVL 为 150K、vol1d 为 50K，还要求资产质量、链上多窗口、reward persistence、完整 NetCover 和 PositionCap。Solana 因 M1-A 明令禁止而停在主漏斗之前。

## 4. 可审计性

- scanner as_of: `2026-08-10T13:24:29.678852+00:00`
- scanner cycle RPC health: `DEGRADED`（健康状态不参与放宽任何闸）
- terminal conjunction 与存储 accepted 计数一致：`True`
- JSON 保留每个终端池的逐位 gate bits、first failure、差距输入，以及独立 cohort 的逐池 death。
- 本工具仅以 SQLite `mode=ro` 读取；无钱包、签名、广播或阈值写入路径。
