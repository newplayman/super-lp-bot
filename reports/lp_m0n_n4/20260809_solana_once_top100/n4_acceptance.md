<stdin>:50: SyntaxWarning: invalid escape sequence '`'
<stdin>:51: SyntaxWarning: invalid escape sequence '`'
<stdin>:51: SyntaxWarning: invalid escape sequence '`'
<stdin>:59: SyntaxWarning: invalid escape sequence '`'
<stdin>:59: SyntaxWarning: invalid escape sequence '`'
<stdin>:59: SyntaxWarning: invalid escape sequence '`'
<stdin>:60: SyntaxWarning: invalid escape sequence '`'
<stdin>:60: SyntaxWarning: invalid escape sequence '`'
<stdin>:60: SyntaxWarning: invalid escape sequence '`'
<stdin>:64: SyntaxWarning: invalid escape sequence '`'
<stdin>:67: SyntaxWarning: invalid escape sequence '`'
<stdin>:69: SyntaxWarning: invalid escape sequence '`'
<stdin>:85: SyntaxWarning: invalid escape sequence '`'
<stdin>:89: SyntaxWarning: invalid escape sequence '`'
<stdin>:102: SyntaxWarning: invalid escape sequence '`'
<stdin>:116: SyntaxWarning: invalid escape sequence '`'
<stdin>:116: SyntaxWarning: invalid escape sequence '`'
<stdin>:124: SyntaxWarning: invalid escape sequence '`'
# FIX-N4 Solana 生产扫描验收

- 任务包：TP-M0N-v1 / FIX-N4
- 正式证据批次：`20260809_solana_once_top100`
- 数据时间：`2026-08-09T15:48:44.753135+00:00`
- 结论：**PASS — 有价值的 candidate-level fail-closed 生产诊断**
- 限定：本次没有走通真实 TACTICAL H 选择；100 个候选均因缺少权威池地址映射而在身份边界封闭。

## 证据锁定

| 证据 | 路径 | SHA-256 | 字节 |
|---|---|---|---:|
| scanner DB | `reports/lp_m0n_n4/20260809_solana_once_top100/scanner.db` | `56dea0aa606de04f1d56c4f42ca9a321380c30f19b0df14e165c760643fa6846` | 1200128 |
| vetted menu | `reports/lp_m0n_n4/20260809_solana_once_top100/vetted_menu.json` | `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570` | 3 |

正式 stdout 数字锁定为：

```text
[scanner] as_of=2026-08-09T15:48:44.753135+00:00 screened=1958 top=100 resolved=100 scored=100 accepted=0 sessions=0
[scanner] vetted_menu exported=0 invalid=0 out=reports/lp_m0n_n4/20260809_solana_once_top100/vetted_menu.json
```

菜单内容为 `[]`。首轮 `reports/lp_m0n_n4/20260809_solana_once` top10 仅为历史诊断，不作为本报告的正式证据。

## 汇总结论

| 检查项 | 正式结果 |
|---|---:|
| screened | 1958 |
| top / resolved orchestrator rows / scored | 100 / 100 / 100 |
| Raydium / Orca | 94 / 6 |
| profile 与 netcover_profile 均为 TACTICAL | 100/100 |
| root 与 blocked reason 均为 authoritative_pool_mapping_missing | 100/100 |
| H / H source / ER-policy H 三字段全为 None | 100/100 |
| reward_observations | 100/100 |
| reward persistence source：absent / surrogate_defillama | 99 / 1 |
| accepted | 0 |

这是一项有效的生产诊断：候选不再因误调用 `eth_blockNumber` 令整轮崩溃，也没有被静默丢弃；100 条候选、100 条拒绝根因及 100 条 reward observation 均可逐池审计。`resolved=100` 是 orchestrator 输出行数，不表示完成了权威链上池解析；逐池 `resolve_status=BLOCKED` 才是实际解析结论。

## 安全与边界

- 运行方式是单次 `--once`，只读，无 wallet、签名、交易构造或广播。
- Solana 分支在身份映射边界短路，未调用 Base/EVM resolver、EVM RPC、多窗口 V3 Swap replay 或 Q96 NetCover 状态读取。
- 没有启动长跑；单次运行结束后 PID 文件被清理。
- 没有根据 symbol 猜测池地址，也没有把 DefiLlama UUID、聚合器 sigma 或 proxy horizon 冒充真实链上证据。

## 真实 TACTICAL H 尚缺的权威适配器

1. DefiLlama UUID → 协议所有的 Solana pool account 映射，并验证 account owner、mint pair 与池身份。
2. Orca Whirlpool 与 Raydium CLMM/AMM 子类型的独立账户解析器。
3. 基于 slot/time window 的真实 swap 解码，用于 pair sigma、ER 和窗口稳定性。
4. 协议正确的手续费、active-liquidity/depth、reward conversion、gas 与退出成本证据。
5. 不依赖 EVM Q96 假设的 chain-aware multiwindow 与 NetCover 归一化。

在这些适配器完成前，`holding_horizon_hours`、`holding_horizon_source` 与 `holding_horizon_er_policy_hours` 保持 `None` 是正确的 fail-closed 结果。

## 逐池证据

| # | symbol | project | llama identity | profile | H(h) | H source | ER-policy H | root | reward evidence |
|---:|---|---|---|---|---:|---|---:|---|---|
| 1 | TINYTANK-USDC | raydium-amm | `llama:75641161-b710-5671-acac-0d2f22c3faf3` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 2 | WSOL-ARC | raydium-amm | `llama:83e9a75a-881a-4e5a-9aaa-82e2140fa57d` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 3 | WSOL-USDT | raydium-amm | `llama:cdd04383-21ea-45d1-94d6-295e58100559` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 4 | USD1-FIH | raydium-amm | `llama:5d6f57f4-6b2e-4647-a7b0-1034aab84475` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 5 | WSOL-CAPX | raydium-amm | `llama:ed309d3d-19bd-54fa-9673-39dd33813b18` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 6 | WSOL-SWARMS | raydium-amm | `llama:25cb3610-4aae-43dc-8773-fe13bdec9eb2` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 7 | WSOL-CHILLGUY | raydium-amm | `llama:1e958818-9a22-46b0-8567-12cb34fb4eb1` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 8 | WSOL-ZEREBRO | raydium-amm | `llama:b7c5a111-447f-4af6-9f18-581591249a76` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 9 | SPCX-USDC | raydium-amm | `llama:48e0c6f7-bcab-4b68-ba6f-3fb55ce6da69` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 10 | SPCXX-USDC | raydium-amm | `llama:8feb7ee9-2530-4168-860a-ee444c809da7` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 11 | WSOL-WOULD | raydium-amm | `llama:71b80fb4-50bc-4e0a-b01f-f60cb59fb859` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 12 | WSOL-USDC | raydium-amm | `llama:709f121d-d3b4-44da-b3d0-47bc16f5400b` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 13 | WSOL-GRIFFAIN | raydium-amm | `llama:9299b1ab-2c25-4032-bc90-f6f620373e0b` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 14 | WSOL-AVA | raydium-amm | `llama:4ad29d1d-ff76-48fb-ba0e-a88dfd71f3e0` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 15 | WSOL-ACT | raydium-amm | `llama:804a0c7b-7eb7-4b75-b066-4c568704fefe` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 16 | BOME-WSOL | raydium-amm | `llama:efa5ce76-dc4f-4d06-a9d4-0e09c4dcd0a1` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 17 | CARDS-USDC | raydium-amm | `llama:593fca5b-1e6c-492e-bb8c-30c5307defb8` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 18 | PONKE-WSOL | raydium-amm | `llama:ac66514d-8133-45a3-b317-2a2ae2ecd82e` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 19 | WSOL-GOAT | raydium-amm | `llama:f840ec7e-3d8c-40ea-b761-66515f8f17b9` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 20 | WSOL-RAY | raydium-amm | `llama:8161ea57-0353-485d-9ebd-c43ba4fbc7ae` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 21 | WSOL-USDT | raydium-amm | `llama:36439c60-452b-434f-8c62-651060e7dd55` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 22 | WSOL-MSTRX | raydium-amm | `llama:340cf7b7-9654-4f2c-9d30-e519dbde849d` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 23 | WSOL-MOODENG | raydium-amm | `llama:46f5eec1-26f1-4911-8d91-d627ff756dcd` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 24 | SPYX-USDC | raydium-amm | `llama:5ccd0074-df46-49d8-8f6d-de221b60672c` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 25 | WSOL-USELESS | raydium-amm | `llama:99d4b1c8-9e7b-45d7-8603-260d9846866c` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 26 | WSOL-BAN | raydium-amm | `llama:a24db72d-5c6a-4028-b81e-de1480fa0f81` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 27 | USDC-CSPR | raydium-amm | `llama:2a265415-e598-52de-a138-e90460d8a212` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 28 | WSOL-AURA | raydium-amm | `llama:c2f18cd1-e4e6-4ecd-aec5-e078505c69e7` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 29 | GIGA-WSOL | raydium-amm | `llama:10a72779-843e-4491-a9f6-7bc81e452193` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 30 | BDAG-USDC | raydium-amm | `llama:e5d99a8e-83dd-5aad-bf3f-576a8ea5078a` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 31 | USDC-2Z | raydium-amm | `llama:cc9c346a-22e8-46a3-b42f-3f9eac08f354` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 32 | CATE-USDC | raydium-amm | `llama:9ad28117-763a-52b9-9d0b-2bdca7abeb10` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 33 | SPX-WSOL | raydium-amm | `llama:e7187b64-b5f9-43cb-a2be-c101b72873bc` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 34 | AKE-USDC | raydium-amm | `llama:04166f2e-694d-518c-b08e-bd36e01d3f76` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 35 | BDAG-USDC | raydium-amm | `llama:67b704ad-e16c-543b-b6b4-1eefba68193b` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 36 | WSOL-PNUT | raydium-amm | `llama:8be07d6f-99a3-4643-9256-6f8a0b881508` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 37 | CRCLX-USDC | raydium-amm | `llama:2619cf7a-535e-43a6-8163-a0d1265611a6` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 38 | WSOL-PIPPIN | raydium-amm | `llama:20d99514-4d6b-4ff3-bbec-0732971885a0` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 39 | USDC-USOS | raydium-amm | `llama:fc9e6389-d6d4-58f9-94f4-29c87dc074eb` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 40 | USDC-BIRB | raydium-amm | `llama:e65da47e-838a-4247-b01e-60b8bd9bdc1a` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 41 | QQQX-USDC | raydium-amm | `llama:318d20fb-417b-492f-aeb9-d0709b0d3d58` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 42 | CSPR-USDC | raydium-amm | `llama:34a76123-af18-50b6-9f1d-84bb72c8925f` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 43 | LIKE-WSOL | raydium-amm | `llama:185ce02a-06db-4051-a6d8-25f86b32d77f` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 44 | WSOL-USD1 | raydium-amm | `llama:866092b0-6627-432a-af86-e1af0c4dae6c` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 45 | USD1-USDC | raydium-amm | `llama:d14d4632-727b-47c2-b69a-def5691b4155` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 46 | WSOL-VINE | raydium-amm | `llama:470dd76d-850f-49db-861a-0f675735ec57` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 47 | NVDAX-USDC | raydium-amm | `llama:6f7708a9-58d0-4941-a06a-b83e91b06903` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 48 | TSLAX-USDC | raydium-amm | `llama:314c6cb3-b2d1-4262-9b16-1c1db245b262` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 49 | WSOL-ALCH | raydium-amm | `llama:b09355f3-286d-472e-a1dd-4d0170dfb4aa` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 50 | PEPE-USDC | raydium-amm | `llama:f533ee34-5354-5712-9a31-332d21888e52` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 51 | BAYLA-USDC | raydium-amm | `llama:54c635f2-0ccb-5ca2-bb86-1e1c634be43e` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 52 | WSOL-MSOL | raydium-amm | `llama:62a15fee-d11c-4291-b566-4d9403a7913f` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 53 | WSOL-BC | raydium-amm | `llama:fef9bde9-fd67-465c-bf52-930d7782e174` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 54 | POPCAT-WSOL | raydium-amm | `llama:06faada9-ad40-4027-9380-db05f0f3fd53` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 55 | PUMP-USDC | raydium-amm | `llama:85ca2b2c-c141-5a4d-989f-64a5439d0b1e` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 56 | MEW-WSOL | raydium-amm | `llama:919f83c6-1a2d-4c67-985f-99e8b8423f62` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 57 | JUPUSD-USDC | raydium-amm | `llama:b486afff-6cb0-4932-aacb-4c32cf955512` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 58 | RAY-USDC | raydium-amm | `llama:8d1c0b44-a5ce-421c-b899-bf489159aa0f` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 59 | WSOL-FARTCOIN | raydium-amm | `llama:c66d7944-6582-4638-881a-360e5918e4b4` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 60 | WSOL-JELLYJELLY | raydium-amm | `llama:d3f1bb4f-6d3a-41f2-af1a-ae6baa4edd66` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 61 | USDC-TRX | raydium-amm | `llama:ca46228a-5be2-4f58-97e2-c98fb2b56e54` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 62 | VENUSCOIN-USDC | raydium-amm | `llama:981ebf61-78f8-50e4-bca4-77eaa26a9f68` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 63 | WSOL-JITOSOL | raydium-amm | `llama:ce89c76d-e6d5-4de0-9706-df3f33d309c7` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 64 | $WIF-WSOL | raydium-amm | `llama:caca758f-7a8f-4242-8d9c-cd44d98c5ee0` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 65 | PEPE-USDC | raydium-amm | `llama:75bf0314-4de8-50c3-b390-31d28279f1db` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 66 | CATE-USDC | raydium-amm | `llama:93127081-cbd5-5413-8c29-abe9bf883719` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 67 | USDC-USDT | raydium-amm | `llama:8ad76d42-6247-42f2-8281-5d59cb77b8b3` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 68 | AKE-USDC | raydium-amm | `llama:4f141be3-4027-5cc0-a209-001afaa01af0` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 69 | BNB-USDC | raydium-amm | `llama:f15c7999-1309-512e-b18f-7d8a363721ec` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 70 | XDC-USDC | raydium-amm | `llama:91084eaa-0740-5dcc-87a9-81e6e02f3099` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 71 | USDC-AKE | raydium-amm | `llama:eb98c798-bba1-588f-b2e3-81d006ef35e2` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 72 | USDG-ONYC | raydium-amm | `llama:92d30c54-b6c6-436d-b93d-c17f09268d0a` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 73 | USDS-USDC | raydium-amm | `llama:5b6c56a9-3b81-48ee-bee7-3f0dcd862e4d` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 74 | USDC-CSPR | raydium-amm | `llama:5259c0d6-2d70-5114-9ef5-bcce89078c2c` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 75 | USDC-BDAG | raydium-amm | `llama:29d89ccc-8d08-56b5-a930-742d22c706ff` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 76 | THEMEMES-USDC | raydium-amm | `llama:a5bdd9d9-f7c2-5223-a934-65aa08289c68` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 77 | XMR-USDC | raydium-amm | `llama:6dcaa44a-25a5-5ef4-b9ad-c8bdc0206a12` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 78 | XMR-USDC | raydium-amm | `llama:541701d0-895e-57d5-8eec-d6b4352e15a3` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 79 | USDC-BEAT | raydium-amm | `llama:379401d3-a7d0-5810-b086-63d8ac3847f9` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 80 | JCT-USDC | raydium-amm | `llama:24d1ee96-3bdd-5d59-b1a8-d818b39cef8d` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 81 | UOTF-USDC | raydium-amm | `llama:809896f2-6e28-5293-9a19-1e73a46bcb56` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 82 | BEAT-USDC | raydium-amm | `llama:116ca935-cd3a-56fd-b127-67f23ce72944` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 83 | TUT-USDC | raydium-amm | `llama:ec884686-76c8-54d3-8c9e-db3afc2b7562` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 84 | PIPEDOG-USDC | raydium-amm | `llama:7cdeccc6-3734-51fc-b9e1-df0792f02572` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 85 | ENA-USDC | raydium-amm | `llama:e90a9517-b4ec-50b5-8872-871f263f1259` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 86 | MARSCOIN-USDC | raydium-amm | `llama:79e3a42d-adfe-5f1e-8ca1-7b3d446bcb09` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 87 | USDC-XMR | raydium-amm | `llama:1fd548b1-c3f8-5794-adb2-04764d66e43b` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 88 | MARSCOIN-USDC | raydium-amm | `llama:5fc831f1-b421-5e93-87a5-6c03774c8f1e` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 89 | USDC-MARSCOIN | raydium-amm | `llama:0f961bd3-ba48-52ec-b918-b2833780dc58` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 90 | MARSCOIN-USDC | raydium-amm | `llama:55fb9b53-ba64-5f34-bd7e-3adc98a197a8` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 91 | XMR-USDC | raydium-amm | `llama:fe3c6eae-cc4e-580e-a9ff-d0916b05a81a` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 92 | XMR-USDC | raydium-amm | `llama:7c5b28ca-057f-5b12-bf1b-d53696cf9377` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 93 | CC-USDC | raydium-amm | `llama:3d5c485e-5dfd-5396-84d5-6ce1ef0abc28` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 94 | SOL-PUMP | orca-dex | `llama:c9e701f0-b82a-49d6-9da7-5955ef20157b` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 95 | ZEC-USDC | orca-dex | `llama:3de7947c-e199-4842-a496-a775f59d6ba3` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 96 | SOL-ORCA | orca-dex | `llama:558efc67-8544-434b-bf15-ea152f5c5e1d` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 97 | SOL-CBBTC | orca-dex | `llama:6dc30ef3-d497-497c-91f3-b4ccb817a8b9` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 98 | WSOL-USDC | raydium-amm | `llama:12edc6f3-4926-4b4f-b97c-38ef6a458574` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | surrogate_defillama/SURROGATE_STRONG; apyReward=0.84113; obs=defillama:/pools |
| 99 | SOL-USDC | orca-dex | `llama:a5c85bc8-eb41-45c0-a520-d18d7529c0d8` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |
| 100 | SOL-BORG | orca-dex | `llama:490a8764-1b70-4d7f-889a-70637e61a21a` | TACTICAL/TACTICAL | None | None | None | authoritative_pool_mapping_missing | absent/NOT_APPLICABLE; apyReward=0; obs=defillama:/pools |

所有逐池行同时满足：`status=FAIL_CLOSED`、`resolve_status=BLOCKED`、`accepted=false`，终态拒绝为 `ENTRY_INELIGIBLE:authoritative_pool_mapping_missing`。

