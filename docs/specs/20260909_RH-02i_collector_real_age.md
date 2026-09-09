# RH-02i：采集器写真实数据龄，并说清 `reference_mid` 到底是什么

## 两个实测问题

### 1. `reference_age_secs` 被写死成 0，freshness 闸因此形同虚设

```python
# scripts/lp_rh_collector_v1_readonly.py:233
"reference_age_secs": 0 if price_text else None,
```

`scanner.db` 全部 5,254 行该列都是 0（不同取值 = 1）。
而 `shadow_runner.compute_conjuncts` 的 freshness 闸是
`age > REFERENCE_MAX_AGE_SECS(120) → fail`，**在这个数据上永远不触发**。
闸存在、测试通过、实际是空的。

**注意方向**：这与本仓已发现的 `session="UNKNOWN"` 同族但更坏——
`UNKNOWN` 是 fail-closed（保守），**`0` 是 fail-open（闸门失效而无人察觉）**。

### 2. `reference_mid` 装的是 DEX 池价，不是参考价

第 211 行：`price_text = price_to_text(compute_price_human(sqrt_price, dec0, dec1))`
——由 `sqrtPriceX96` 算出的**池价**。采集器**不调用任何 REST**，
所以这一列里从来没有过外部参考价。

任何把它当参考价用的下游都在做错误的比较。
（`premium.db` 不受影响：那里链价与 REST 参考价是分开的两列。）

## 只改一个文件

只改 `scripts/lp_rh_collector_v1_readonly.py`，
测试追加进 `tests/test_lp_rh_collector_v1_readonly.py`。
**现有测试一条不许改、不许删。**

### 1. 写真实数据龄

采集器已经拿到 `good_block`。**再取该区块的 `timestamp`**（`eth_getBlockByNumber`，
已有的 RPC 通道），令

```python
"reference_age_secs": (now_epoch - block_timestamp) if block_timestamp else None
```

**取不到区块时间戳时写 `None`，不要写 0。**
（本链出块 0.102 s，正常龄应在 0–5 秒量级；采集器每轮多一次 RPC 调用，可接受。）

### 2. 说清这一列是什么

在写入处加注释，并在模块 docstring 里写明：

> `reference_mid` 存的是**由 `sqrtPriceX96` 算出的 DEX 池价**，不是外部参考价。
> 本采集器不调用任何 REST。需要「链价 vs 参考价」的溢价分析请用
> `reports/lp_rh/premium.db`（`lp_rh_premium_recorder`），那里两者是分开的列。

**不要改列名**——重命名会打断所有下游读取；本包只让语义可见。

## 新增测试（**≥8 条**）

- **自证其罪**：注入两个时间戳不同的区块 → 写出的两行 `reference_age_secs`
  **不相等**。这条直接防止该列再退化成常量。
- 区块时间戳取不到 → 该列为 `None`（**`is None` 断言，不是 0**）。
- 龄由 `now − block_timestamp` 算出：注入固定时钟与固定区块时间戳，断言精确值。
- 区块时间戳在未来（时钟偏移）→ 龄为负数时写 `0`，**并在 `health_flags_json`
  里加一个标记**（自定名如 `CLOCK_SKEW`），不要静默夹成 0。
- `price_text` 为 `None` 时该列仍为 `None`（保持现有行为）。
- 模块 docstring 含 “DEX pool price” 与 “not an external reference” 字样
  （用 `assert ... in mod.__doc__` 断言，防止说明被删）。
- 现有的 `session="UNKNOWN"` 行为**不变**（本包不动它，回归断言）。
- 每轮 RPC 调用次数增加不超过 1 次（断言 mock 的调用计数）。

## 不许动
不改列名。不改其他脚本。不联网（测试用注入的假 RPC）。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。
**注意采集器正在运行**，改完由主脑负责重启，你不要去停它。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_collector_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向全绿且新增 ≥8；全量 0 failed / 14 skipped。两条命令尾部原样贴出。
