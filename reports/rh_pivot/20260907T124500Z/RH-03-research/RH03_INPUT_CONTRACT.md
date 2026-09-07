

调研完成，以下为完整结论（全部基于 `/opt/lpbot/lp-bot-v3-origin-check` 只读取证）。

---

# A. 引擎四个函数的精确输入契约

文件：`scripts/lp_netcover_engine_v1_readonly.py`（399 行）

## A1. `evaluate_netcover`（:177–222）

**签名**（全部 keyword-only，无 dict 入参）：

```python
def evaluate_netcover(
    *,
    fee_ev: float,
    reward_ev: float,
    reward_haircut: float | Mapping[str, Any],
    expected_il: float,
    lvr_coefficient: float,
    entry_cost: float,
    exit_cost: float,
    gas: float,
    slippage: float,
    reward_conversion_cost: float,
    exit_latency_loss: float,
) -> NetCoverEstimate:
```

- 11 个参数全部显式命名，**不读任何 dict key**。
- 校验路径：金额类走 `_amount`（:61，要求 finite 且 ≥0）；`lvr_coefficient` 走 `_amount(positive=False)`；`reward_haircut` 走 `_haircut_value`（:84，float 或含 `"category"` key 的 Mapping，值域 [0,1]）。
- 计算：`lvr = expected_il * lvr_coefficient`；`income = fee_ev + reward_ev * haircut`；`risk = expected_risk_cost(...)`（:108，8 项求和）；`cover = netcover(income, risk)`（:141，income>0 且 cost==0 时为 `inf`，否则 0.0）。

**返回值 `NetCoverEstimate`**（frozen dataclass，:150–171）字段：

| 字段 | 类型 |
|---|---|
| conservative_fee_ev | float |
| haircut_reward_ev | float |
| adjusted_income_ev | float |
| expected_il | float |
| expected_lvr_model | float |
| entry_cost / exit_cost / gas / slippage / reward_conversion_cost / exit_latency_loss_model | float |
| expected_risk_cost | float |
| gross_fee_cover_diagnostic | float（可能 inf） |
| netcover | float（可能 inf） |
| shadow_candidate | bool（`cover >= NETCOVER_SHADOW`，:219） |
| tiny_live_candidate | bool（`cover >= NETCOVER_TINY_LIVE`，:220） |
| semantics | Mapping[str,str]（default_factory，3 个 key） |

`.to_dict()` 即 `asdict`（:173）。

## A2. `apply_netcover_gate`（:282–380）

**签名**：

```python
def apply_netcover_gate(
    records: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
    *,
    reward_haircut: float | Mapping[str, Any] = REWARD_HAIRCUTS["protocol"],  # = 0.50
    lvr_coefficient: float = 0.5,
) -> list[dict[str, Any]]:
```

**每条 record 读取的 key（逐 key 列举）**：

| key | 读取方式 | 行号 |
|---|---|---|
| `protocol_type` | `rec.get` | :299 |
| `netcover_model_path` | `rec.get` | :312, :322 |
| `fee_ev_usd` | `rec.get`（缺失检测）+ `rec[...]`（取值） | :327 / :342 |
| `reward_ev_usd` | 同上 | :327 / :343 |
| `il_ev_usd` | 同上 | :327 / :345 |
| `entry_cost_usd` | 同上 | :327 / :347 |
| `exit_cost_usd` | 同上 | :327 / :348 |
| `gas_usd` | 同上 | :327 / :349 |
| `slippage_usd` | 同上 | :327 / :350 |
| `reward_conversion_cost_usd` | 同上 | :327 / :351 |
| `exit_latency_loss_usd` | 同上 | :327 / :352 |
| `reward_haircut` | `rec.get(key, 默认参数)` | :344 |
| `lvr_coefficient` | `rec.get(key, 默认参数)` | :346 |
| `capital_usd` | `rec.get` | :366 |

9 个 gate 输入 key 由常量 `_GATE_INPUT_KEYS` 定义（:275–278）。

**写入的 key（`rec = dict(source)` 后 `rec.update`，:295，不改原 dict）**：

- **失败路径**（4 种，均写同一组 None + reason）：`risk_usd=None, expected_net_yield_usd=None, expected_net_yield_pct=None, netcover_ratio=None, netcover=None, netcover_pass=False, rejection_reason=<str>`
  - `NETCOVER_PROTOCOL_TYPE_INVALID:{exc}`（:304）
  - `NETCOVER_MODEL_PATH_MISMATCH:expected=...,got=...`（:313–324）
  - `NETCOVER_INPUT_MISSING:<逗号拼接缺失 key>`（:327–336）
  - `NETCOVER_INPUT_INVALID:{exc}`（:355–363）
- **成功路径**（:370–379）：`lvr_ev_usd, risk_usd, expected_net_yield_usd, expected_net_yield_pct`（capital 有效时 `net_yield/capital*100`，否则 None）, `netcover_ratio, netcover, netcover_pass`（bool）, `rejection_reason`（None 或 `"NETCOVER_BELOW_SHADOW"`）, `netcover_semantics`（dict）。

## A3. `absolute_profit_gate`（:233–254）

```python
def absolute_profit_gate(
    expected_net_profit_h: float,        # 位置参数，_finite（可负）
    round_trip_cost: float,              # 位置参数，>=0
    *,
    min_profit_usd: float = MIN_PROFIT_USD,    # 1.0（:21）
    safety_multiple: float = SAFETY_MULTIPLE,  # 5.0（:20）
) -> AbsoluteProfitDecision:
```

返回 `AbsoluteProfitDecision`（:225–231）：`allowed: bool`、`expected_net_profit_usd: float`、`round_trip_cost_usd: float`、`required_profit_usd: float`、`reason: str`（`"PASS"` 或 `"INV-COST-01_EXPECTED_NET_PROFIT_TOO_LOW"`）。逻辑：`required = max(min_profit_usd, safety_multiple * round_trip_cost)`；`allowed = profit >= required`。

## A4. `position_cap_usd`（:256–272）

```python
def position_cap_usd(
    tier_configured_max: float,          # >0
    pool_tvl: float,                     # >0
    active_liquidity_notional: float,    # >0
    *,
    active_share_limit: float = ACTIVE_SHARE_LIMIT,  # 0.02（:25）
) -> float:
```

返回 `min(tier_cap, pool_tvl * POSITION_TVL_SHARE, active * active_share_limit, pool_tvl * HARD_POSITION_TVL_SHARE)`（:271–272）。

---

# B. 装配器产出字段清单

文件：`scripts/lp_netcover_inputs_v1_readonly.py`（1428 行）

## B0. `protocol_type` 分派（`assemble_netcover_inputs`，:1404–1425）

- 读 `source.get("protocol_type")`（:1410），`strip().lower()`。
- `"clmm"` → `assemble_clmm_netcover_inputs`（:824）；`"amm_constant_product"` → `assemble_amm_netcover_inputs`（:1134）；其他 → `_invalid_protocol_record`（:1389–1401）。
- **fail-closed 常量**：字符串字面量 **`"NETCOVER_PROTOCOL_TYPE_INVALID"`**（:1397），写入 `permanent_fail_closed_reason` 与 `permanent_fail_closed_reasons=["NETCOVER_PROTOCOL_TYPE_INVALID"]`；同时 9 个字段全 None、各 `{field}_semantics`/`{field}_source`=None、`netcover_model_path=None`、`netcover_input_semantics={field:None}`。引擎侧对应前缀 `"NETCOVER_PROTOCOL_TYPE_INVALID:"`（engine:304）。

## B1. `assemble_clmm_netcover_inputs`（:824–1113）

`record = dict(source)`（:831）——**输入 key 全部透传**。要求 `protocol_type=="clmm"` 否则 ValueError（:832–835）。先 pop 不可信路由 key（`reward_conversion_routes/_route_costs/_selected_route_id/_route_selection_rule`）。

**写入的 key（逐 key，标注口径）**：

**① 9 个 horizon-USD 字段**（:958–960，`record[field] = value`）——全部 **horizon-USD 口径**（持有期 H 内的 USD 期望值），**全部可能为 None**（fail-closed）：
`fee_ev_usd, reward_ev_usd, il_ev_usd, entry_cost_usd, exit_cost_usd, gas_usd, slippage_usd, reward_conversion_cost_usd, exit_latency_loss_usd`

**② 每字段伴随元数据**（:965–966）：`{field}_semantics`（str|None，取自 INPUT_SEMANTICS :101–111，gas_usd 为 `"historical_observation"`，其余 `"model_estimate"`）、`{field}_source`（str|None，取自 INPUT_SOURCES :113–128，gas_usd 为 None 即链特定）。

**③ 主 update 块**（:968–989）：

| key | 口径 | 可能 None |
|---|---|---|
| `capital_usd` | 原始 USD（= position_usd 参数，默认 `M1_MIN_POSITION_USD`=50.0） | 否 |
| `holding_horizon_hours` | 原始小时数 | 是 |
| `protocol_type` | 常量 `"clmm"` | 否 |
| `netcover_model_path` | 常量 `"clmm_vol_sized_range_v1"` | 否 |
| `netcover_profile` | `"PASSIVE"`/`"TACTICAL"` | 是 |
| `fee_apr_haircut` | 0.65（established）/0.40（new/unknown） | 否 |
| `reward_category` | 字符串 | 是 |
| `reward_category_haircut` | 0.90/0.75/0.50/0.25/0.0 | 是 |
| `reward_persistence_haircut` | score_factor | 否 |
| `reward_persistence_evidence_source` | str | 否 |
| `reward_persistence_status` | str | 否 |
| `lvr_coefficient` | 常量 `LVR_COEFFICIENT_MODEL`=0.50（:981） | 否 |
| `netcover_input_semantics` | dict[str, str\|None] | 否 |
| `gas_usd_source` | str | 是 |
| `solana_gas_cost_reason` | str | 是 |
| `solana_reward_reason` | str | 是 |
| `netcover_input_position_source` | 常量 `"M1_MIN_POSITION_USD"` | 否 |
| `netcover_input_assembly_source` | 常量 `"lp_netcover_inputs_v1_readonly:raw_evidenc_e_calculated_only"` | 否 |

**④ fee_capture 元数据**（:516–526 构造，:990 update）：`fee_capture_reference_horizon_hours`(=168.0)、`fee_capture_reference_range_pct`、`fee_capture_target_range_pct`、`fee_capture_reference_share`、`fee_capture_target_share`、`fee_capture_share_ratio`、`fee_capture_evidence_apr_pct`（以上均可能 None）、`fee_capture_haircut`、`active_liquidity_notional_usd`（**原始 USD 口径**，非 horizon，可能 None）。

**⑤ 仓位上限块**（:1004–1053）：`capital_tier`（可能 None）、`tier_configured_max_usd`（可能 None）、`position_requested_usd`（float）、`position_investable_usd`（可能 None）、`position_cap_usd`（可能 None）、`position_cap_tvl_share`（可能 None）、`position_cap_regular_tvl_share_limit`(=0.0005, :1036)、`position_cap_active_share_limit`(=0.02)、`position_cap_hard_tvl_share_limit`(=0.001, :1038)、`position_cap_hard_tvl_share_ok`（bool，:1017 读 `HARD_POSITION_TVL_SHARE`）、`position_cap_pass`（bool）、`position_cap_reason`（`"PASS"`/`"INV-TVLSHARE-01_INPUT_MISSING_OR_INVALID"`/`"INV-TVLSHARE-01_HARD_TVL_SHARE_EXCEEDED"`/`"INV-TVLSHARE-01_POSITION_CAP_BELOW_M1_MIN"`）、`active_liquidity_notional_usd_source`（可能 None）。

**⑥ reward 路由元数据**（:1054）：`reward_conversion_route_costs`（list）、`reward_conversion_selected_route_id`（可能 None）、`reward_conversion_route_selection_rule`（可能 None）。

**⑦ 条件写入**：
- 有 `scanner_measured_evidence` 时（:1055–1062）：`scanner_measured_cross_pool_evidence`（dict）、`measured_token1_usd`（float）、`measured_token1_usd_source`（可能 None）。
- category 与 persistence 均有时（:1065–1067）：`reward_haircut`（float = category × persistence）。
- `round_trip_cost_usd`（:1068–1074）：float|None = entry+exit+slippage（**horizon-USD 口径**）。
- 永久 fail-closed 时（:1108–1113）：`permanent_fail_closed_reasons`（list）、`permanent_fail_closed_reason`（str）、`permanent_fail_closed_r1a_classification`（`"NO_MEASURED_USD_QUOTE_AND_REWARD_CONVERSION_DEPTH"` 或 `"MISSING_REWARD_CONVERSION_EVIDENCE"`）。

## B2. `assemble_amm_netcover_inputs`（:1134–1387）额外 key

`amm_holding_horizon_max_hours`(=720.0)、`amm_horizon_cap_reason`、`netcover_profile="AMM_FULL_RANGE"`、`amm_no_range_model=True`、`amm_price_ratio`（可能 None）、`amm_il_fraction_signed`（可能 None）、`amm_position_dilution_factor`（可能 None）、`active_liquidity_notional_usd`（= pool_tvl）、`fee_capture_*` 全显式 None、`lvr_coefficient`（:1341）、`position_cap_regular_tvl_share_limit`（:1355）、`position_cap_hard_tvl_share_limit`（:1357）、hard_ok 判定读 `HARD_POSITION_TVL_SHARE`（:1294）。

---

# C. 输入三分类（RH-03 视角）

## ① 链无关纯计算（RH 可直接复用旧函数，零改动）

- **引擎**：`evaluate_netcover`、`apply_netcover_gate`、`absolute_profit_gate`、`position_cap_usd`、`netcover_model_path`、`netcover`、`gross_fee_cover`、`adjusted_income_ev`、`expected_risk_cost`（engine 全文）。
- **成本模型**：`clmm_token0_value_fraction`、`exit_conversion_cost_usd`、`roundtrip_cost_usd`、`slippage_bps_for_swap`、`effective_fee_share`、`human_liquidity`、`price_impact_frac`、`swap_new_sqrt_price`（`scripts/lp_swap_cost_model_v1_readonly.py`）。
- **装配器纯函数**：`constant_product_il_fraction`、`_amm_swap_costs`、`profile_kind`、`holding_horizon_hours`、`amm_holding_horizon_hours`、`select_drag_adjusted_horizon`（inputs 内）；`_swap_components`（`scripts/lp_cost_sensitivity_v1_readonly.py:142–165`）、`price_from_sqrt_x96`、`HOURS_PER_YEAR`=8760.0（:39）；`position_liquidity_raw`（`scripts/lp_v3_fee_share.py:3`）；`recommend_range_pct`（`scripts/lp_vol_range_sizer_v1_readonly.py:99`）；`reward_persistence_gate`（`scripts/lp_universe_screener_v1_readonly.py:164`）。
- **常量**：`NETCOVER_SHADOW/TINY_LIVE`、`REWARD_HAIRCUTS`、`SAFETY_MULTIPLE`、`MIN_PROFIT_USD`、`POSITION_TVL_SHARE`、`HARD_POSITION_TVL_SHARE`、`ACTIVE_SHARE_LIMIT`、`LVR_COEFFICIENT_MODEL`、`EXIT_LATENCY_LOSS_APR_PCT_MODEL`(=0.50)、`ESTABLISHED_FEE_HAIRCUT`(=0.65)、`NEW_OR_AGE_UNKNOWN_FEE_HAIRCUT`(=0.40)、`DRAG_APR_MAX`(=15.0)、`AMM_HOLDING_HORIZON_MAX_HOURS`(=720.0)、`PROFILE_HORIZONS_HOURS`、`FEE_EVIDENCE_REFERENCE_HOURS`(=168.0)、`HISTORICAL_GAS_USD`（仅 Base=0.0795）、`CAPITAL_TIER_CONFIGURED_MAX_USD`、`M1_MIN_POSITION_USD`(=50.0)、`NETCOVER_MODEL_CLMM/AMM`。

## ② 链上数据（RH 必须新采集）

| 数据 | 来源（RPC 方法 / 表列） |
|---|---|
| `sqrtPriceX96`（或 Solana `sqrt_price_x64`）、`dec0`、`dec1`、`token0`、`token1`、`fee_tier`、`range_pct` | EVM: `getPool`/slot0（Uniswap V3）；Solana: pool 账户解码。inputs 读取点 :886–887, :453–500 |
| `l_active_raw`（pool.liquidity）或 `last_swap_liquidity_raw`（解码 swap 事件） | 同池状态 / 最新 swap 事件解码；**provenance 字段必须为 `measured:` 前缀**：`l_active_raw_source`、`sqrt_price_x96_source`、`last_swap_cost_state_source`（:556–577） |
| `last_swap_price_token1_per_token0` | 解码 swap 事件（:453–500） |
| `tvlUsd`/`tvl_usd`/`tvl` | 扫描器表列（:1011） |
| `active_liquidity_notional_usd` | 扫描器内部测量（当前活跃 L 在目标区间的 USD 名义值）（:1012–1013） |
| `capital_tier` | 扫描器表列（:1004） |
| `solana_transaction_cost_evidence`（status/signature_fee_lamports/priority_fee_lamports/rent_lamports/operation_count/sol_usd/sol_usd_source/quoted_at） | Solana RPC `getFeeForMessage`/`simulateTransaction` + rent（:137） |
| `solana_reward_evidence`（status/reward_ev_usd/reward_conversion_cost_usd/reward_token_symbol/conversion_routes/selected_route_id） | Solana 奖励路由测量（:181） |
| `scanner_measured_evidence.aero_reward_routes`（每路由：route_id/pool/factory/token0/token1/dec0/dec1/fee_tier/pair_price_token1_per_token0/l_active_raw/observed_block/measurement_source=`measured:scanner_internal_rpc:...`/executable/tick_spacing）+ `complete` 标志 | 扫描器内部 RPC 跨池测量（:795–801, :1055–1062） |
| AMM 路径：`amm_price_ratio`（`amm_price_ratio_source` 须 `measured:` 前缀）或 `amm_entry_price`/`amm_exit_price`；pool TVL；fee_tier | 池状态（:1181–1184, :1294） |

## ③ 外部市场/奖励数据

- `fee_apr_24h`/`fee_apr_onchain`、`fee_apr_7d`/`apyBase`（DefiLlama 或链上费用 APR）（:851–852）
- `reward_apr`/`apyReward`（DefiLlama）（:869）
- `sigma_pair`/`sigma_daily`/`sigma`（多窗口价格回放波动率）（:886）
- `il_apr`/`expected_il_apr_pct`（:887）
- `is_new_pool`（:853）
- `profile`/`strategy_profile`、`project`（profile_kind，:320–340）
- `holding_horizon_hours`（ER/profile 阶段输出，内部策略非链上）（:350–358）
- `reward_high_duration_hours`/`reward_high_duration` + `reward_persistence_evidence_source`（扫描器自身 SQLite 历史）
- `reward_token_symbol`/`rewardTokens`/`reward_is_points`（奖励代币分类，:420–451）
- `sol_usd`（SOL/USDC 外部报价）

---

# D. 六常量的全部读取点

| 常量 | 定义 | 读取点（文件:行号，所在函数） |
|---|---|---|
| `NETCOVER_SHADOW`=1.0 | engine:18 | **engine:219**（`evaluate_netcover`，shadow_candidate）；导出 engine:392；测试 tests/test_lp_netcover_engine_v1_readonly.py:9,25、tests/test_lp_netcover_positive_controls_v1_readonly.py:8,44、tests/test_lp_netcover_inputs_v1_readonly.py:18,794 |
| `NETCOVER_TINY_LIVE`=1.5 | engine:19 | **engine:220**（`evaluate_netcover`，tiny_live_candidate）；导出 engine:392；测试同上 |
| `POSITION_TVL_SHARE`=0.0005 | engine:24 | **engine:271**（`position_cap_usd`）；inputs:34（import）；**inputs:1036**（`assemble_clmm_netcover_inputs`，position_cap_regular_tvl_share_limit）；**inputs:1355**（`assemble_amm_netcover_inputs`）；导出 engine:392 |
| `HARD_POSITION_TVL_SHARE`=0.001 | engine:26 | **engine:272**（`position_cap_usd`）；inputs:31（import）；**inputs:1017**（CLMM hard_ok 判定）、**inputs:1038**（CLMM limit 字段）、**inputs:1294**（AMM hard_ok）、**inputs:1357**（AMM limit 字段）；导出 engine:391 |
| `LVR_COEFFICIENT_MODEL`=0.50 | **inputs:94**（不在引擎） | **inputs:981**（`assemble_clmm_netcover_inputs`）、**inputs:1341**（`assemble_amm_netcover_inputs`）。引擎侧 `apply_netcover_gate` 的默认参数是字面量 `0.5`（engine:285），与该常量数值一致但**无引用关系** |
| `STABLE_MIN_FRAC`=0.7 | **不在引擎/装配器** | `scripts/lp_multiwindow_stability_v1_readonly.py:37`（定义）、**:70**（`classify_stability` 默认 min_frac）；`scripts/lp_funnel_autopsy_v1_readonly.py:46`（定义）、**:127**（multiwindow_stable 闸门距离）；docs 提及 scripts/lp_tp_d_compare_v1_readonly.py:144；测试 tests/test_lp_multiwindow_stability_v1_readonly.py:5,53、tests/test_lp_d2_window_discretization_v1.py:4,25 |

**RH-03 注意**：`STABLE_MIN_FRAC` 属于多窗口稳定性/漏斗模块，与 NetCover 引擎无调用关系；若 RH 装配层需要稳定性闸门，须显式 import `lp_multiwindow_stability_v1_readonly.classify_stability`。

---

# E. 成本模型接口

文件：`scripts/lp_swap_cost_model_v1_readonly.py`（331 行）

## E1. `clmm_token0_value_fraction`（:184–218）

```python
def clmm_token0_value_fraction(entry_price: float, range_pct: float) -> float:
```

- `entry_price`：>0，token1/token0 计价；`range_pct`：(0,100)，对称半区间百分比。
- 返回 token0 价值占比 ∈ (0,1)。内部 lazy import `lp_il_inventory_engine_v1_readonly` 的 `position_state_from_capital` + `current_inventory`（:197–198），计算 `xP/(xP+y)`。

## E2. `exit_conversion_cost_usd`（:220–241）

```python
def exit_conversion_cost_usd(
    value_usd: float,
    l_active_raw: float,
    price: float,
    fee_tier: float,
    dec0: int,
    dec1: int,
    side: str = "sell_base",
) -> float:
```

- 必需输入：`value_usd`（USD 头寸价值，≤0→0.0）、`l_active_raw`（原始池流动性，≤0→0.0）、`price`（token1/token0，≤0→0.0）、`fee_tier`（分数）、`dec0`/`dec1`（代币精度）、`side`（`"buy_base"`|`"sell_base"`）。
- 返回 `value_usd * fee_tier + value_usd * (slip_bps / 1e4)`，slip 由 `slippage_bps_for_swap`（:119）算出。

## E3. `roundtrip_cost_usd`（:243–265）

```python
def roundtrip_cost_usd(
    size_usd: float,
    l_active_raw: float,
    price: float,
    fee_tier: float,
    dec0: int,
    dec1: int,
) -> float:
```

- = `exit_conversion_cost_usd(size, ..., "buy_base")` + `exit_conversion_cost_usd(size, ..., "sell_base")`；`size_usd<=0` 或 `l_active_raw<=0` 或 `price<=0` → 0.0。
- **注意**：装配器并不直接调用 `roundtrip_cost_usd`，而是用 `_swap_components`（lp_cost_sensitivity:142）自行算 entry/exit/slippage 三项，`round_trip_cost_usd = entry+exit+slippage`（inputs:1068–1074）。`roundtrip_cost_usd` 是独立工具函数（自测用）。

---

# F. 固定快照不变性（Base-invariance）验证方法

## F1. 可复用脚本：`scripts/lp_netcover_snapshot_replay_v1_readonly.py`（80 行）

**用法**：

```bash
python3 scripts/lp_netcover_snapshot_replay_v1_readonly.py \
  --db <snapshot.db> --code-root <repo_root> --out <out.json>
```

**`replay(*, db_path: Path, code_root: Path) -> dict`**（:20–64）机制：

1. `sys.path.insert(0, code_root)` 后 `importlib.import_module("scripts.lp_netcover_inputs_v1_readonly")` + engine —— **code_root 决定跑哪份代码**（新旧切换的唯一开关）。
2. 只读打开 SQLite：`sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)`。
3. 读 `select id, as_of, pool, score_json from opportunity_scores order by id`（:28）。
4. 每行 `json.loads(score_json)`；若 `protocol_type` 为 None 且 `project ∈ {aerodrome-slipstream, uniswap-v3}`，**仅内存中**设 `protocol_type="clmm"`（:40–44，复刻生产边界审计过的 Base 映射，不改库）。
5. `position = capital_usd or position_requested_usd or 50.0`。
6. `assembled = inputs.assemble_netcover_inputs(source, position_usd=..., scanner_measured_evidence=source.get("scanner_measured_cross_pool_evidence"))`。
7. `gated = engine.apply_netcover_gate([assembled])[0]`。
8. 每行输出：`id, as_of, pool, netcover_ratio, netcover_pass, netcover_reason, position_cap_pass, position_cap_reason, entry_cost_usd, exit_cost_usd, slippage_usd`（或 `replay_error`）。
9. 返回 `{db, code_root, row_count, netcover_pass_counts, position_cap_counts, rows}`；CLI 写 sorted JSON（sort_keys, indent 2）。

**该脚本无测试引用**（tests/ 与 docs/ 中 grep `lp_netcover_snapshot_replay` 无命中）——它是 J3 审计的一次性工具，但接口自包含、可直接复用。

## F2. 逐闸 diff 方法（J3 实例）

依据 `CODEX_任务包_J_闸门校准与口径对账_2026-08-11.md:122`（"用固定快照法（sqlite3 backup 复制 scanner.db，新旧代码跑同一份，逐个闸对照）"）与 `reports/lp_tp_j/20260814_j3/J3_LEG_COST_AUDIT.md:24–36`：

1. **固定快照**：用 SQLite backup API 从 `reports/lp_scanner/scanner.db`（现存，2GB，`opportunity_scores` 表 114,422 行，列：id/as_of/pool/symbol/fee_ev_usd/reward_ev_usd/il_ev_usd/lvr_ev_usd/risk_usd/expected_net_yield_usd/expected_net_yield_pct/netcover_ratio/accepted/rejection_reason/score_json/source）复制出 `scanner.J3.snapshot.db`。
2. **旧代码跑一遍**：旧 code root（git worktree 检出 c9419d5）→ `base_snapshot_pre_j3.json`。
3. **新代码跑一遍**：工作树 → `base_snapshot_post_j3.json`。
4. **逐行 diff**：按 `id` 对齐，比较 9 个 gate 字段；记录 `changed_rows`（数值变化）与 `changed_gate_rows`（闸门展示字段变化），存 `BASE_INVARIANCE_COMPARISON.json`。

**J3 实测结果**（`reports/lp_tp_j/20260814_j3/BASE_INVARIANCE_COMPARISON.json`，现存）：结构 `{changed_gate_rows: 54, changed_rows: 3245, changes: [{id, as_of, pool, changes: {field: [old, new]}}]}`；6,812 行中 NetCover pass 51→61、PositionCap 3107/3705 不变、3,245 行 entry/exit/slippage 数值变化。

**注意**：`base_snapshot_{pre,post}_j3.json` 两个中间产物**不在仓库中**（已清理）；diff 脚本本身也不在仓库（一次性），可复用部分 = replay 脚本 + 一个按行对齐的 JSON diff（约 30 行）。RH-03 验收时建议：快照 → 旧 code-root replay → RH 新 code-root replay → 逐行 diff 出 `BASE_INVARIANCE_COMPARISON.json`，作为 spec 的验收命令。
