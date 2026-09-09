# RH-03e：gas 的时间序列——没有它，资金政策只能靠单点

## 为什么需要

实测（`CAPITAL_POLICY_RECOMPUTE_20260909.md`）：**最小可行仓位对 gas 近似线性**。
gas 0.20 → 仓位 $25.5；gas 0.4005（今日）→ $50.5；gas 2.00 → $252。
而 gas 一天内变了 13%、七分钟内变了 0.5%。

**任何用单点 gas 算出的本金都会在 gas 变化时失效。**
按分布定政策（或设 gas 上限闸）都需要时间序列，而现在
`pool_meta.gas_provenance` **只保留最近一次刷新**，没有历史。

现有观测点只有 3 个（0.4614 / 0.4026 / 0.4005），不足以谈分布。

## 只新建一个实质文件 + 其测试

### 1. `scripts/lp_rh_gas_history_v1_readonly.py`（≤260 行）

**模块自身不联网**：链上数据经注入的 `rpc_fn` 取得，
`native_price_usd` 由调用方给入（与 RH-03d 同约定）。
**复用 RH-03d 已验收的采集与计算，不要重写**：
```
from scripts.lp_rh_gas_refresh_v1_readonly import collect_gas_inputs, compute_refresh
```

- `ensure_table(conn)`：幂等建 `rh_gas_observations`
  （`observed_at TEXT NOT NULL`、`gas_price_wei INTEGER`、`native_price_usd TEXT`、
  `gas_usd TEXT`、`block_number INTEGER`、`receipt_n INTEGER`、`source TEXT`），
  主键 `(observed_at, block_number)`。**金额列一律 decimal TEXT**
  （`gas_usd`、`native_price_usd` 与 `rh_assets.multiplier_raw` 同规矩，
  绝不经 `float`——见 RH-02n）。
- `record_observation(conn, *, rpc_fn, native_price_usd, source="gas-history-v1") -> dict`
  取一次观测并写入。**`compute_refresh` 的 `verdict != "REFRESHED"` 时不写任何行**，
  返回 `{"written": False, "verdict": ...}`。**绝不写 0 或占位值。**
- `summarize(conn, *, limit=None) -> dict`
  返回 `{"n", "min", "max", "median", "p90", "latest", "oldest_at", "newest_at"}`，
  金额均为**字符串**（Decimal 转 str）。`n == 0` 时各统计量为 `None`（**不是 0**）。
  **用 `decimal.Decimal` 排序与取分位，不得用 float。**
- `main()`：`--db --native-price-usd --once --summary`。
  **`--once` 才写入**；`--summary` 只读打印。默认什么都不做。

### 2. `tests/test_lp_rh_gas_history_v1_readonly.py`（≤240 行，**≥16 测试**）
顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。
**不许联网**，用假 `rpc_fn`（JSON-RPC 信封 `{"result": …}` / `{"error": …}`
——这是 `_call` 的契约）与内存 SQLite。必测：

- 幂等建表：连跑两次不报错。
- 正常观测写入一行，`gas_usd` 读回是 **`str`**，且逐字符等于计算值。
- **★`rpc_fn` 失败 → `written is False` 且表中**零行**★**（不写占位）
- **★`native_price_usd` 为 `None`/0/负 → 不写★**（三条）
- 同一 `(observed_at, block_number)` 重复写只有一行（幂等）。
- `summarize` 空表 → `n == 0` 且 `median is None`（**不是 0**）。
- `summarize` 三条已知值 → `min`/`max`/`median` 精确等于预期字符串。
- **★`summarize` 全程不经 float：注入 `'0.100000000000000001'` 与
  `'0.100000000000000002'`，断言二者在结果中**可区分**★**
  （float 会把它们压成同一个数）
- `p90` 在 10 条已知值上等于预期值。
- `latest` 是最新 `observed_at` 对应的值，不是最大值。
- `n == 1` 时 `min == max == median == latest`。
- `--summary` 不写库（跑前后行数相同）。
- `main` 不带任何标志时不写库且返回 0。
- 金额列在 store 口径下是 decimal TEXT（断言类型为 `str`，两条：`gas_usd`、`native_price_usd`）。

## 不许动
不改 `lp_rh_gas_refresh_v1_readonly.py`、不改 `lp_rh_gas_estimator_v1_readonly.py`、
不改 `pool_meta.json`、不改任何闸门。**本包只记录，不影响任何判定。**
不联网。单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_gas_history_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥16 全绿；全量 **0 failed / 14 skipped**。两条命令尾部原样贴出。

## 落地后（写进 commit message，不要写进代码）
本包只是**能力**。要产生分布还需周期性调用——
**这正是本项目反复踩的「能力就绪未上线」**，因此完成后应立即决定上线方式
（cron 每 15 分钟 `--once`），不要留着。
