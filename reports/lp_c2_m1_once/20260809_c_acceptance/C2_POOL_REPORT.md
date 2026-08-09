# FIX-C2 真实 scanner --once 逐池报告

- as_of: `2026-08-09T17:56:14.163747+00:00`
- pools: `30`; accepted: `0`; PositionCap pass: `15`
- M1 coarse TVL floor: `150000 U`
- runtime cap: `min(TierConfiguredMax, TVL*0.0005, ActiveLiquidityNotional*0.02)`; hard TVL share: `0.100%`

| pool | pair | TVL | active notional | cap | cap pass | terminal accepted | reason |
|---|---|---:|---:|---:|---|---|---|
| `0x7501bc8bb51616f79bfa524e464fb7b41f0b10fb` | MSUSD-USDC | 1240664.0000 | 10427419.0805 | 60.0000 | True | False | NETCOVER_BELOW_SHADOW |
| `0x892a6ab3fa0f1f839fcb0ae264a8c4bbfb030725` | XSGD-USDC | 452876.0000 | 299178.2754 | 60.0000 | True | False | NETCOVER_BELOW_SHADOW |
| `0x9785ef59e2b499fb741674ecf6faf912df7b3c1b` | WETH-USDT | 900202.0000 | 1256093.3620 | 60.0000 | True | False | ENTRY_INELIGIBLE:REWARD_PERSISTENCE_SURROGATE_WEAK |
| `0xb07d7eece8866e549601af5c7622d8cdbedc914e` | EURC-CBBTC | 390690.0000 | 141606.1211 | 60.0000 | True | False | ENTRY_INELIGIBLE:REWARD_PERSISTENCE_SURROGATE_WEAK |
| `0x9e48d016ee76cf53e2de8dc8058c7549c8c202df` | HYPE-WETH | 254744.0000 | 207462.2306 | 60.0000 | True | False | NETCOVER_BELOW_SHADOW |
| `0x29183f918920a2aef0115a9c7374945589968aea` | SOSO-USDC | 300793.0000 | 579550.0812 | 60.0000 | True | False | NETCOVER_BELOW_SHADOW |
| `0x0150e3d89e161518c044ad191c4bdf6b40df6e83` | USDC-CBMEGA | 386711.0000 | 12029946.7724 | 60.0000 | True | False | ENTRY_INELIGIBLE:REWARD_PERSISTENCE_SURROGATE_WEAK |
| `0x74f72788f4814d7ff3c49b44684aa98eee140c0e` | WETH-MSETH | 1099509.0000 | 707854.6520 | 60.0000 | True | False | ENTRY_INELIGIBLE:REWARD_PERSISTENCE_SURROGATE_WEAK |
| `0x0225ba893d5f8ecd6d2022f9dec59b34f61098a1` | WETH-USOL | 788627.0000 | 466955.7382 | 60.0000 | True | False | NETCOVER_BELOW_SHADOW |
| `0x48be08d21fccf3f793783c23c33555f5e0c2b7cd` | TOWNS-WETH | 210096.0000 | 654483.1900 | 60.0000 | True | False | NETCOVER_BELOW_SHADOW |
| `0x6d76a0f856a2ba951da45da9be399509ad602e6a` | USDC-ACU | 206003.0000 | 66871.8669 | 60.0000 | True | False | ENTRY_INELIGIBLE:REWARD_PERSISTENCE_SURROGATE_WEAK |
| `0xe30d5bf485f7476ac15884a28ffb3c9cea635dcb` | AVNT-USDC | 593576.0000 | 215980.6609 | 60.0000 | True | False | NETCOVER_BELOW_SHADOW |
| `0x0ab02e160f0df68dc049b012c514857306960eae` | CTR-USDC | 455663.0000 | 23406.5287 | 60.0000 | True | False | NETCOVER_BELOW_SHADOW |
| `0x6b0f53cbd9272d8117e9535fe25371dedf39a1be` | USDC-VELVET | 3255192.0000 | 239324.3518 | 60.0000 | True | False | ENTRY_INELIGIBLE:REWARD_PERSISTENCE_SURROGATE_WEAK |
| `0x8a8e4170c09074b109352190d47e54d7c1f61e4e` | USDC-PROS | 707408.0000 | 167015.7930 | 60.0000 | True | False | ENTRY_INELIGIBLE:REWARD_PERSISTENCE_SURROGATE_WEAK |
| `llama:07eda095-9e08-4f82-ad79-2225c60ed229` | WETH-CBBTC | 7744929.0000 | N/A | N/A | False | False | PERMANENT_FAIL_CLOSED:ambiguous_multi_factory_pool |
| `llama:1328ac9d-9939-4719-a85a-114935209e08` | WETH-USDC | 6032949.0000 | N/A | N/A | False | False | PERMANENT_FAIL_CLOSED:ambiguous_multi_factory_pool |
| `llama:1b0810d3-1ee3-4a8c-be39-b8a8978fbbc9` | SOL-CBBTC | 293830.0000 | N/A | N/A | False | False | PERMANENT_FAIL_CLOSED:ambiguous_multi_factory_pool |
| `llama:3aebe700-db0b-49e2-82f6-564acdfae434` | WETH-AERO | 1388078.0000 | N/A | N/A | False | False | PERMANENT_FAIL_CLOSED:ambiguous_multi_factory_pool |
| `llama:4153d5ef-763e-4e84-b109-c31ce0f447e2` | WETH-TIBBIR | 224324.0000 | N/A | N/A | False | False | PERMANENT_FAIL_CLOSED:ambiguous_multi_factory_pool |
| `llama:4e01eb90-f885-40e9-a484-3624be86fd66` | RECALL-USDC | 574315.0000 | N/A | N/A | False | False | PERMANENT_FAIL_CLOSED:ambiguous_multi_factory_pool |
| `llama:53b7036a-ec2a-494b-ad8e-ae53f35c20b8` | AERO-CBBTC | 1101878.0000 | N/A | N/A | False | False | PERMANENT_FAIL_CLOSED:ambiguous_multi_factory_pool |
| `llama:541b4974-e23b-4a7a-968f-6cfc027825de` | WETH-CBBTC | 780783.0000 | N/A | N/A | False | False | PERMANENT_FAIL_CLOSED:ambiguous_multi_factory_pool |
| `llama:6f1786fc-a22f-4c46-91cd-d3792479bdc2` | USDC-CBBTC | 4892441.0000 | N/A | N/A | False | False | PERMANENT_FAIL_CLOSED:ambiguous_multi_factory_pool |
| `llama:79369b35-dd99-4d68-b989-31c258fc40ab` | CBETH-CBBTC | 863496.0000 | N/A | N/A | False | False | PERMANENT_FAIL_CLOSED:ambiguous_multi_factory_pool |
| `llama:9b9497ab-56f4-4650-a162-e323b90d0c4c` | WETH-ZRO | 163174.0000 | N/A | N/A | False | False | PERMANENT_FAIL_CLOSED:ambiguous_multi_factory_pool |
| `llama:a6a1fe38-a220-4f68-a2b9-d2749c3e4664` | SOL-USDC | 397379.0000 | N/A | N/A | False | False | PERMANENT_FAIL_CLOSED:ambiguous_multi_factory_pool |
| `llama:c0675357-219a-42b5-b6cc-079cef869cf5` | USDC-CBBTC | 560961.0000 | N/A | N/A | False | False | PERMANENT_FAIL_CLOSED:ambiguous_multi_factory_pool |
| `llama:deeb8740-4041-4ca2-b87c-70f708eae796` | WETH-EURC | 1022089.0000 | N/A | N/A | False | False | PERMANENT_FAIL_CLOSED:ambiguous_multi_factory_pool |
| `llama:fbce5857-69c4-4142-938b-62bdc9444967` | EURC-USDC | 1060225.0000 | N/A | N/A | False | False | PERMANENT_FAIL_CLOSED:ambiguous_multi_factory_pool |

accepted 为 0 也是有效结果；本报告不调整任何 NC/STABLE/FEE_COVER 阈值。
