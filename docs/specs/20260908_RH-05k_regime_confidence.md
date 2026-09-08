# RH-05k：regime 标签必须带信噪比，否则两个 UNSTABLE 含义完全不同

## 实测依据

`reports/rh_pivot/20260907T124500Z/RH-05-research/PREMIUM_BY_SESSION_20260908.md`：

| 标的 | 时段 | stdev | floor | `stdev/floor` | regime |
|---|---|---:|---:|---:|---|
| QQQ | 盘后 | 2.28 | 0.77 | **3.0** | `UNSTABLE` |
| NVDA | 盘后 | 2.67 | 2.44 | **1.09** | `UNSTABLE` |

**两者拿到同一个标签，但一个是真振荡、一个只是刚够过分辨率闸。**
`premium_regime` 目前只返回字符串，读者无从分辨。

## 改哪些文件

只改 `scripts/lp_rh_premium_series_v1_readonly.py`，
测试追加进 `tests/test_lp_rh_premium_series_v1_readonly.py`。
**现有 37 条测试一条不许改、不许删。**

### 1. `series_stats` 新增 `signal_to_floor`

`stdev_bps / resolution_floor_bps`，用 `Decimal`。
`resolution_floor_bps` 为 `None` 或 `0` → 该字段为 `None`（**不是 0，也不是 inf**）。
`status` 非 `COMPUTED` 时同样为 `None`，但键必须存在（结构稳定）。

### 2. 新增 `regime_confidence(stats) -> str`

- `signal_to_floor is None` → `"UNKNOWN"`
- `< 1` → `"BELOW_FLOOR"`（此时 `premium_regime` 本就返回 `INSUFFICIENT_RESOLUTION`）
- `1 <= x < 2` → `"MARGINAL"`（NVDA 盘后是 1.09，落这一档）
- `2 <= x < 5` → `"ADEQUATE"`（QQQ 盘后 3.0）
- `>= 5` → `"STRONG"`

**这是一个独立函数，不改 `premium_regime` 的返回值**——现有调用方不受影响。

### 3. `lvr_haircut_frac` 在 `MARGINAL` 时的行为

**保持现状不变。** 本包只增加可见性，不改变任何闸门行为。
若你认为 `MARGINAL` 应该影响 haircut，**在报告里写出理由，不要直接改**——
那是主脑要裁决的政策问题。

## 新增测试（**≥10 条**）

- `signal_to_floor` 在 floor 为 `None` 时是 `None`（**`is None` 断言**）。
- floor 为 `0` 时也是 `None`（不得除零、不得返回 inf）。
- `status` 为 `INSUFFICIENT_SAMPLES` / `INPUTS_UNAVAILABLE` 时键存在且为 `None`。
- 五个档位各一条测试，用构造数据精确落在边界上：
  `0.99 → BELOW_FLOOR`、`1.0 → MARGINAL`、`1.99 → MARGINAL`、
  `2.0 → ADEQUATE`、`5.0 → STRONG`（**边界取闭区间，逐条断言**）。
- **复现实测**：构造 NVDA 盘后场景（stdev≈2.67、floor≈2.44）→ `MARGINAL`；
  构造 QQQ 盘后场景（stdev≈2.28、floor≈0.77）→ `ADEQUATE`。
  **断言两者的 `premium_regime` 相同而 `regime_confidence` 不同**——这正是本包的意义。
- `premium_regime` 的返回值集合**未改变**（对五种 regime 各断言一次，回归保护）。
- `lvr_haircut_frac` 的行为未变（对 `MEAN_REVERTING` / `PERSISTENT_OFFSET` /
  `INSUFFICIENT_RESOLUTION` 各断言一次）。

## 不许动
不改 `premium_regime` 与 `lvr_haircut_frac` 的行为。不改 `LVR_COEFFICIENT_MODEL`。
不联网。单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_premium_series_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥47 全绿（原 37 + 新增 ≥10）；全量 0 failed / 14 skipped。两条命令尾部原样贴出。
