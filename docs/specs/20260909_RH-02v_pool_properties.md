# RH-02v：池注册表的四列空着，因为采集端从没去问过链

## 现状

`rh_pool_registry` 唯一那行：
```
pool_address = 0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca
protocol     = v3
token0       = None     token1       = None
fee          = None     tick_spacing = None
pool_id      = None     hooks        = None
```

**`write_pool_registry` 没有问题**——它已经会从 candidate 读
`token0` / `token1` / `fee` / `tick_spacing` / `pool_id` / `hooks`。
问题在采集端：`run_once` 传的 candidate 只有一个键
```
candidates = [{"pool": SEED_ADDRESSES["POOL_USDG_WETH"]["address"]}]
```

## ★`pool_id` 与 `hooks` 不在本包范围，也不该填★

这两个是 **Uniswap v4** 的概念；本池 `protocol = v3`，**对它们而言 NULL 是正确值**。
不要为了让哨兵不报 EMPTY 而填任何东西——
**列健康哨兵是发现工具，不是判决工具**，哪些空是缺陷要由人判断。

## 实测过的选择器（主脑 2026-09-09 对本池实调，全部成功，直接用）

```
token0()      0x0dfe1681  -> 0x0bd7d308f8e1639fab988df18a8011f41eacad73
token1()      0xd21220a7  -> 0x5fc5360d0400a0fd4f2af552add042d716f1d168
fee()         0xddca3f43  -> 100
tickSpacing() 0xd0c93a7c  -> 1
```
`fee` 与 `tick_spacing` 的链上值与 `pool_meta.json` 中的 `100` / `1` **一致**
（交叉验证通过）。返回值是 32 字节右对齐：地址取末 40 个十六进制字符并小写，
整数用 `int(value, 16)`。

## 只改一个文件 + 其测试

### `scripts/lp_rh_evidence_collector_v1_readonly.py`

- 新增 `collect_pool_properties(rpc_fn, pool) -> dict`
  用 `_call(rpc_fn, "eth_call", [{"to": pool, "data": <选择器>}, "latest"])`
  依次取四项。返回只含**成功取到**的键，形如
  `{"token0": "0x…", "token1": "0x…", "fee": 100, "tick_spacing": 1}`。
  - **任何一项失败 → 该键不出现在返回值里**（于是 writer 写 NULL）。
    **不得填 0、空串或猜测值**——`fee = 0` 是一个合法费率，与"没问到"必须可区分。
  - 返回值里**不得**包含 `pool_id` 或 `hooks`。
  - 结果非 32 字节/长度不足/不以 `0x` 开头 → 视为失败，跳过该键。
- `run_once`：把该函数的结果**合并进** candidate
  （`{"pool": <地址>, **props}`），其余逻辑不变。
  失败不得中断其余环节——沿用现有 `try/except` 收集到 `errors` 的模式。

## 不许动
不改 `write_pool_registry`（它已经是对的）。不改 `collect_assets` /
`collect_attestations` / `write_assets` / `write_attestations`。
不改表结构。不联网（测试用假 `rpc_fn`）。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。

## 新增测试 `tests/test_lp_rh_pool_properties_v1_readonly.py`（≤240 行，**≥14 测试**）
顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。
**不许联网。** 假 `rpc_fn` 返回 JSON-RPC 信封（`{"result": …}` / `{"error": …}`），
**这是 `_call` 的契约**。必测：

- 四项都成功 → 返回四个键，`token0` 是小写 40 位十六进制地址（带 `0x`）。
- `fee` 与 `tick_spacing` 是 `int`（不是十六进制字符串）。
- 用实测值构造：`fee` 返回 `0x64` → `100`；`tickSpacing` 返回 `0x1` → `1`。
- **★`fee()` 返回 error → 返回值里没有 `"fee"` 键★**（而不是 `fee: 0`）
- **★`fee()` 返回代表 0 的 `0x0…0` → `fee == 0` 且键存在★**
  （0 是合法费率，与"没问到"必须可区分——这两条合起来才是本包的意义）
- `token0()` 返回 error → 无 `"token0"` 键，但其余三项仍在（一项失败不影响其余）。
- 结果不以 `0x` 开头 / 长度不足 → 该键缺席。
- 返回值**从不包含** `pool_id` 与 `hooks`（两条断言）。
- 全部失败 → 返回空 dict（不是 `None`）。
- 地址被转成小写（构造大写返回值，断言小写）。
- 与 writer 联动：把返回值合并进 candidate 调 `write_pool_registry`，
  读回该行，断言 `token0` / `token1` / `fee` / `tick_spacing` 四列非 NULL 且等于注入值。
- 联动：`fee` 缺席时该列写入 NULL（而不是 0）。
- 联动：`pool_id` 与 `hooks` 写入后仍为 NULL（v3 正确行为）。
- `run_once` 的报告里 `pool_registry.written` 仍为 1（回归，不破坏既有行为）。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_pool_properties_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥14 全绿；全量 **0 failed / 14 skipped**（现有 4245 passed 一条都不许退）。
两条命令尾部原样贴出。
