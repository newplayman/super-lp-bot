# TP-D D2/D4 对照

阈值保持不变：`STABLE_MIN_FRAC=0.7`、`NetCover>=1.0`。D2 翻转来自同一批 10 窗观测的前 6 窗反事实，因此不混入时点变化。

- D2 可控样本：48；6 窗 stable=27，10 窗 stable=37。
- D4 old/new：92/68；交集 66。
- accepted：0 → 0。

## D2 6窗过 → 10窗不过

| symbol | llama_pool_id | 6窗 enter_frac | 10窗 enter_frac |
|---|---|---:|---:|
| USDC-PROS | `9e788cd1-c7f7-4857-99ca-495db03e67f1` | 0.833 | 0.6 |

## D2 6窗不过 → 10窗过

| symbol | llama_pool_id | 6窗 enter_frac | 10窗 enter_frac |
|---|---|---:|---:|
| USDC-DIEM | `7944b313-e6ee-42b2-a5c8-a26446e37621` | 0.667 | 0.8 |
| RAVE-USDC | `af5670be-df7d-4d34-934f-5b5cc7dcef0b` | 0.667 | 0.8 |
| WETH-USDC | `b99bcdf5-1350-4269-981e-0e9b5cccb007` | 0.667 | 0.8 |
| WETH-USDT | `577caee3-254c-405d-a642-17e6b47a52b6` | 0.667 | 0.7 |
| WETH-USDC | `3ea03bb2-0fda-4280-9389-f76c5b75ff2b` | 0.667 | 0.7 |
| WETH-VVV | `1666d5a3-22ab-456c-9ef7-66bba0733c39` | 0.667 | 0.8 |
| USDC-VVV | `c7d461f8-4ad8-42d8-a6b8-378fd8045660` | 0.667 | 0.8 |
| WETH-USOL | `a09feb82-76db-4291-aea9-dc6e88343e09` | 0.5 | 0.7 |
| BIO-WETH | `3709f4bb-2114-4742-907a-7bb5d58de274` | 0.5 | 0.7 |
| WETH-REI | `7cb47e02-170a-4f9e-bdd4-9d1a9a65e65a` | 0.667 | 0.8 |
| BIO-USDC | `c82b6e92-d55c-484c-997f-fd54e1ea5705` | 0.5 | 0.7 |

## 分布与 D4 逐闸

- 6窗 enter_frac：`{"0.333": 3, "0.500": 7, "0.667": 11, "0.833": 14, "1.000": 13}`
- 10窗 enter_frac：`{"0.400": 2, "0.500": 5, "0.600": 4, "0.700": 10, "0.800": 12, "0.900": 10, "1.000": 5}`
- old 逐闸：`{"asset_quality": 1, "entry_eligible": 14, "multiwindow_stable": 20, "netcover": 23, "resolution_status": 25, "yield_cover": 9}`
- new 逐闸：`{"entry_eligible": 8, "multiwindow_stable": 9, "netcover": 23, "resolution_status": 20, "yield_cover": 8}`
- 交集 first-failed-gate 变化：19（完整列表见 JSON）。
