# Stage A 主表 26 小时采了 6131 行，14 列里只有 4 列真正有值

日期：2026-09-09 主脑全量统计（`reports/lp_rh/scanner.db`）

## 实测

```
列                      NULL 率        判定
---------------------------------------------------------------
derived_block_hash      6131/6131      全空  <== 溯源列
derived_block_number    6131/6131      全空  <== 溯源列
multiplier_human        6131/6131      全空
reference_bid           6131/6131      全空
reference_ask           6131/6131      全空
oracle_paused           6131/6131      全空
session                 0/6131         恒为 "UNKNOWN"（distinct=1）
---------------------------------------------------------------
reference_mid           32/6131        有值（但装的是 DEX 池价，非参考价）
reference_age_secs      32/6131        有值（已修，实测 age=3）
source_payload_hash     0/6131         有值（distinct=6124）
health_flags_json       0/6131         有值（distinct=2）
```

## 三类成因，处置优先级不同

**第一类：数据在手边却没写（可立即修）**
`derived_block_hash` / `derived_block_number` 根本不在 `insert_row` 的字典里。
而 `collect_round` 早就调过 `eth_getBlockByNumber(hex(good_block), False)`，
区块对象就在局部变量 `blk_age` 里，只取了 `timestamp`，没取 `hash`。

**第二类：有现成模块却写死常量（可立即修）**
`"session": "UNKNOWN"` 是字面量。而 `classify_session` 模块一直存在，
`shadow_runner` 正在用它。

**第三类：采集器按设计不打 REST（属设计变更，需用户决定）**
`reference_bid` / `reference_ask` / `multiplier_human` 依赖 REST 参考价，
采集器的 docstring 明确写了「no REST here」，`reference_mid` 存的是
`sqrtPriceX96` 换算出的 DEX 池价。要填这三列，等于让采集器新增 REST 依赖
——这是设计决定，不是 bug 修复。

`oracle_paused` 需要额外链上 `paused()` 调用（选择器 `0x5c975abb`），另算。

## 影响一：重组回滚链在真实数据上作用于空集

`plan_rollback` / `apply_rollback` 靠 `derived_block_hash` 定位受被弃链影响的行。
该列全空 ⇒ **匹配不到任何行**。

这条链上的三个包——重组检测、RH-02k 的孤块解析、回滚执行——
逻辑都正确且都有绿测试，但**合起来对真实数据没有任何作用**。
主脑验收 RH-02k 时做的 18 条独立断言用的是**自己填好溯源列的构造数据**，
所以验出了「逻辑对」，验不出「真实数据里没有对象」。

**教训**：验收一个消费某列的模块时，必须同时查那一列在真实库里的填充率。
「模块正确」与「模块有用」是两个问题。

## 影响二：Stage A 的覆盖率衡量的是行数，不是列的完整性

覆盖率 96.18%（门槛 99%）算的是时间维度上有没有采到样本。
**它不检查采到的样本里有多少列是空的。** 因此这 6 列全空不会让覆盖率下降，
也不会让任何测试变红——Stage A 可以在数据严重残缺的情况下「毕业」。

## 处置

- `docs/specs/20260909_RH-02p_collector_provenance.md` 已就绪：
  补溯源两列 + 真实时段分类。两者数据都在手边，不需要 REST。
- 第三类（REST 参考价三列）**不在本轮范围**，需用户决定是否让采集器打 REST。
- **已有 6131 行的溯源列不可追回**，与覆盖率的历史亏空同性质。
- 修复后**必须重启采集器**，正在跑的是旧代码。
