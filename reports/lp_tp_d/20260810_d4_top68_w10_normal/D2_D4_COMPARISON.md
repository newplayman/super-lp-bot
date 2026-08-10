# TP-D D2/D4 对照

阈值保持不变：`STABLE_MIN_FRAC=0.7`、`NetCover>=1.0`。D2 翻转来自同一批 10 窗观测的前 6 窗反事实，因此不混入时点变化。

- D2 可控样本：47；6 窗 stable=29，10 窗 stable=38。
- D4 old/new：92/68；交集 65。
- accepted：0 → 0。

## D2 6窗过 → 10窗不过

| symbol | llama_pool_id | 6窗 enter_frac | 10窗 enter_frac |
|---|---|---:|---:|
| WETH-AAVE | `2641aaa3-d441-4718-b638-029d09ca1d14` | 0.833 | 0.6 |
| USDC-AERO | `06a7ca71-dc68-495c-b1d8-5c708339f0ab` | 0.833 | 0.6 |

## D2 6窗不过 → 10窗过

| symbol | llama_pool_id | 6窗 enter_frac | 10窗 enter_frac |
|---|---|---:|---:|
| USDC-DIEM | `7944b313-e6ee-42b2-a5c8-a26446e37621` | 0.667 | 0.8 |
| WETH-USDC | `b99bcdf5-1350-4269-981e-0e9b5cccb007` | 0.667 | 0.8 |
| WETH-USDT | `577caee3-254c-405d-a642-17e6b47a52b6` | 0.667 | 0.8 |
| USDC-VVV | `c7d461f8-4ad8-42d8-a6b8-378fd8045660` | 0.667 | 0.8 |
| AVNT-USDC | `eb27d0be-9de4-4ed9-8d36-a754e18d3358` | 0.667 | 0.8 |
| EURC-USDC | `847c874f-d4e7-47ed-8870-97d2f24a8767` | 0.667 | 0.7 |
| WETH-USOL | `a09feb82-76db-4291-aea9-dc6e88343e09` | 0.5 | 0.7 |
| SOSO-USDC | `d1a265ef-1c32-4d98-b2d6-a473447286a2` | 0.667 | 0.7 |
| TOWNS-WETH | `f3ab8cab-927e-4aed-9cbf-00d95c5350d7` | 0.667 | 0.7 |
| WETH-REI | `7cb47e02-170a-4f9e-bdd4-9d1a9a65e65a` | 0.5 | 0.7 |
| BIO-WETH | `3709f4bb-2114-4742-907a-7bb5d58de274` | 0.5 | 0.7 |

## 分布与 D4 逐闸

- 6窗 enter_frac：`{"0.167": 2, "0.333": 1, "0.500": 6, "0.667": 9, "0.833": 18, "1.000": 11}`
- 10窗 enter_frac：`{"0.300": 1, "0.400": 2, "0.500": 4, "0.600": 2, "0.700": 8, "0.800": 14, "0.900": 11, "1.000": 5}`
- old 逐闸：`{"asset_quality": 1, "entry_eligible": 14, "multiwindow_stable": 20, "netcover": 23, "resolution_status": 25, "yield_cover": 9}`
- new 逐闸：`{"entry_eligible": 8, "multiwindow_stable": 6, "netcover": 25, "resolution_status": 21, "yield_cover": 8}`
- 交集 first-failed-gate 变化：18（完整列表见 JSON）。
