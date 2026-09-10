# RH-02cg — T34：用真实 gas 观测替代静态估值

## 背景

PRD §20 的 T34 有模块也有测试，但 `scripts/lp_rh_gas_estimator_v1_readonly.py`
**被 runner / netcover 引用 0 次**（codex 在 PRD 对账时标了「⚠ 尚未接入完整端到端主链」）。

NetCover 的 gas 成本现在来自 `pool_meta.json` 的一个静态数字：

```
pool_meta.gas_usd_estimate = 0.4005191780352
```

而 `reports/lp_rh/gas_history.db` 的 `rh_gas_observations` 有 **104 条真实观测**，
每 15 分钟一条：

```
列: observed_at, gas_price_wei, native_price_usd, gas_usd, block_number, receipt_n, source
最近: 2026-09-10T16:00:02Z  gas_price_wei=136462000  native_price_usd=2440.46  gas_usd=0.2664
```

**静态值比当前真实值高约 50%**。方向上偏保守（成本高估 → NetCover 偏严），
但它是个死数字，链上 gas 一变就失真，而且没人知道它什么时候失真。

## 要做的事

### 1. 新增取数函数

在 `scripts/lp_rh_gas_estimator_v1_readonly.py` 里新增：

```python
def observed_gas_usd(
    conn,                      # rh_gas_observations 所在库的只读连接
    *,
    now: str,                  # 判定时刻，ISO8601（可注入，便于测试）
    max_age_secs: int = 3600,  # 超过这个年龄的观测不用
    min_samples: int = 3,      # 少于这么多条就不给结论
) -> dict:
    """近期真实 gas 观测的中位数。

    返回 {"gas_usd": Decimal|None, "source": str, "sample_count": int,
          "newest_observed_at": str|None, "reason": str}
    """
```

判定顺序与 reason（每条都要能分辨）：

| 情况 | reason | gas_usd |
|---|---|---|
| 表不存在 | `GAS_OBSERVATIONS_TABLE_MISSING` | `None` |
| 窗口内 0 条 | `GAS_OBSERVATIONS_EMPTY` | `None` |
| 窗口内条数 < `min_samples` | `GAS_OBSERVATIONS_INSUFFICIENT` | `None` |
| 最新一条超过 `max_age_secs` | `GAS_OBSERVATIONS_STALE` | `None` |
| 正常 | `OK` | 中位数（Decimal） |

- **取中位数不是平均**：gas 有尖峰，平均会被单条异常拉走。
  复用文件里已有的 `_median`。
- 解析不了的 `gas_usd` 值跳过并计数，**不要当成 0**。
- 只读，绝不写这个库。

### 2. netcover 输入优先用观测值

`scripts/lp_rh_netcover_inputs_v1_readonly.py` 现在（约 L128）：

```python
gas_usd_estimate = _to_float(evidence.get("gas_usd_estimate"))
if gas_usd_estimate is None:
    gas_usd = None
    missing.append(("gas_usd_estimate", "CHAIN_DATA_UNAVAILABLE"))
else:
    gas_usd = gas_usd_estimate
```

改为：evidence 里若带 `observed_gas_usd`（由调用方注入）就优先用它，
否则退回 `gas_usd_estimate`。**两种情况都要在返回的 record 里留下
`gas_usd_source`**，取值 `"observed"` / `"static_pool_meta"` / `None`。

**这一条是重点**：静默降级到静态值，就等于没人知道成本是真的还是猜的。
本仓库已确认 27 例「静默假绿」，全是这么来的。

`gas_usd_source` 要一路传到 `apply_netcover_gate` 的输出里
（它 `dict(source)` 复制输入，所以只要 key 在 record 上就会带过去）。

### 3. runner 注入观测值

`scripts/lp_rh_shadow_runner_v1_readonly.py` 的 `_evidence_for()`
（搜 `_POOL_EVIDENCE_KEYS`）负责把 pool_meta 的证据并进 sample。

在 `run_episode` 开始时取一次观测值（**整轮取一次，不要每步取**——
每步查库会把一轮 200 步变成 200 次查询），放进 pool_meta 的副本里传下去。

- gas 库路径：默认 `reports/lp_rh/gas_history.db`，
  加一个 `gas_db_path` 关键字参数便于测试注入，**默认值不改变现有调用**
- 取不到（库不存在、观测不足、过期）→ **不注入 `observed_gas_usd`**，
  自然退回静态值，且 `gas_usd_source` 会是 `"static_pool_meta"`
- 把这一轮用的 gas 来源记进 episode summary（daemon 日志能看见）

### 4. 经济表记下来源

`rh_economic_evaluations` 的 `cost_components_json` 已经存 8 个成本项。
在同一个 JSON 里加 `"gas_usd_source"`，值取自上面。
**不要新增数据库列**（改 schema 是另一回事）。

## 不许动

- 不要改 `estimate_gas_usd` / `round_trip_gas_usd` / `_median` 的现有行为。
- 不要改 NetCover 的公式、阈值、`_GATE_INPUT_KEYS`。
- 不要改 `pool_meta.json`（静态值保留作兜底）。
- 不要碰 `scripts/lp_rh_shadow_daemon_v1_readonly.py`（另一条线刚改完）。
- 不要碰 `scripts/lp_rh_readiness_v1_readonly.py`、
  `scripts/lp_rh_graduation_evidence_v1.py`（另一条线正在写）。
- 对 `reports/lp_rh/gas_history.db` 与 `scanner.db` **只读**（`mode=ro`）。
- **不要重启或 kill 任何进程**（采集器 1168725 / daemon 1569118 在跑生产）。
- **不要执行任何 git 命令。**
- 单次 Write/Edit ≤150 行或 6000 字符。

## 测试

### `tests/test_lp_rh_gas_estimator_v1_readonly.py`（已存在，追加）

1. 5 条新鲜观测 → 返回中位数，`reason == "OK"`，`sample_count == 5`。
2. 表不存在 → `gas_usd is None`，reason `GAS_OBSERVATIONS_TABLE_MISSING`。
3. 窗口内 0 条 → `GAS_OBSERVATIONS_EMPTY`，`gas_usd is None`（**不是 0**）。
4. 2 条（< min_samples=3）→ `GAS_OBSERVATIONS_INSUFFICIENT`。
5. 最新一条 2 小时前（max_age_secs=3600）→ `GAS_OBSERVATIONS_STALE`。
6. 含一条异常尖峰（比其余大 100 倍）→ 中位数不被它带走
   （断言结果接近其余几条，而非接近尖峰）。

### `tests/test_lp_rh_netcover_inputs_v1_readonly.py`（已存在，追加）

7. evidence 带 `observed_gas_usd` → `gas_usd` 用它，
   `gas_usd_source == "observed"`。
8. evidence 不带 → 用 `gas_usd_estimate`，`gas_usd_source == "static_pool_meta"`。
9. 两者都没有 → `gas_usd is None`，`missing` 含 `gas_usd_estimate`，
   `gas_usd_source is None`。

### `tests/test_lp_rh_shadow_runner_v1_readonly.py`（已存在，追加）

10. 注入一个带新鲜观测的临时 gas 库 → 该 episode 的
    `rh_economic_evaluations.cost_components_json` 里
    `gas_usd_source == "observed"`。
11. gas 库不存在 → episode 正常跑完，`gas_usd_source == "static_pool_meta"`。
    ——这条保证接入不会让现有流程变脆。

## 验收标准（主脑会逐条查）

1. 三个测试文件全绿，新增 ≥11 条。
2. 全量 `python3 -m pytest tests/ -q` 通过。
3. 真实库上取一次观测值（只读）：
   ```
   python3 -c "
   import importlib.util, sqlite3, datetime
   s=importlib.util.spec_from_file_location('g','scripts/lp_rh_gas_estimator_v1_readonly.py')
   m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
   c=sqlite3.connect('file:reports/lp_rh/gas_history.db?mode=ro',uri=True)
   now=datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')
   print(m.observed_gas_usd(c, now=now))
   "
   ```
   应返回一个 0.2 附近的中位数、`reason == "OK"`。把输出贴进总结，
   并与 pool_meta 的 0.4005 做对比说明。
4. `git status --short` 里只有那三个脚本及其测试被改动。
